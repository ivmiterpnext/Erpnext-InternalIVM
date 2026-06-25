const PROJECT_MACHINE_DETAIL_TABLES = [
  'custom_deployment_smartlocker_details',
  'custom_deployment_smartstation_details',
  'custom_deployment_smartsync_details',
  'custom_deployment_smartvault_details'
];

frappe.ui.form.on('Deployment SmartLocker Details', {
  form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn)
});

frappe.ui.form.on('Deployment SmartSync Details', {
  form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn)
});

frappe.ui.form.on('Deployment SmartVault Details', {
  form_render: (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn)
});

frappe.ui.form.on("Project", {
  refresh: function (frm) {
    frm._prev_status = frm.doc.status;
    setupMachineDetailGrids(frm, PROJECT_MACHINE_DETAIL_TABLES);
  },

  onload: function (frm) {
    frm.set_query("shipping_address", function () {
      return {
        filters: [["Address", "address_type", "=", "Shipping"]],
      };
    });
  },

  connectivity_type: (frm) => loadConnectivityTypeOptions(frm),

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

  status: function(frm) {
    if (frm.doc.status === 'Ready to Ship') {
      if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
        frappe.msgprint(__('Please fill in both Contacts Completed Date and Delivery Contact before moving to Ready to Ship.'));
        frm.set_value('status', frm._prev_status || '');
      }
    }
    frm._prev_status = frm.doc.status;
  },

  before_save: function(frm) {
    if (frm.doc.status === 'Ready to Ship') {
      if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
        frappe.throw(__('Please fill in both Contacts Completed Date and Delivery Contact before saving.'));
      }
    }
    validateUniqueMachineNames(frm, PROJECT_MACHINE_DETAIL_TABLES);
  },

  custom_generate_smartstation_build_requests: function(frm) {
    if (!frm.doc.planogram_approved_date || !frm.doc.custom_planogram_approved_by || !frm.doc.custom_label_file_created) {
      frappe.msgprint(__('Planogram must be approved and Label File must be created before generating SmartStation Build requests.'));
      return;
    }
    _generate_build_requests(frm, 'custom_deployment_smartstation_details', 'SmartStation');
  },

  custom_generate_smartlocker_build_requests: function(frm) {
    if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
      frappe.msgprint(__('Locker Configuration must be approved before generating SmartLocker Build requests.'));
      return;
    }
    _generate_build_requests(frm, 'custom_deployment_smartlocker_details', 'SmartLocker');
  },

  custom_generate_smartsync_build_requests: function(frm) {
    if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
      frappe.msgprint(__('Locker Configuration must be approved before generating SmartSync Build requests.'));
      return;
    }
    _generate_build_requests(frm, 'custom_deployment_smartsync_details', 'SmartSync');
  },

  custom_generate_smartvault_build_requests: function(frm) {
    if (!frm.doc.vault_configuration_approved_date || !frm.doc.custom_vault_configuration_approved_by) {
      frappe.msgprint(__('Vault Configuration must be approved before generating SmartVault Build requests.'));
      return;
    }
    _generate_build_requests(frm, 'custom_deployment_smartvault_details', 'SmartVault');
  },

  custom_generate_smartcenter_build_requests: function(frm) {
    if (!frm.doc.kiosk_configuration_approved_date || !frm.doc.custom_kiosk_configuration_approved_by) {
      frappe.msgprint(__('Kiosk Configuration must be approved before generating SmartCenter Build requests.'));
      return;
    }
    _generate_build_requests(frm, 'custom_deployment_smartcenter_details', 'SmartCenter');
  },
  
});

function loadConnectivityTypeOptions(frm) {
  if (!frm.doc.connectivity_type) return;
  frappe.call({
    method: 'ivm.api.get_connectivity_type_record',
    args: { record_name: frm.doc.connectivity_type },
    callback: function (r) {
      if (r.message && r.message.cell_carrier) {
        updateSelectFieldOptions(frm, 'cell_carrier', r.message.cell_carrier);
      }
    }
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

function updateSelectFieldOptions(frm, fieldname, optionsData) {
  const optionsList = optionsData.map(option => option[fieldname]);
  frm.set_df_property(fieldname, 'options', optionsList);
  frm.refresh_field(fieldname);
}

function _generate_build_requests(frm, detail_table, label) {
  const rows = frm.doc[detail_table] || [];
  if (!rows.length) {
    frappe.msgprint(__(`No ${label} rows found on this deployment.`));
    return;
  }

  frappe.call({
    method: 'ivm.warehouse.services.warehouse_request.create_build_requests_from_detail_rows',
    args: {
      project_name: frm.doc.name,
      detail_table: detail_table,
    },
    freeze: true,
    freeze_message: __(`Creating ${label} Build Requests...`),
    callback: function(r) {
      if (!r.exc && r.message) {
        const { created, skipped, failed } = r.message;

        if (failed && failed.length) {
          frappe.msgprint({
            title: __('Could not generate build requests'),
            message: __(
              'The following machines were not found in iCorp. ' +
              'Please ensure the records are created before generating build requests:'
            ) + '<ul>' + failed.map(n => `<li><strong>${n}</strong></li>`).join('') + '</ul>',
            indicator: 'red'
          });
          return;
        }

        frm.reload_doc();
        if (created.length) {
          frappe.show_alert({
            message: __(`Created ${created.length} ${label} Build Request(s).`) +
              (skipped ? __(' ' + skipped + ' already existed and were skipped.') : ''),
            indicator: 'green'
          }, 7);
        } else {
          frappe.msgprint({
            title: __('Already Created'),
            message: __(`All ${label} Build Requests have already been created.`),
            indicator: 'orange'
          });
        }
      }
    }
  });
}
