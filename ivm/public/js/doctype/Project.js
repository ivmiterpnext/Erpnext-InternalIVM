const SMART_DETAIL_TABLES = [
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
    setupSmartDetailGrids(frm);
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
    frm.set_query("associated_deployment_location", function () {
      return {
        filters: [["Address", "address_type", "=", "Deployment"]],
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

function setupSmartDetailGrids(frm) {
  SMART_DETAIL_TABLES.forEach(fieldname => {
    const grid = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].grid;
    if (!grid) return;
    grid.allow_on_grid_editing = () => false;
    grid.wrapper.addClass('ivm-smart-detail-grid');
  });
}

function injectBinsEditor(frm, cdt, cdn) {
  const $wrapper = cur_frm?.cur_grid?.grid_form?.wrapper;
  if (!$wrapper || $wrapper.find('.ivm-bins-injected').length) return;

  const $container = $('<div class="ivm-bins-injected" style="padding: 10px 15px 5px;"></div>');
  $wrapper.find('[data-fieldname="bins_data"]').hide().after($container);

  const row = frappe.get_doc(cdt, cdn);
  let existing = [];
  try { existing = row.bins_data ? JSON.parse(row.bins_data) : []; } catch(e) {}

  $container.html(`
    <table class="table table-bordered table-sm mb-2">
      <thead><tr>
        <th style="width:90px">Type</th>
        <th style="width:70px">#</th>
        <th style="width:80px">Size (Inches)</th>
        <th style="width:40px"></th>
      </tr></thead>
      <tbody class="ivm-bins-body"></tbody>
    </table>
    <button class="btn btn-xs btn-secondary ivm-add-bin">+ Add Row</button>
    <span class="ivm-bins-warning text-danger small ml-2" style="display:none;"></span>
  `);

  function saveBins() {
    const bins = [];
    const seen = new Set();
    let duplicate = null;
    $container.find('.ivm-bin-row').each(function() {
      const $r = $(this);
      const bin_type = $r.find('.ivm-bin-type').val();
      const entry = { bin_type, bin_size: $r.find('.ivm-bin-size').val() };
      if (bin_type === 'Bin') {
        const num = $r.find('.ivm-bin-number').val();
        if (num && seen.has(num)) duplicate = num;
        if (num) seen.add(num);
        entry.bin_number = num;
      }
      bins.push(entry);
    });
    const $warning = $container.find('.ivm-bins-warning');
    if (duplicate) {
      $warning.text(`Bin #${duplicate} is duplicated.`).show();
    } else {
      $warning.hide();
      frappe.model.set_value(cdt, cdn, 'bins_data', JSON.stringify(bins));
    }
  }

  function nextBinNumber() {
    let last = null;
    $container.find('.ivm-bin-row').each(function() {
      if ($(this).find('.ivm-bin-type').val() === 'Bin') {
        const n = parseInt($(this).find('.ivm-bin-number').val());
        if (!isNaN(n)) last = n;
      }
    });
    return last !== null ? String(last + 1) : '';
  }

  function lastRowSize() {
    const $rows = $container.find('.ivm-bin-row');
    return $rows.length ? $rows.last().find('.ivm-bin-size').val() : '4';
  }

  function setNumberState($row, isBin) {
    const $input = $row.find('.ivm-bin-number');
    if (isBin) {
      $input.prop('disabled', false).val($input.data('saved') || '').css('color', '');
    } else {
      $input.data('saved', $input.val()).prop('disabled', true).val('N/A').css('color', '#aaa');
    }
  }

  function addRow(bin) {
    const isNew = !bin;
    bin = bin || {};
    const type = bin.bin_type || 'Bin';
    const $row = $(`
      <tr class="ivm-bin-row">
        <td><select class="form-control form-control-sm ivm-bin-type">
          <option value="Bin">Bin</option>
          <option value="PWR">PWR</option>
        </select></td>
        <td><input type="text" inputmode="numeric" class="form-control form-control-sm ivm-bin-number" /></td>
        <td><select class="form-control form-control-sm ivm-bin-size">
          <option>4</option><option>8</option><option>12</option>
        </select></td>
        <td class="ivm-remove-bin-td"><button class="btn btn-xs btn-danger ivm-remove-bin">&times;</button></td>
      </tr>
    `);
    $row.find('.ivm-bin-type').val(type);
    $row.find('.ivm-bin-size').val(isNew ? lastRowSize() : (bin.bin_size || '4'));
    const binNum = isNew && type === 'Bin' ? nextBinNumber() : (bin.bin_number || '');
    $row.find('.ivm-bin-number').val(binNum).data('saved', String(binNum));
    setNumberState($row, type === 'Bin');

    $row.find('.ivm-bin-type').on('change', function() {
      setNumberState($row, $(this).val() === 'Bin');
      saveBins();
    });
    $row.find('.ivm-bin-number, .ivm-bin-size').on('change', saveBins);
    $row.find('.ivm-remove-bin').on('click', () => { $row.remove(); saveBins(); });
    $container.find('.ivm-bins-body').append($row);
  }

  existing.forEach(b => addRow(b));
  if (!existing.length) addRow();
  $container.find('.ivm-add-bin').on('click', () => { addRow(); saveBins(); });
}

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
