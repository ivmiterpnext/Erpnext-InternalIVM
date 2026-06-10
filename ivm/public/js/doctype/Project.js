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
    frm.set_query("billing_address", function () {
      return {
        filters: [["Address", "address_type", "=", "Billing"]],
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
    // TODO: Add logic for generating SmartStation Build Requests here
    frappe.msgprint(__('SmartStation Build Requests logic not yet implemented.'));
  },

  custom_generate_smartsync_build_requests: function(frm) {
    if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
      frappe.msgprint(__('Locker Configuration must be approved before generating SmartSync Build requests.'));
      return;
    }
    // TODO: Add logic for generating SmartSync Build Requests here
    frappe.msgprint(__('SmartSync Build Requests logic not yet implemented.'));
  },

  custom_generate_smartlocker_build_requests: function(frm) {
    if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
      frappe.msgprint(__('Locker Configuration must be approved before generating SmartLocker Build requests.'));
      return;
    }
    // TODO: Add logic for generating SmartLocker Build Requests here
    frappe.msgprint(__('SmartLocker Build Requests logic not yet implemented.'));
  },

  custom_generate_smartvault_build_requests: function(frm) {
    if (!frm.doc.vault_configuration_approved_date || !frm.doc.custom_vault_configuration_approved_by) {
      frappe.msgprint(__('Vault Configuration must be approved before generating SmartVault Build requests.'));
      return;
    }
    // TODO: Add logic for generating SmartVault Build Requests here
    frappe.msgprint(__('SmartVault Build Requests logic not yet implemented.'));
  },

  custom_generate_smartcenter_build_requests: function(frm) {
    if (!frm.doc.kiosk_configuration_approved_date || !frm.doc.custom_kiosk_configuration_approved_by) {
      frappe.msgprint(__('Kiosk Configuration must be approved before generating SmartCenter Build requests.'));
      return;
    }
    // TODO: Add logic for generating SmartCenter Build Requests here
    frappe.msgprint(__('SmartCenter Build Requests logic not yet implemented.'));
  },
  
  after_save(frm) {
    if (frm.doc.graphic_design_approved_date) {
      show_Dialog('Wrap Ready', frm);
    }
    if (frm.doc.planogram_approved_date) {
      createWarehouseRequest('Build Machine', null, frm);
    }
    if (frm.doc.locker_configuration_approved_date) {
      createWarehouseRequest('Build Locker', null, frm);
    }
    if (frm.doc.kiosk_configuration_approved_date) {
      createWarehouseRequest('Build Kiosk', null, frm);
    }
    if (frm.doc.vault_configuration_approved_date) {
      createWarehouseRequest('Build Vault', null, frm);
    }
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

function show_Dialog(reason, frm) {
  const dialog = new frappe.ui.Dialog({
    title: 'Add Attachments',
    fields: [
      {
        label: 'Do you want to add attachments?',
        fieldname: 'add_attachments',
        fieldtype: 'Select',
        options: 'Yes\nNo',
        default: 'No',
      },
      {
        fieldname: 'attach_files',
        fieldtype: 'Attach',
        depends_on: 'eval:doc.add_attachments=="Yes"',
      },
    ],
    primary_action_label: 'Submit',
    primary_action(values) {
      const addAttachments = values.attach_files;
      if (addAttachments) {
        createWarehouseRequest(reason, addAttachments, frm);
      } else {
        createWarehouseRequest(reason, null, frm);
      }
      dialog.hide();
    },
  });

  dialog.show();
}

function createWarehouseRequest(reason, attachedFiles, frm) {
  const doc = frm.doc;

  frappe.call({
    method: 'ivm.api.create_warehouse_request',
    args: {
      doc: doc,
      reason: reason,
      attached_files: attachedFiles,
    },
    callback: function (r) {
      frm.reload_doc();
      frappe.show_alert({
        message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason}</span> is created`),
        indicator: 'green'
      }, 5);
    }
  });
}
