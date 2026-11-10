frappe.listview_settings["iCorp Client Link"] = {
	add_fields: [
		"is_active",
		"customer",
		"match_status",
		"review_status",
		"proposed_customer",
		"has_multiple_customer_candidates",
		"duplicate_name_siblings",
	],
	filters: [["is_active", "=", 1]],

	formatters: {
		match_status: function (value) {
			const labels = {
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
			return `<span>${frappe.utils.escape_html(labels[value] || value || "")}</span>`;
		},
	},

	get_indicator: function (doc) {
		const colors = {
			"Needs match": "red",
			"Possible duplicates": "yellow",
			"Merge pending": "blue",
			"Ready to accept": "orange",
			Done: "green",
		};
		const status = doc.review_status || "Needs match";
		return [__(status), colors[status] || "gray", `review_status,=,${status}`];
	},

	onload: function (listview) {
		frappe.call({
			method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.is_review_site",
			callback: function (r) {
				if (r.message) {
					add_review_site_actions(listview);
				}
			},
		});
	},
};

function add_review_site_actions(listview) {
	listview.page.add_action_item(__("Accept proposal"), function () {
		listview.call_for_selected_items(
			"ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.bulk_accept_proposal"
		);
	});

	listview.page.add_action_item(__("Assign to Customer..."), function () {
		const dialog = new frappe.ui.Dialog({
			title: __("Assign Customer"),
			fields: [
				{
					fieldname: "customer",
					fieldtype: "Link",
					options: "Customer",
					label: __("Customer"),
					reqd: 1,
				},
			],
			primary_action_label: __("Assign"),
			primary_action: (values) => {
				listview.call_for_selected_items(
					"ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.bulk_assign_customer",
					{ customer: values.customer }
				);
				dialog.hide();
			},
		});
		dialog.show();
	});

	listview.page.add_action_item(__("Export decisions to repo"), function () {
		frappe.call({
			method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.export_decisions",
			freeze: true,
			callback: (r) => {
				if (r.message) {
					frappe.msgprint(
						__("Wrote {0} assignment(s) to {1}", [
							r.message.rows_written,
							r.message.path,
						])
					);
				}
			},
		});
	});

	listview.page.add_action_item(__("Execute pending decisions..."), function () {
		check_merge_conflicts_then_preview(listview);
	});
}

function check_merge_conflicts_then_preview(listview) {
	frappe.call({
		method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.get_merge_conflicts",
		freeze: true,
		callback: function (r) {
			const conflicts = r.message || [];
			if (!conflicts.length) {
				show_execute_preview(listview);
				return;
			}
			show_merge_conflict_dialog(listview, conflicts);
		},
	});
}

function show_merge_conflict_dialog(listview, conflicts) {
	const field_map = [];
	const fields = [];

	conflicts.forEach(function (survivor) {
		fields.push({
			fieldtype: "Section Break",
			label: __("Merging {0} into {1}", [survivor.merges.join(", "), survivor.merge_into]),
		});
		survivor.fields.forEach(function (field) {
			const idx = field_map.length;
			const select_options = field.options.map(function (o, oi) {
				return {
					label: `${frappe.utils.escape_html(o.customer)}: ${frappe.utils.escape_html(
						o.value
					)}`,
					value: `opt::${oi}`,
				};
			});
			select_options.push({ label: __("Enter a different value…"), value: "__custom__" });

			field_map.push({
				merge_into: survivor.merge_into,
				fieldname: field.fieldname,
				options: field.options,
			});

			fields.push({
				fieldname: `sel_${idx}`,
				fieldtype: "Select",
				label: `${field.label} (${field.fieldname})`,
				options: select_options,
				default: select_options.length ? select_options[0].value : undefined,
			});
			fields.push({
				fieldname: `custom_${idx}`,
				fieldtype: "Data",
				label: __("New value"),
				depends_on: `eval:doc.sel_${idx}=='__custom__'`,
				mandatory_depends_on: `eval:doc.sel_${idx}=='__custom__'`,
			});
		});
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Resolve merge conflicts"),
		size: "large",
		fields: fields,
		primary_action_label: __("Save choices"),
		primary_action: function () {
			const values = dialog.get_values(true);
			const resolutions = {};
			field_map.forEach(function (entry, i) {
				const sel_value = values[`sel_${i}`];
				if (!sel_value) return;
				resolutions[entry.merge_into] = resolutions[entry.merge_into] || {};
				if (sel_value === "__custom__") {
					resolutions[entry.merge_into][entry.fieldname] = {
						value: values[`custom_${i}`],
						custom: true,
					};
				} else {
					const opt_index = parseInt(sel_value.replace("opt::", ""), 10);
					resolutions[entry.merge_into][entry.fieldname] = {
						value: entry.options[opt_index].value,
						custom: false,
					};
				}
			});

			frappe.call({
				method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.save_merge_resolutions",
				args: { resolutions: resolutions },
				freeze: true,
				callback: function () {
					dialog.hide();
					show_execute_preview(listview);
				},
			});
		},
		secondary_action_label: __("Skip blocked merges"),
		secondary_action: function () {
			dialog.hide();
			show_execute_preview(listview);
		},
	});

	dialog.show();
}

function show_execute_preview(listview) {
	frappe.call({
		method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.preview_pending_decisions",
		freeze: true,
		callback: function (r) {
			const preview = r.message || {};
			const merges = preview.merges || [];
			const will_merge = merges.filter((m) => m.action === "would_merge");
			const blocked = merges.filter((m) => m.status === "blocked");
			const invalid_assignments = (preview.assignments || []).filter(
				(a) => a.status === "invalid"
			);

			let body = `<p>${__(
				"{0} merge(s) will run, {1} blocked by field conflicts, {2} invalid assignment(s).",
				[will_merge.length, blocked.length, invalid_assignments.length]
			)}</p>`;
			const customer_record_ids = preview.customer_record_ids || [];
			const will_assign_from_record = customer_record_ids.filter(
				(r) => r.action === "assigned"
			);
			const name_mismatches = customer_record_ids.filter(
				(r) => r.action === "name_mismatch"
			);
			body += `<p>${__("{0} assigned from Customer records, {1} skipped (name mismatch).", [
				will_assign_from_record.length,
				name_mismatches.length,
			])}</p>`;

			frappe.confirm(body + __("Run the merges and assignments now?"), function () {
				frappe.call({
					method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.execute_pending_decisions",
					freeze: true,
					callback: function () {
						frappe.msgprint(
							__(
								"Running in the background. You'll see a notification when it's done."
							)
						);
					},
				});
			});
		},
	});
}
