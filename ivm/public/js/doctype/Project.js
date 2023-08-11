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
    }
});
