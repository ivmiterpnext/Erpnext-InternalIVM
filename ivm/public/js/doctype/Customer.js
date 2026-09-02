frappe.ui.form.on("Customer", {
  onload: function(frm) {
      $(document).ready(function() {
          $(".section-head").css({"color": "#2490EF", "font-size": "16px"});
      });
  },
  validate: async function(frm) {
      if (frm.doc.__islocal) {
          const customerExists = await checkCustomerExists(frm.doc.customer_name);
          if (customerExists) {
              const confirmed = await showConfirmationPopup();
              if (!confirmed) {
                  frappe.validated = false;
              }
          }
      }
      var sum = parseInt(frm.doc.number_of_lockers_in_place) + parseInt(frm.doc.number_of_machines_in_place);
        frm.set_value('custom_total_pieces_of_equipment_in_place', sum);
  },
});

async function checkCustomerExists(customerName) {
  return new Promise(function(resolve, reject) {
      frappe.call({
          method: "frappe.client.get_value",
          args: {
              doctype: "Customer",
              filters: {
                  customer_name: customerName,
              },
              fieldname: "name",
          },
          callback: function(customer_response) {
              resolve(!!customer_response.message.name);
          },
      });
  });
}

function showConfirmationPopup() {
  return new Promise(function(resolve, reject) {
      frappe.confirm(
          "A customer with the same name already exists. Do you want to continue?",
          function() {
              resolve(true);
          }
      );
  });
}


