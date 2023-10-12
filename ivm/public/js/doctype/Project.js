frappe.ui.form.on("Project", {
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
    frm.set_query("associated_deployment_location", function () {
      return {
        filters: [["Address", "address_type", "=", "Deployment"]],
      };
    });

    $(document).ready(function () {
      const fieldGroups = {
        input: ['number_of_kiosks', 'opportunity', "po_and_tracking", "associated_deployment_location", "customer"],
        select: ["install_type", "vault_size", "kiosk_options", "kvm_switch_options", "network_options", "countertop_color", "ada_side_table", "kiosk_side_for_table"],
        div: ["expedited_delivery", "enhanced_lockers", "number_of_machines", "number_of_primary_lockers", "number_of_secondary_lockers", "number_of_vaults", "opportunity_term"],
        textarea: ["description", "vault_power_configuration_details", "expedited_delivery_details"]
      };

      Object.keys(fieldGroups).forEach(group => {
        fieldGroups[group].forEach(field => {
          let selector;
          let backgroundColor = '#e1f0f0';

          if (group === 'div' && (field === "expedited_delivery" || field === "enhanced_lockers")) {
            selector = `div[data-fieldname="${field}"] .label-area`;
          } else {
            selector = `${group}[data-fieldname="${field}"]`;
            if (group === 'div' && field !== "expedited_delivery" && field !== "enhanced_lockers") {
              selector = `div[data-fieldname="${field}"] .control-value.like-disabled-input`;
            }
          }

          $(selector).css('background-color', backgroundColor);
        });
      });
    });
    if (frm.doc.__islocal) {
      if (frm.doc.customer) {
        frm.set_value("project_type", "");
        frappe.db.get_doc("Customer", frm.doc.customer).then((r) => {
          if (r.opportunity_name) {
            frm.set_value("opportunity", r.opportunity_name);
          }
        });
      }
      frm.set_value(
        "number_of_lockers",
        (frm.doc.number_of_primary_lockers || 0) +
        (frm.doc.number_of_secondary_lockers || 0)
      );
    }
  },
  customer: function (frm) {
    if (frm.doc.customer) {
      frappe.db.get_doc("Customer", frm.doc.customer).then((r) => {
        if (r.opportunity_name) {
          frm.set_value("opportunity", r.opportunity_name);
        }
      });
    }
  },
  project_type: function (frm) {
    if (frm.doc.connectivity_type) {
      frappe.call({
        method: 'ivm.api.get_connectivity_type_record',
        args: {
          record_name: frm.doc.connectivity_type
        },
        callback: function (r) {
          const message = r.message;
          if (message) {
            if (message.cell_carrier) {
              updateSelectFieldOptions(frm, 'cell_carrier', message.cell_carrier);
            }
          }
        }
      });
    }
  },
  connectivity_type: function (frm) {
    if (frm.doc.connectivity_type) {
      frappe.call({
        method: 'ivm.api.get_connectivity_type_record',
        args: {
          record_name: frm.doc.connectivity_type
        },
        callback: function (r) {
          const message = r.message;
          if (message) {
            if (message.cell_carrier) {
              updateSelectFieldOptions(frm, 'cell_carrier', message.cell_carrier);
            }
          }
        }
      });
    }
  },
  opportunity: function (frm) {
    frappe.db.get_value("Opportunity", frm.doc.opportunity, "*", (response) => {
      var doc = response;
      var fieldsToSet = [
        "number_of_kiosks",
        "enhanced_lockers",
        "expedited_delivery",
        "expedited_delivery_details",
        "install_type",
        "po_and_tracking",
        "vault_size",
        "vault_power_configuration_details",
        "kiosk_options",
        "kvm_switch_options",
        "network_options",
        "countertop_color",
        "ada_side_table",
        "description",
        "number_of_machines",
        "number_of_primary_lockers",
        "number_of_secondary_lockers",
        "number_of_vaults",
        "kiosk_side_for_table",
        "customer",
      ];
      for (var field of fieldsToSet) {
        if (doc[field] !== undefined) {
          frm.set_value(field, doc[field]);
        }
      }
      frm.set_value(
        "number_of_lockers",
        (doc.number_of_primary_lockers || 0) +
        (doc.number_of_secondary_lockers || 0)
      );
      frm.set_value("opportunity_term", doc.sv_term);
      frm.set_value("associated_deployment_location", doc.deployment_address)

      if (doc.customer_name) {
        frappe.db.get_value(
          "Customer",
          { name: doc.customer_name },
          "name",
          function (customer_response) {
            if (customer_response && customer_response.name) {
              frm.set_value("customer", doc.customer_name);
            }
          }
        );
      }
    });
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
          // Set the phone field
          if (contactDetails && contactDetails.phone) {
            frm.set_value(phoneField, contactDetails.phone);
          } else {
            frm.set_value(phoneField, "");
          }
          // Set the email field
          if (contactDetails && contactDetails.email_id) {
            frm.set_value(emailField, contactDetails.email_id);
          } else {
            frm.set_value(emailField, "");
          }
        } else {
          // Handle errors if any
          frappe.msgprint(__("Error fetching contact details."));
          console.error(response.exc);
        }
      },
    });
  } else {
    // Clear fields if contact is not selected
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
      }
      else{
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
      frm.reload_doc()
      var reason = r.message
      if (reason === "Wrap Ready") {
        //show_alert with indicator
        frappe.show_alert({
          message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason} </span> is created`),
          indicator: 'green'
        }, 5);
      }
      else if (reason === "Build Machine") {
        frappe.show_alert({
          message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason} </span> is created`),
          indicator: 'green'
        }, 5);
      }
      else if (reason === "Build Locker") {
        frappe.show_alert({
          message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason} </span> is created`),
          indicator: 'green'
        }, 5);
      }
      else if (reason === "Build Kiosk") {
        frappe.show_alert({
          message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason} </span> is created`),
          indicator: 'green'
        }, 5);
      }
      else if (reason === "Build Vault") {
        frappe.show_alert({
          message: __(`Warehouse Request <b><span style="color: #FF5733;">${reason} </span> is created`),
          indicator: 'green'
        }, 5);
      }
    }
  });
}
