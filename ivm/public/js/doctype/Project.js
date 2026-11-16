const PROJECT_MACHINE_DETAIL_TABLES = [
	"custom_deployment_smartlocker_details",
	"custom_deployment_smartstation_details",
	"custom_deployment_smartsync_details",
	"custom_deployment_smartvault_details",
];

// All machine detail tables that carry a per-row icorp_client_id (includes SmartCenter).
const ICORP_CLIENT_DETAIL_TABLES = {
	custom_deployment_smartstation_details: "Deployment SmartStation Details",
	custom_deployment_smartlocker_details: "Deployment SmartLocker Details",
	custom_deployment_smartsync_details: "Deployment SmartSync Details",
	custom_deployment_smartvault_details: "Deployment SmartVault Details",
	custom_deployment_smartcenter_details: "Deployment SmartCenter Details",
};

// New rows default to the Project's selected iCorp client.
Object.entries(ICORP_CLIENT_DETAIL_TABLES).forEach(([table, child_doctype]) => {
	frappe.ui.form.on(child_doctype, {
		[`${table}_add`]: function (frm, cdt, cdn) {
			if (frm.doc.icorp_client_id) {
				frappe.model.set_value(cdt, cdn, "icorp_client_id", frm.doc.icorp_client_id);
			}
		},
	});
});

frappe.ui.form.on("Deployment SmartLocker Details", {
	form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn),
});

frappe.ui.form.on("Deployment SmartSync Details", {
	form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn),
});

frappe.ui.form.on("Deployment SmartVault Details", {
	form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn),
});

frappe.ui.form.on("Project", {
	refresh: function (frm) {
		frm._prev_status = frm.doc.status;
		frm._prev_icorp_client_id = frm.doc.icorp_client_id;
		setupMachineDetailGrids(frm, PROJECT_MACHINE_DETAIL_TABLES);
		const smartstation_grid = frm.fields_dict.custom_deployment_smartstation_details.grid;
		smartstation_grid.get_field("card_reader_type").get_query = () => ({
			filters: { enabled: 1 },
		});
		refresh_deployable_clients(frm);
	},

	onload: function (frm) {
		frm.set_query("shipping_address", function () {
			return {
				filters: [["Address", "address_type", "=", "Shipping"]],
			};
		});

		frm.set_query("icorp_client_id", () => ({
			query: "ivm.deployments.services.deployment_clients.deployable_client_query",
			filters: { customer: frm.doc.customer },
		}));

		Object.keys(ICORP_CLIENT_DETAIL_TABLES).forEach((table) => {
			const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
			if (grid) {
				grid.get_field("icorp_client_id").get_query = () => ({
					query: "ivm.deployments.services.deployment_clients.deployable_client_query",
					filters: { customer: frm.doc.customer, own_only: 1 },
				});
			}
		});
	},

	connectivity_type: (frm) => loadConnectivityTypeOptions(frm),

	customer: function (frm) {
		if (!frm._swapping) {
			refresh_deployable_clients(frm);
		}
	},

	icorp_client_id: function (frm) {
		sync_row_icorp_clients(frm, frm._prev_icorp_client_id, frm.doc.icorp_client_id);
		frm._prev_icorp_client_id = frm.doc.icorp_client_id;

		const chosen = (frm._deployable_clients || []).find(
			(c) => c.name === frm.doc.icorp_client_id
		);
		if (!chosen) return;

		if (chosen.group === "managed") {
			const previous_customer = frm.doc.customer;
			frm._swapping = true;
			frm.set_value("customer", chosen.customer).then(() => {
				frm.set_value("partner_customer", previous_customer).then(() => {
					frm.set_value("partner_icorp_client_id", chosen.partner_icorp_client_id || "");
					frappe.show_alert(
						{
							message: __("Client changed to {0}; {1} set as Partner.", [
								chosen.customer,
								previous_customer,
							]),
							indicator: "orange",
						},
						7
					);
					frm._swapping = false;
					refresh_deployable_clients(frm);
				});
			});
		} else {
			frm.set_value("partner_customer", chosen.partner_customer || "");
			frm.set_value("partner_icorp_client_id", chosen.partner_icorp_client_id || "");
		}
	},

	customs_contact: function (frm) {
		fetchContactDetails(
			frm,
			"customs_contact",
			"customs_contact_phone",
			"customs_contact_email"
		);
	},

	install_contact: function (frm) {
		fetchContactDetails(
			frm,
			"install_contact",
			"install_contact_phone",
			"install_contact_email"
		);
	},

	delivery_contact: function (frm) {
		fetchContactDetails(
			frm,
			"delivery_contact",
			"delivery_contact_phone",
			"delivery_contact_email"
		);
	},

	contact_name: function (frm) {
		fetchContactDetails(frm, "contact_name", "contact_phone", "contact_email");
	},

	status: function (frm) {
		if (frm.doc.status === "Ready to Ship") {
			if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
				frappe.msgprint(
					__(
						"Please fill in both Contacts Completed Date and Delivery Contact before moving to Ready to Ship."
					)
				);
				frm.set_value("status", frm._prev_status || "");
			}
		}
		frm._prev_status = frm.doc.status;
	},

	before_save: function (frm) {
		if (frm.doc.status === "Ready to Ship") {
			if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
				frappe.throw(
					__(
						"Please fill in both Contacts Completed Date and Delivery Contact before saving."
					)
				);
			}
		}
		validateUniqueMachineNames(frm, PROJECT_MACHINE_DETAIL_TABLES);
	},

	custom_generate_smartstation_build_requests: function (frm) {
		if (
			!frm.doc.planogram_approved_date ||
			!frm.doc.custom_planogram_approved_by ||
			!frm.doc.custom_label_file_created
		) {
			frappe.msgprint(
				__(
					"Planogram must be approved and Label File must be created before generating SmartStation Build requests."
				)
			);
			return;
		}
		_generate_build_requests(frm, "custom_deployment_smartstation_details", "SmartStation");
	},

	custom_generate_smartlocker_build_requests: function (frm) {
		if (
			!frm.doc.locker_configuration_approved_date ||
			!frm.doc.custom_locker_configuration_approved_by
		) {
			frappe.msgprint(
				__(
					"Locker Configuration must be approved before generating SmartLocker Build requests."
				)
			);
			return;
		}
		_generate_build_requests(frm, "custom_deployment_smartlocker_details", "SmartLocker");
	},

	custom_generate_smartsync_build_requests: function (frm) {
		if (
			!frm.doc.locker_configuration_approved_date ||
			!frm.doc.custom_locker_configuration_approved_by
		) {
			frappe.msgprint(
				__(
					"Locker Configuration must be approved before generating SmartSync Build requests."
				)
			);
			return;
		}
		_generate_build_requests(frm, "custom_deployment_smartsync_details", "SmartSync");
	},

	custom_generate_smartvault_build_requests: function (frm) {
		if (
			!frm.doc.vault_configuration_approved_date ||
			!frm.doc.custom_vault_configuration_approved_by
		) {
			frappe.msgprint(
				__(
					"Vault Configuration must be approved before generating SmartVault Build requests."
				)
			);
			return;
		}
		_generate_build_requests(frm, "custom_deployment_smartvault_details", "SmartVault");
	},

	custom_generate_smartcenter_build_requests: function (frm) {
		if (
			!frm.doc.kiosk_configuration_approved_date ||
			!frm.doc.custom_kiosk_configuration_approved_by
		) {
			frappe.msgprint(
				__(
					"Kiosk Configuration must be approved before generating SmartCenter Build requests."
				)
			);
			return;
		}
		_generate_build_requests(frm, "custom_deployment_smartcenter_details", "SmartCenter");
	},
});

function loadConnectivityTypeOptions(frm) {
	if (!frm.doc.connectivity_type) return;
	frappe.call({
		method: "ivm.api.get_connectivity_type_record",
		args: { record_name: frm.doc.connectivity_type },
		callback: function (r) {
			if (r.message && r.message.cell_carrier) {
				updateSelectFieldOptions(frm, "cell_carrier", r.message.cell_carrier);
			}
		},
	});
}

function fetchContactDetails(frm, contactField, phoneField, emailField) {
	var contact = frm.doc[contactField];
	if (contact) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Contact",
				filters: {
					name: contact,
				},
				fieldname: ["email_id", "phone"],
			},
			callback: function (response) {
				if (!response.exc) {
					var contactDetails = response.message;
					if (contactDetails && contactDetails.phone) {
						frm.set_value(phoneField, contactDetails.phone);
					} else {
						frm.set_value(phoneField, "");
					}
					if (contactDetails && contactDetails.email_id) {
						frm.set_value(emailField, contactDetails.email_id);
					} else {
						frm.set_value(emailField, "");
					}
				} else {
					frappe.msgprint(__("Error fetching contact details."));
					console.error(response.exc);
				}
			},
		});
	} else {
		frm.set_value(phoneField, "");
		frm.set_value(emailField, "");
	}
}

function sync_row_icorp_clients(frm, previous, current) {
	// Rows that are blank or still hold the previous Project client follow the
	// new Project client; rows manually set to another client are left alone.
	Object.keys(ICORP_CLIENT_DETAIL_TABLES).forEach((table) => {
		(frm.doc[table] || []).forEach((row) => {
			if (!row.icorp_client_id || (previous && row.icorp_client_id === previous)) {
				frappe.model.set_value(row.doctype, row.name, "icorp_client_id", current || "");
			}
		});
		if (frm.fields_dict[table]) {
			frm.refresh_field(table);
		}
	});
}

function refresh_deployable_clients(frm) {
	if (frm.doc.project_type !== "Deployment") return;

	if (!frm.doc.customer) {
		frm.set_df_property("icorp_client_id", "hidden", 1);
		frm.dashboard.clear_headline();
		if (!frm.is_new()) {
			frm.dashboard.set_headline_alert(
				`<div class="alert alert-warning" style="margin-bottom: 0;">${__(
					"This deployment has no customer yet. Set the Customer to continue."
				)}</div>`
			);
		}
		return;
	}

	frappe.call({
		method: "ivm.deployments.services.deployment_clients.get_deployable_clients",
		args: { customer: frm.doc.customer },
		callback: function (r) {
			const clients = r.message || [];
			frm._deployable_clients = clients;
			const own = clients.filter((c) => c.group === "own");
			const managed = clients.filter((c) => c.group === "managed");

			frm.dashboard.clear_headline();

			if (own.length === 0 && managed.length === 0) {
				frm.set_df_property("icorp_client_id", "hidden", 1);
				frappe.call({
					method: "ivm.deployments.services.deployment_clients.get_customer_client_summary",
					args: { customer: frm.doc.customer },
					callback: function (s) {
						// Only show if the Customer still has no deployable client and is still selected.
						if (!frm.doc.customer || (frm._deployable_clients || []).length) return;
						const summary = s.message || { active: [], inactive: [] };
						const esc = frappe.utils.escape_html;
						const customer_href = frappe.utils.get_form_link(
							"Customer",
							frm.doc.customer
						);
						const customer_link = `<a href="${esc(customer_href)}">${esc(
							frm.doc.customer
						)}</a>`;
						const tab_href = esc(`${customer_href}#icorp_tab`);
						const tab_link = `<a href="${tab_href}">${__("Customer's iCorp tab")}</a>`;
						let text;
						if (summary.inactive.length && !summary.active.length) {
							text = __(
								"{0} only has inactive iCorp clients ({1}). Reactivate one in iCorp (the daily sync will pick it up), or add one on the {2}, then pick it here.",
								[customer_link, esc(summary.inactive.join(", ")), tab_link]
							);
						} else {
							text = __(
								"{0} has no iCorp client yet. Add one on the {1}, then pick it here.",
								[customer_link, tab_link]
							);
						}
						frm.dashboard.set_headline_alert(
							`<div class="alert alert-warning" style="margin-bottom: 0;">${text}</div>`
						);
					},
				});
			} else {
				frm.set_df_property("icorp_client_id", "hidden", 0);

				if (own.length === 1 && managed.length === 0) {
					if (!frm.doc.icorp_client_id) {
						frm.set_value("icorp_client_id", own[0].name);
					}
					frm.set_df_property("icorp_client_id", "read_only", 1);
				} else {
					frm.set_df_property("icorp_client_id", "read_only", 0);
				}

				const valid_names = clients.map((c) => c.name);
				if (
					frm._clients_loaded_once &&
					frm.doc.icorp_client_id &&
					!valid_names.includes(frm.doc.icorp_client_id)
				) {
					frm.set_value("icorp_client_id", "");
				}
			}

			frm.refresh_field("icorp_client_id");

			Object.keys(ICORP_CLIENT_DETAIL_TABLES).forEach((table) => {
				const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
				if (grid) {
					grid.update_docfield_property(
						"icorp_client_id",
						"hidden",
						own.length > 1 ? 0 : 1
					);
					grid.refresh();
				}
			});

			frm._clients_loaded_once = true;
		},
	});
}

function updateSelectFieldOptions(frm, fieldname, optionsData) {
	const optionsList = optionsData.map((option) => option[fieldname]);
	frm.set_df_property(fieldname, "options", optionsList);
	frm.refresh_field(fieldname);
}

function _generate_build_requests(frm, detail_table, label) {
	const rows = frm.doc[detail_table] || [];
	if (!rows.length) {
		frappe.msgprint(__(`No ${label} rows found on this deployment.`));
		return;
	}

	frappe.call({
		method: "ivm.warehouse.services.warehouse_request.create_build_requests_from_detail_rows",
		args: {
			project_name: frm.doc.name,
			detail_table: detail_table,
		},
		freeze: true,
		freeze_message: __(`Creating ${label} Build Requests...`),
		callback: function (r) {
			if (!r.exc && r.message) {
				const { created, skipped, failed } = r.message;

				if (failed && failed.length) {
					frappe.msgprint({
						title: __("Could not generate build requests"),
						message:
							__(
								"The following machines were not found in iCorp. " +
									"Please ensure the records are created before generating build requests:"
							) +
							"<ul>" +
							failed.map((n) => `<li><strong>${n}</strong></li>`).join("") +
							"</ul>",
						indicator: "red",
					});
					return;
				}

				frm.reload_doc();
				if (created.length) {
					frappe.show_alert(
						{
							message:
								__(`Created ${created.length} ${label} Build Request(s).`) +
								(skipped
									? __(" " + skipped + " already existed and were skipped.")
									: ""),
							indicator: "green",
						},
						7
					);
				} else {
					frappe.msgprint({
						title: __("Already Created"),
						message: __(`All ${label} Build Requests have already been created.`),
						indicator: "orange",
					});
				}
			}
		},
	});
}
