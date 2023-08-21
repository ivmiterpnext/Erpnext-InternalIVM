frappe.ui.form.on("Project", {
    onload: function (frm) {
        frm.set_query("shipping_address", function () {
            return {
                "filters": [
                    ["Address", "address_type", "=", "Shipping"],
                ]
            }
        });
        frm.set_query("billing_address", function () {
            return {
                "filters": [
                    ["Address", "address_type", "=", "Billing"],
                ]
            }
        });
        frm.set_query("associated_deployment_location", function () {
            return {
                "filters": [
                    ["Address", "address_type", "=", "Deployment"],
                ]
            }
        });

        $(document).ready(function() {
            let Num_of_kios = $('input[data-fieldname="number_of_kiosks"]')
            Num_of_kios.css('background','#e1f0f0')
            let Opp = $('input[data-fieldname="opportunity"]')
            Opp.css('background-color','#e1f0f0')
            let Enhanced_lo = $('div[data-fieldname="enhanced_lockers"]')
            Enhanced_lo.find(".label-area").css('background-color','#e1f0f0')
            let Expected_Delivery = $('div[data-fieldname="expedited_delivery"]')
            Expected_Delivery.find(".label-area").css('background-color','#e1f0f0')
            let Expected_deli = $('textarea[data-fieldname="expedited_delivery_details"]')
            Expected_deli.css('background-color','#e1f0f0')
            let Install_Type = $('select[data-fieldname="install_type"]')
            Install_Type.css('background-color','#e1f0f0')
            let Po_Tracking = $('input[data-fieldname="po_and_tracking"]')
            Po_Tracking.css('background-color','#e1f0f0')
            let Vault_Size = $('select[data-fieldname="vault_size"]')
            Vault_Size.css('background-color','#e1f0f0')
            let Vault_power = $('textarea[data-fieldname="vault_power_configuration_details"]')
            Vault_power.css('background-color','#e1f0f0')
            let Associated_Deployment_Loc = $('input[data-fieldname="associated_deployment_location"]')
            Associated_Deployment_Loc.css('background-color','#e1f0f0')
            let Kiosk_Options = $('select[data-fieldname="kiosk_options"]')
            Kiosk_Options.css('background-color','#e1f0f0')
            let Kvm_switch_Options = $('select[data-fieldname="kvm_switch_options"]')
            Kvm_switch_Options.css('background-color','#e1f0f0')
            let Network_Options = $('select[data-fieldname="network_options"]')
            Network_Options.css('background-color','#e1f0f0')
            let Countertop_Color = $('select[data-fieldname="countertop_color"]')
            Countertop_Color.css('background-color','#e1f0f0')
            let Ada_Side_Table = $('select[data-fieldname="ada_side_table"]')
            Ada_Side_Table.css('background-color','#e1f0f0')
            let Kiosk_Side_Table = $('select[data-fieldname="kiosk_side_for_table"]')
            Kiosk_Side_Table.css('background-color','#e1f0f0')
            let Description = $('textarea[data-fieldname="description"]')
            Description.css('background-color','#e1f0f0')
            let Customer_1 = $('input[data-fieldname="customer"]')
            Customer_1.css('background-color','#e1f0f0') 
        });

    },
    customer: function (frm) {
        frappe.db.get_doc("Customer", frm.doc.customer).then(r => {
            frm.set_value('opportunity', r.opportunity_name);

        })
    },
    project_type: function (frm) {
        frappe.call({
            method: 'ivm.api.set_cell_Carrier',
            args: {
                option: frm.doc.connectivity_type
            },
            callback: function (r) {
                var options = []
                for (let i = 0; i < r.message.length; i++) {
                    console.log(r.message[i]["cell_carrier"])
                    options.push(r.message[i]["cell_carrier"])
                }


                frm.fields_dict['cell_carrier'].wrapper.innerHTML = '';


                // Create a label for the custom field
                var labelElement = document.createElement('label');
                labelElement.innerHTML = 'Cell Carrier'; // Change this to your desired label


                // Create a custom HTML select element
                var selectElement = document.createElement('select');
                selectElement.className = 'input-with-feedback form-control';
                selectElement.id = 'custom-sales-stage';
                selectElement.style.marginBottom = '10px';


                // Populate options in your desired order
                options.forEach(function (option) {
                    var optionElement = document.createElement('option');
                    optionElement.value = option;
                    optionElement.text = option;
                    optionElement.style.fontSize = "18px"
                    optionElement.style.margin = "5px"
                    selectElement.appendChild(optionElement);
                });


                // Append the label and select elements to the field wrapper
                frm.fields_dict['cell_carrier'].wrapper.appendChild(labelElement);
                frm.fields_dict['cell_carrier'].wrapper.appendChild(selectElement);
            }
        })
    },
    connectivity_type: function (frm) {
        if (frm.doc.connectivity_type){
        frappe.call({
            method: 'ivm.api.set_cell_Carrier',
            args: {
                option: frm.doc.connectivity_type
            },
            callback: function (r) {
                var options = []
                for (let i = 0; i < r.message.length; i++) {
                    console.log(r.message[i]["cell_carrier"])
                    options.push(r.message[i]["cell_carrier"])
                }


                frm.fields_dict['cell_carrier'].wrapper.innerHTML = '';


                // Create a label for the custom field
                var labelElement = document.createElement('label');
                labelElement.innerHTML = 'Cell Carrier'; // Change this to your desired label


                // Create a custom HTML select element
                var selectElement = document.createElement('select');
                selectElement.className = 'input-with-feedback form-control';
                selectElement.id = 'custom-sales-stage';
                selectElement.style.marginBottom = '12px';


                // Populate options in your desired order
                options.forEach(function (option) {
                    var optionElement = document.createElement('option');
                    optionElement.value = option;
                    optionElement.text = option;
                    optionElement.style.fontSize = "18px"
                    optionElement.style.margin = "5px"
                    selectElement.appendChild(optionElement);
                });


                // Append the label and select elements to the field wrapper
                frm.fields_dict['cell_carrier'].wrapper.appendChild(labelElement);
                frm.fields_dict['cell_carrier'].wrapper.appendChild(selectElement);
            }
        })
    }},
    opportunity: function(frm){
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Opportunity", 
                name: frm.doc.opportunity  
            },
            callback: function(response) {
                var doc = response.message;
                frm.set_value("number_of_kiosks",doc.number_of_kiosks)
                frm.set_value("enhanced_lockers",doc.enhanced_lockers)
                frm.set_value("expedited_delivery",doc.expedited_delivery)
                frm.set_value("expedited_delivery_details",doc.expedited_delivery_details)
                frm.set_value("install_type",doc.install_type)
                frm.set_value("po_and_tracking",doc.po_and_tracking)
                frm.set_value("vault_size",doc.vault_size)
                frm.set_value("vault_power_configuration_details",doc.vault_power_configuration_details)
                frm.set_value("kiosk_options",doc.kiosk_options)
                frm.set_value("kvm_switch_options",doc.kvm_switch_options)
                frm.set_value("network_options",doc.network_options)
                frm.set_value("countertop_color",doc.countertop_color)
                frm.set_value("ada_side_table",doc.ada_side_table)
                frm.set_value("description",doc.description)
                frm.set_value("associated_deployment_location",doc.deployment_address)
                if (doc.customer_name) {
                    frappe.call({
                        method: "frappe.client.get_value",
                        args: {
                            doctype: "Customer",
                            filters: {
                                name: doc.customer_name
                            },
                            fieldname: "name"
                        },
                        callback: function(customer_response) {
                            console.log(customer_response.message.name)
                            if (customer_response.message && customer_response.message.name) {
                                frm.set_value("customer", doc.customer_name);
                            }
                        }
                    });
                }
            }
        });
        
    }
});


