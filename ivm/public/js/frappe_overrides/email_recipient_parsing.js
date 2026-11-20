frappe.provide("ivm.email_utils");

// JS port of frappe.utils.MULTI_EMAIL_STRING_PATTERN: split on comma or newline,
// but only where the rest of the string has an even number of double quotes.
const EMAIL_LIST_SEPARATOR = /[,\n](?=(?:[^"]|"[^"]*")*$)/;
const BARE_EMAIL = /^[^\s@<>"]+@[^\s@<>"]+$/;

ivm.email_utils.uniqueAddresses = (addresses) => {
	const seen = new Set();
	return addresses.filter((address) => {
		const key = address.toLowerCase();
		if (seen.has(key)) return false;
		seen.add(key);
		return true;
	});
};

ivm.email_utils.splitEmailAddresses = (str) =>
	String(str ?? "")
		.replace(/[\r\n\t]+/g, " ")
		.split(EMAIL_LIST_SEPARATOR)
		.map((token) => token.trim())
		.filter(Boolean);

ivm.email_utils.extractEmailAddress = (token) => {
	const cleaned = String(token ?? "")
		.replace(/[\r\n\t]+/g, " ")
		.trim();
	const open = cleaned.lastIndexOf("<");
	const close = open === -1 ? -1 : cleaned.indexOf(">", open);
	const address = close === -1 ? cleaned : cleaned.slice(open + 1, close);
	return address.trim();
};

ivm.email_utils.parseRecipientString = (str) =>
	ivm.email_utils.uniqueAddresses(
		ivm.email_utils
			.splitEmailAddresses(str)
			.map((token) => ivm.email_utils.extractEmailAddress(token))
			.filter((address) => BARE_EMAIL.test(address))
	);

ivm.email_utils.normalizeRecipientList = (value) => {
	if (!Array.isArray(value)) return ivm.email_utils.parseRecipientString(value);
	return ivm.email_utils.uniqueAddresses(
		value.flatMap((entry) => ivm.email_utils.parseRecipientString(entry))
	);
};

// Monkeypatch 1: recipient normalization for every CommunicationComposer (all doctypes)
{
	const composer = frappe.views.CommunicationComposer.prototype;

	const original_as_recipient_list = composer.as_recipient_list;
	composer.as_recipient_list = function (value) {
		if (!Array.isArray(value)) return ivm.email_utils.parseRecipientString(value);
		return ivm.email_utils.normalizeRecipientList(
			original_as_recipient_list.call(this, value)
		);
	};

	const original_setup_recipient_pills = composer.setup_recipient_pills;
	composer.setup_recipient_pills = function () {
		original_setup_recipient_pills.call(this);
		["recipients", "cc", "bcc"].forEach((fieldname) => {
			const control = this.dialog.fields_dict[fieldname];
			if (!control) return;

			const original_parse = control.parse;
			control.parse = function (value) {
				if (Array.isArray(value)) return original_parse.call(this, value);
				const addresses = ivm.email_utils.parseRecipientString(value);
				return original_parse.call(this, addresses.join(", "));
			};
		});
	};
}

// Monkeypatch 2: CC recovery on reply, applied to FormTimeline.prototype.
// FormTimeline is not global; it is reached through the form footer's make_timeline.
ivm.email_utils.patch_form_timeline_compose_mail = (timeline_prototype) => {
	if (timeline_prototype.__ivm_compose_mail_patched) return;

	timeline_prototype.compose_mail = function (communication_doc = null, reply_all = false) {
		const args = {
			doc: this.frm.doc,
			frm: this.frm,
			recipients:
				communication_doc && communication_doc.sender != frappe.session.user_email
					? communication_doc.sender
					: this.get_recipient(),
			is_a_reply: Boolean(communication_doc),
			title: communication_doc ? __("Reply") : null,
			last_email: communication_doc,
			subject: communication_doc && communication_doc.subject,
			reply_all: reply_all,
			sender: communication_doc?.sender,
		};

		const email_accounts = frappe.boot.email_accounts
			.filter((account) => {
				return (
					!["All Accounts", "Sent", "Spam", "Trash"].includes(account.email_account) &&
					account.enable_outgoing
				);
			})
			.map((e) => e.email_id);

		if (communication_doc && args.is_a_reply) {
			// never CC our own mailboxes or the original sender (already in To);
			// the From address is chosen later in the dialog, so exclude all outgoing accounts
			const excluded = new Set(
				[
					frappe.session.user_email,
					...email_accounts,
					...ivm.email_utils.parseRecipientString(cstr(communication_doc.sender)),
				]
					.filter(Boolean)
					.map((address) => address.toLowerCase())
			);
			const is_kept = (address) => !excluded.has(address.toLowerCase());

			const recovered = ivm.email_utils
				.parseRecipientString(cstr(communication_doc.recipients))
				.filter(is_kept);
			const reply_all_cc = reply_all
				? ivm.email_utils.parseRecipientString(cstr(communication_doc.cc))
				: [];

			args.cc = ivm.email_utils
				.uniqueAddresses([...recovered, ...reply_all_cc])
				.filter(is_kept)
				.join(", ");

			if (reply_all) {
				args.bcc = cstr(communication_doc.bcc);
			}
		}

		if (this.frm.doctype === "Communication") {
			args.message = "";
			args.last_email = this.frm.doc;
			args.recipients = this.frm.doc.sender;
			args.subject = __("Re: {0}", [this.frm.doc.subject]);
		} else {
			const comment_value = frappe.markdown(this.frm.comment_box.get_value());
			args.message = strip_html(comment_value) ? comment_value : "";
		}

		new frappe.views.CommunicationComposer(args);
	};

	timeline_prototype.__ivm_compose_mail_patched = true;
};

{
	const footer = frappe.ui.form.Footer.prototype;
	const original_make_timeline = footer.make_timeline;
	footer.make_timeline = function () {
		original_make_timeline.call(this);
		ivm.email_utils.patch_form_timeline_compose_mail(Object.getPrototypeOf(this.frm.timeline));
	};
}
