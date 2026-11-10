frappe.ui.form.on("iCorp Client Link", {
	refresh: function (frm) {
		show_clarity_warnings(frm);
		render_duplicate_name_siblings(frm);
		render_match_status_label(frm);
		render_child_clients(frm);
		toggle_related_customers_editability(frm);
		add_create_customer_button(frm);
	},
});

const _EVIDENCE_LABELS = {
	confirmed: "Strong (2+ sources agree)",
	project_only: "Projects only",
	existing_field_only: "Legacy field only",
	name_exact_only: "Exact name only",
	name_fuzzy_only: "Similar name only",
	conflict: "Conflicting evidence",
	partner_suspect: "Likely partner",
	assigned_manually: "Manually assigned",
	unmatched: "No evidence",
};

function render_match_status_label(frm) {
	const field = frm.get_field("match_status");
	if (!field || !frm.doc.match_status) return;
	const label = _EVIDENCE_LABELS[frm.doc.match_status] || frm.doc.match_status;
	field.$wrapper.find(".control-value").text(label);
}

function toggle_related_customers_editability(frm) {
	const is_review_site = frm.doc.__onload && frm.doc.__onload.is_review_site;
	frm.set_df_property("related_customers", "read_only", is_review_site ? 0 : 1);
	frm.fields_dict.related_customers.grid.toggle_enable("role", !!is_review_site);
}

function add_create_customer_button(frm) {
	const is_review_site = frm.doc.__onload && frm.doc.__onload.is_review_site;
	if (!is_review_site || frm.is_new() || frm.doc.customer) return;

	frm.add_custom_button(__("Create Customer..."), function () {
		const dialog = new frappe.ui.Dialog({
			title: __("Create Customer for this iCorp Client"),
			fields: [
				{
					fieldname: "customer_name",
					fieldtype: "Data",
					label: __("Customer Name"),
					reqd: 1,
					default: frm.doc.client_name || "",
				},
				{
					fieldname: "customer_type",
					fieldtype: "Select",
					label: __("Customer Type"),
					options: "Company\nIndividual",
					default: "Company",
					reqd: 1,
				},
				{
					fieldname: "customer_group",
					fieldtype: "Link",
					options: "Customer Group",
					label: __("Customer Group"),
					reqd: 1,
					get_query: function () {
						return { filters: { is_group: 0 } };
					},
				},
				{
					fieldname: "territory",
					fieldtype: "Link",
					options: "Territory",
					label: __("Territory"),
					reqd: 1,
					default: "All Territories",
					get_query: function () {
						return { filters: { is_group: 0 } };
					},
				},
			],
			primary_action_label: __("Create"),
			primary_action: function (values) {
				frappe.call({
					method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.create_customer_for_client",
					args: {
						docname: frm.doc.name,
						customer_name: values.customer_name,
						customer_type: values.customer_type,
						customer_group: values.customer_group,
						territory: values.territory,
					},
					freeze: true,
					callback: function (r) {
						if (r.message) {
							dialog.hide();
							frm.reload_doc();
						}
					},
				});
			},
		});
		dialog.show();
	});
}

function show_clarity_warnings(frm) {
	frm.dashboard.clear_headline();
	const alerts = [];

	if (frm.doc.match_status === "partner_suspect") {
		alerts.push(
			__(
				"This client's only evidence is Project usage matching its iCorp parent's own Customer ({0}) — likely the managing partner, not the end customer. See 'Related Customers' below.",
				[frm.doc.parent_customer]
			)
		);
	} else if (frm.doc.match_status === "conflict") {
		alerts.push(
			__(
				"Evidence points at more than one Customer. Use 'Flag for merge...' below if two Customer records look like the same company, or assign manually."
			)
		);
	}

	if (frm.doc.duplicate_name_siblings) {
		alerts.push(
			__(
				"Another ACTIVE iCorp client has this exact same name — a live naming collision inside iCorp itself. Check 'Other Active iCorp Clients With This Same Name' below before assigning either one."
			)
		);
	}

	if (frm.doc.has_multiple_customer_candidates) {
		alerts.push(
			__(
				'More than one Customer name looks like a match for this client — see the \'Related Customers\' table below. Mark one row "This client\'s Customer", any duplicates "Duplicate - merge in", and anything that\'s actually a different company "Different company", then save.'
			)
		);
	}

	if (alerts.length) {
		frm.dashboard.set_headline_alert(
			`<div class="alert alert-warning" style="margin-bottom: 0;">${alerts
				.map((a) => `<div>${a}</div>`)
				.join("")}</div>`
		);
	}
}

function render_duplicate_name_siblings(frm) {
	const field = frm.get_field("duplicate_name_siblings");
	if (!field || !frm.doc.duplicate_name_siblings) return;

	const names = frm.doc.duplicate_name_siblings
		.split(",")
		.map((n) => n.trim())
		.filter((n) => n);

	const links = names
		.map(
			(n) =>
				`<a href="/app/icorp-client-link/${encodeURIComponent(
					n
				)}">${frappe.utils.escape_html(n)}</a>`
		)
		.join(", ");

	field.$wrapper.find(".control-value").html(links);
}

function render_child_clients(frm) {
	const field = frm.get_field("child_clients_html");
	if (!field) return;

	field.$wrapper.empty();
	frm.toggle_display("child_clients_html", false);

	if (frm.is_new()) return;

	const docname = frm.doc.name;

	frappe.call({
		method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.get_child_clients",
		args: { parent_client: frm.doc.name },
		callback: function (r) {
			if (frm.doc.name !== docname) return;

			const children = r.message || [];
			if (!children.length) return;

			let rows = children
				.map(function (c) {
					const customer_display =
						c.customer || (c.proposed_customer ? `(${c.proposed_customer}?)` : "—");
					return `
						<tr>
							<td><a href="/app/icorp-client-link/${encodeURIComponent(
								c.name
							)}">${frappe.utils.escape_html(c.display_label)}</a></td>
							<td>${frappe.utils.escape_html(customer_display)}</td>
							<td>${frappe.utils.escape_html(c.match_status || "")}</td>
							<td>${c.sv_machine_count_active || 0}</td>
						</tr>`;
				})
				.join("");

			const html = `
				<div style="margin-top: 10px;">
					<b>${__("Child clients ({0})", [children.length])}</b>
					<table class="table table-bordered" style="margin-top: 6px;">
						<thead>
							<tr>
								<th>${__("Client")}</th>
								<th>${__("Customer")}</th>
								<th>${__("Match Status")}</th>
								<th>${__("Machines")}</th>
							</tr>
						</thead>
						<tbody>${rows}</tbody>
					</table>
				</div>`;

			field.$wrapper.html(html);
			frm.toggle_display("child_clients_html", true);
		},
	});
}
