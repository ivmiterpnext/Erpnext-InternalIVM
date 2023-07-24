// Function to check if the SalesLoft user already exists
function checkSalesLoftUser(email) {
    return new Promise(function (resolve, reject) {
      frappe.call({
        method: "ivm.api.check_salesloft_user",
        args: {
          email: email,
        },
        callback: function (response) {
          var data = response.message;
          resolve(data);
        },
        error: function (xhr, textStatus, errorThrown) {
          // If the API call fails, reject the promise and handle the error
          reject(errorThrown);
        },
      });
    });
  }
  
  // Function to show SalesLoft user details in a popup
  function showSalesLoftUserDetails(data) {
    // Create the HTML content for the popup dialog
    var message = `
      <div style="text-align: center; font-size: 18px; font-weight: bold; margin-bottom: 20px;">
        SalesLoft User Found
      </div>
      <div style="margin-bottom: 10px;">
        <strong>Email:</strong> ${data.email_address || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>Name:</strong> ${data.first_name || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>City:</strong> ${data.city || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>Last Contacted At:</strong> ${data.last_contacted_at || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>Person Company Industry:</strong> ${data.person_company_industry || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>Person Company Name:</strong> ${data.person_company_name || "Not Found"}
      </div>
      <div style="margin-bottom: 10px;">
        <strong>View User in SalesLoft:</strong>
        ${data.id ? `<a href="https://app.salesloft.com/app/people/${data.id}" target="_blank" style="text-decoration: none; color: #3366CC;">${data.id}</a>` : "Not Found"}
      </div>
    `;
  
    // Create a new Frappe dialog with the HTML content
    var dialog = new frappe.ui.Dialog({
      title: "SalesLoft User Found",
      fields: [
        {
          fieldtype: "HTML",
          fieldname: "message",
          label: "Details",
        },
      ],
      primary_action_label: "OK",
      primary_action: function () {
        dialog.hide();
      },
    });
  
    // Set the HTML content in the dialog and show it
    dialog.fields_dict.message.$wrapper.html(message);
    dialog.show();
  }
  
  
  // Function to create a new SalesLoft person
  function createSalesLoftPerson(email, name, frm) {
    frappe.call({
      method: "ivm.api.create_salesloft_person",
      args: {
        email: email,
        name: name,
      },
      callback: function (response) {
        if (response.message) {
          var salesloftLink = `<a href="https://app.salesloft.com/app/people/${response.message}" target="_blank" rel="noopener noreferrer">SalesLoft ID: ${response.message}</a>`;
          var description = `
            <p style="margin-top: 10px; margin-bottom: 5px; color: #3366CC;">
              SalesLoft Link:
              ${salesloftLink}
            </p>
          `;
  
          // Set the SalesLoft link description for the email_id field
          frm.set_df_property("email_id", "description", description);
          frappe.show_alert("Lead created and SalesLoft user added.", 3);
        } else {
          // Clear the SalesLoft link description if the creation fails
          frm.set_df_property("email_id", "description", "");
          frappe.show_alert(
            "Failed to create SalesLoft user. Please try again.",
            3
          );
        }
      },
      error: function (xhr, textStatus, errorThrown) {
        // Handle error if the API call fails
        frappe.show_alert(
          "An error occurred while creating the SalesLoft user. Please try again later.",
          3
        );
        console.error(xhr, textStatus, errorThrown);
      },
    });
  }
  
  // Frappe form event handling for the Lead doctype
  frappe.ui.form.on("Lead", {
    validate: function (frm) {
      var email = frm.doc.email_id;
      var name = frm.doc.first_name;
  
      // Check if the SalesLoft user already exists
      checkSalesLoftUser(email)
        .then((data) => {
          if (data) {
            // If the user exists, prevent saving the lead and show the details popup
            frappe.validated = false;
            showSalesLoftUserDetails(data);
          } else {
            // If the user doesn't exist, create a new SalesLoft person
            createSalesLoftPerson(email, name, frm);
          }
        })
        .catch((error) => {
          // Handle error if the API call fails
          frappe.show_alert(
            "An error occurred while checking SalesLoft user. Please try again.",
            3
          );
          console.error(error);
        });
    },
    email_id: function (frm, cdt, cdn) {
      var email = frm.doc.email_id;
  
      // Check if the SalesLoft user already exists when email field changes
      checkSalesLoftUser(email)
        .then((data) => {
          if (data) {
            // If the user exists, show the link and details below the email field
            var description = `
              <p style="margin-top: 10px; margin-bottom: 5px; color: #FF0000;">
                SalesLoft User Already Exists
              </p>
              <p style="margin-bottom: 10px;">
                SalesLoft ID:
                <a href="https://app.salesloft.com/app/people/${data.id}" target="_blank" class="salesloft-link">
                  ${data.id}
                </a>
              </p>
            `;
  
            // Set the SalesLoft link description for the email_id field
            frm.set_df_property("email_id", "description", description);
          } else {
            // If the user doesn't exist, clear the link and details below the email field
            frm.set_df_property("email_id", "description", "");
          }
        })
        .catch((error) => {
          // Handle error if the API call fails
          frappe.show_alert(
            "An error occurred while checking SalesLoft user. Please try again.",
            3
          );
          console.error(error);
        });
    },
  });
  