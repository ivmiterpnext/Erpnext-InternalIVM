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
    },
    project_type:function(frm){
        frappe.call({
        method: 'ivm.api.set_cell_Carrier',
        args: {
        option: frm.doc.connectivity_type
        },
        callback: function(r) {
        var options = []
        for (let i = 0; i < r.message.length; i++){
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
        options.forEach(function(option) {
        var optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.text = option;
        optionElement.style.fontSize = "18px"
        optionElement.style.margin="5px"
        selectElement.appendChild(optionElement);
        });
        
        
        // Append the label and select elements to the field wrapper
        frm.fields_dict['cell_carrier'].wrapper.appendChild(labelElement);
        frm.fields_dict['cell_carrier'].wrapper.appendChild(selectElement);
        }
        })
        },
        connectivity_type:function(frm){
        frappe.call({
        method: 'ivm.api.set_cell_Carrier',
        args: {
        option: frm.doc.connectivity_type
        },
        callback: function(r) {
        var options = []
        for (let i = 0; i < r.message.length; i++){
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
        options.forEach(function(option) {
        var optionElement = document.createElement('option');
        optionElement.value = option;
        optionElement.text = option;
        optionElement.style.fontSize = "18px"
        optionElement.style.margin="5px"
        selectElement.appendChild(optionElement);
        });
        
        
        // Append the label and select elements to the field wrapper
        frm.fields_dict['cell_carrier'].wrapper.appendChild(labelElement);
        frm.fields_dict['cell_carrier'].wrapper.appendChild(selectElement);
        }
        })
        }
        
});


    