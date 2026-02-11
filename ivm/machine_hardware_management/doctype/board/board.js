// Copyright (c) 2025, Dev and contributors
// For license information, please see license.txt

frappe.ui.form.on('Board', {
    onload: function(frm) {
        // Offline Sales Mode select setup
        frm.offline_sales_mode_code_to_desc = {
            "D": "Disabled",
            "A": "All Accounts",
            "S": "Stored Accounts Only"
        };
        frm.offline_sales_mode_desc_to_code = {
            "Disabled": "D",
            "All Accounts": "A",
            "Stored Accounts Only": "S"
        };
        let descriptions = ["", "Disabled", "All Accounts", "Stored Accounts Only"];
        frm.set_df_property('offline_sales_mode_description', 'options', descriptions.join('\n'));

        if (frm.doc.offline_sales_mode && frm.offline_sales_mode_code_to_desc[frm.doc.offline_sales_mode]) {
            frm.set_value('offline_sales_mode_description', frm.offline_sales_mode_code_to_desc[frm.doc.offline_sales_mode]);
        }

        // RFID Target Number Base select setup
        frappe.call({
            method: "ivm.machine_hardware_management.doctype.board.board.get_rfid_target_number_base_types",
            callback: function(r) {
                if (r.message) {
                    frm.rfid_target_base_code_to_desc = {};
                    frm.rfid_target_base_desc_to_code = {};
                    let descriptions = [];
                    r.message.forEach(item => {
                        frm.rfid_target_base_code_to_desc[item.code] = item.description;
                        frm.rfid_target_base_desc_to_code[item.description] = item.code;
                        descriptions.push(item.description);
                    });
                    let options_str = [''].concat(descriptions).join('\n');
                    [
                        'primary_rfid_target_number_base_description',
                        'secondary_rfid_target_number_base_description',
                        'setting3_rfid_target_number_base_description',
                        'setting4_rfid_target_number_base_description',
                        'setting5_rfid_target_number_base_description'
                    ].forEach(field => frm.set_df_property(field, 'options', options_str));

                    if (frm.doc.primary_rfid_target_number_base_code && frm.rfid_target_base_code_to_desc[frm.doc.primary_rfid_target_number_base_code]) {
                        frm.set_value('primary_rfid_target_number_base_description', frm.rfid_target_base_code_to_desc[frm.doc.primary_rfid_target_number_base_code]);
                    }
                    if (frm.doc.secondary_rfid_target_number_base_code && frm.rfid_target_base_code_to_desc[frm.doc.secondary_rfid_target_number_base_code]) {
                        frm.set_value('secondary_rfid_target_number_base_description', frm.rfid_target_base_code_to_desc[frm.doc.secondary_rfid_target_number_base_code]);
                    }
                    if (frm.doc.setting3_rfid_target_number_base_code && frm.rfid_target_base_code_to_desc[frm.doc.setting3_rfid_target_number_base_code]) {
                        frm.set_value('setting3_rfid_target_number_base_description', frm.rfid_target_base_code_to_desc[frm.doc.setting3_rfid_target_number_base_code]);
                    }
                    if (frm.doc.setting4_rfid_target_number_base_code && frm.rfid_target_base_code_to_desc[frm.doc.setting4_rfid_target_number_base_code]) {
                        frm.set_value('setting4_rfid_target_number_base_description', frm.rfid_target_base_code_to_desc[frm.doc.setting4_rfid_target_number_base_code]);
                    }
                    if (frm.doc.setting5_rfid_target_number_base_code && frm.rfid_target_base_code_to_desc[frm.doc.setting5_rfid_target_number_base_code]) {
                        frm.set_value('setting5_rfid_target_number_base_description', frm.rfid_target_base_code_to_desc[frm.doc.setting5_rfid_target_number_base_code]);
                    }
                }
            }
        });

        // Manufacturer related logic
        if (!frm.doc.board_manufacturer_id) {
            frm.set_value('board_manufacturer_id', 'Waiting for PROSE Number...');
        }
        frm.set_df_property('board_manufacturer_id', 'description', 'Automatically set based on PROSE');

        frm.set_query('board_firmware_id', function() {
            return {
                filters: {
                    board_manufacturer_id: frm.doc.board_manufacturer_id
                }
            };
        });

        toggleRfidSections(frm);
    },

    offline_sales_mode_description: function(frm) {
        if (frm.offline_sales_mode_desc_to_code && frm.doc.offline_sales_mode_description in frm.offline_sales_mode_desc_to_code) {
            frm.set_value('offline_sales_mode', frm.offline_sales_mode_desc_to_code[frm.doc.offline_sales_mode_description]);
        } else {
            frm.set_value('offline_sales_mode', '');
        }
    },
    
    primary_rfid_target_number_base_description: function(frm) {
        if (frm.rfid_target_base_desc_to_code && frm.doc.primary_rfid_target_number_base_description in frm.rfid_target_base_desc_to_code) {
            frm.set_value('primary_target_number_base_code', frm.rfid_target_base_desc_to_code[frm.doc.primary_rfid_target_number_base_description]);
        } else {
            frm.set_value('primary_target_number_base_code', '');
        }
    },

    secondary_rfid_target_number_base_description: function(frm) {
        if (frm.rfid_target_base_desc_to_code && frm.doc.secondary_rfid_target_number_base_description in frm.rfid_target_base_desc_to_code) {
            frm.set_value('secondary_target_number_base_code', frm.rfid_target_base_desc_to_code[frm.doc.secondary_rfid_target_number_base_description]);
        } else {
            frm.set_value('secondary_target_number_base_code', '');
        }
    },

    setting3_rfid_target_number_base_description: function(frm) {
        if (frm.rfid_target_base_desc_to_code && frm.doc.setting3_rfid_target_number_base_description in frm.rfid_target_base_desc_to_code) {
            frm.set_value('setting3_target_number_base_code', frm.rfid_target_base_desc_to_code[frm.doc.setting3_rfid_target_number_base_description]);
        } else {
            frm.set_value('setting3_target_number_base_code', '');
        }
    },

    setting4_rfid_target_number_base_description: function(frm) {
        if (frm.rfid_target_base_desc_to_code && frm.doc.setting4_rfid_target_number_base_description in frm.rfid_target_base_desc_to_code) {
            frm.set_value('setting4_target_number_base_code', frm.rfid_target_base_desc_to_code[frm.doc.setting4_rfid_target_number_base_description]);
        } else {
            frm.set_value('setting4_target_number_base_code', '');
        }
    },
    
    setting5_rfid_target_number_base_description: function(frm) {
        if (frm.rfid_target_base_desc_to_code && frm.doc.setting5_rfid_target_number_base_description in frm.rfid_target_base_desc_to_code) {
            frm.set_value('setting5_target_number_base_code', frm.rfid_target_base_desc_to_code[frm.doc.setting5_rfid_target_number_base_description]);
        } else {
            frm.set_value('setting5_target_number_base_code', '');
        }
    },

    onload_post_render: function(frm) {
        const fieldname = 'effective_date';
        if (!frm.doc[fieldname]) {
            const now = frappe.datetime.now_datetime();
            const nowJSDate = frappe.datetime.str_to_obj(now);
            frm.fields_dict[fieldname].datepicker.update({
                minDate: nowJSDate
            });
        }
    },

    refresh: function(frm) {
        toggleRfidSections(frm);
        frm.toggle_display('update_flags_section', !frm.is_new());
    },

    has_rfid_configuration: function(frm) {
        toggleRfidSections(frm);
    },

    board_manufacturer_id: function(frm) {
        applyBoardManufacturerTypeRules(frm);
        toggleRfidSections(frm);
    },

    board_firmware_version: function(frm) {
        frm.set_value('board_firmware_id', frm.doc.board_firmware_version || '');
    },

    is_update_firmware: function(frm) {
        onFirmwareCheckboxChange(frm);
    },

    serial_number: function(frm) {
        if (frm.doc.serial_number) {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.board.board.get_manufacturer_by_serial_number",
                args: { board_serial_number: frm.doc.serial_number },
                callback: function(r) {
                    if (r.message && r.message.id) {
                        frm.set_value('board_manufacturer_id', r.message.id);
                    } else {
                        frm.set_value('board_manufacturer_id', 'Invalid PROSE Number');
                    }
                    toggleRfidSections(frm);
                }
            });
        } else {
            frm.set_value('board_manufacturer_id', 'Invalid PROSE Number');
            toggleRfidSections(frm);
        }
    }
});

// Helper functions
function toggleRfidSections(frm) {
    frm.toggle_display('rfid_settings_1_section', frm.doc.has_rfid_configuration === 1);
    frm.toggle_display('rfid_settings_2_section', frm.doc.has_rfid_configuration === 1);
    frm.toggle_display('rfid_settings_3_section', frm.doc.has_rfid_configuration === 1);
    frm.toggle_display('rfid_settings_4_section', frm.doc.has_rfid_configuration === 1);
    frm.toggle_display('rfid_settings_5_section', frm.doc.has_rfid_configuration === 1);
}

function setVisibleFields(frm) {
    if (frm.doc.board_manufacturer_id) {
        frappe.db.get_value('Board Manufacturer', frm.doc.board_manufacturer_id, 'manufacturer_name', function(r) {
            let manufacturer_name = r && r.manufacturer_name ? r.manufacturer_name : '';
            frm.toggle_display('locker_motor_section', manufacturer_name === "VendNovation");
            toggleRfidSections(frm);
            frm.toggle_display('board_type_code', manufacturer_name === "VendNovation");
            frm.toggle_display('program_type_code', manufacturer_name === "VendNovation");
            frm.toggle_display('offline_vend_storage', manufacturer_name !== "VendNovation");
            frm.toggle_display('keypad_id_entry', manufacturer_name !== "VendNovation");
        });
    } else {
        frm.toggle_display('locker_motor_section', false);
        toggleRfidSections(frm);
        frm.toggle_display('board_type_code', false);
        frm.toggle_display('program_type_code', false);
        frm.toggle_display('offline_vend_storage', true);
        frm.toggle_display('keypad_id_entry', true);
    }
}

function applyBoardManufacturerTypeRules(frm) {
    if (frm.doc.board_manufacturer_id) {
        frappe.db.get_value('Board Manufacturer', frm.doc.board_manufacturer_id, 'manufacturer_name', function(r) {
            let manufacturer_name = r && r.manufacturer_name ? r.manufacturer_name : '';
            setVisibleFields(frm); 
            if (manufacturer_name === "VendNovation") {
                frm.set_value('motor_range_start', null);
                frm.set_value('motor_range_end', null);
                frm.set_value('motor_rows_start', null);
                frm.set_value('motor_rows_end', null);
                frm.set_value('offline_vend_storage', 0);
                frm.set_value('board_type_code', '');
                frm.set_value('program_type_code', null);
                frm.set_value('keypad_id_entry', 0);
                frm.set_df_property('is_pin_entry_enabled', 'label', 'Is Keypad ID Entry Enabled?');
            } else {
                frm.set_value('motor_range_start', '11');
                frm.set_value('motor_range_end', '80');
                frm.set_value('motor_rows_start', 1);
                frm.set_value('motor_rows_end', 7);
                frm.set_value('board_type_code', 'D');
                frm.set_df_property('is_pin_entry_enabled', 'label', 'Is PIN Entry Enabled?');
            }
        });
    }
}

function onFirmwareCheckboxChange(frm) {
    if (frm.doc.is_update_firmware) {
        frm.set_value('is_update_connection', 0);
        frm.set_value('is_update_machine_motor_info', 0);
        frm.set_value('is_update_rfid', 0);

        frm.set_df_property('is_update_connection', 'read_only', 1);
        frm.set_df_property('is_update_machine_motor_info', 'read_only', 1);
        frm.set_df_property('is_update_rfid', 'read_only', 1);
    } else {
        frm.set_df_property('is_update_connection', 'read_only', 0);
        frm.set_df_property('is_update_machine_motor_info', 'read_only', 0);
        frm.set_df_property('is_update_rfid', 'read_only', 0);
    }
}