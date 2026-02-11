frappe.ui.form.on("Customer", {
  onload: function(frm) {
      $(document).ready(function() {
          $(".section-head").css({"color": "#2490EF", "font-size": "16px"});
      });

      if (frm.doc.__islocal) {
        return; // Exit the function if it's a new customer
    ``}

      frappe.call({
        method: "ivm.api.calculate_closed_opportunity_total",
        args: {
            customer_name: frm.doc.customer_name
        },
        callback: function(response) {
            if (!response.exc) {
                // Set the calculated value as a read-only field
                frm.set_value('custom_total_account_sv', response.message);
                frm.refresh_field('custom_total_account_sv');
                frm.save(ignore_permission = true) // Refresh the field to display the value
            } else {
                console.error("Error:", response.exc);
            }
        }
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

        setTimeout(function() {
            var totalAccountSV = frm.doc.custom_total_account_sv;
            var totalPieces = frm.doc.custom_total_pieces_of_equipment_in_place;
            if (totalAccountSV > 0 && totalPieces > 0) {
                var averageValuePerPiece = totalAccountSV / totalPieces;
                var averageValuePerPieceRounded = averageValuePerPiece.toFixed(2);
                frm.set_value('custom_average_value_per_piece', averageValuePerPieceRounded);
            }
        }, 1000);
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



