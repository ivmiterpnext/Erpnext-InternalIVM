frappe.listview_settings["Lead"] = {
  hide_name_column: true,
  onload: function (me) {
    me.$page.find(`div[data-fieldname='name']`).addClass("hide");
    me.$page.find(`div[data-fieldname='title']`).addClass("hide");
    me.page.add_inner_button("Import from Apollo", function () {
      importLeads();
    }).css({
      'background-color': '#4CAF50', 
      'color': 'white', 
      'border': 'none',
      'text-align': 'center',
      'cursor': 'pointer',
    });
  },
};
function importLeads() {
  var data = [];
  var selectedPage = 1;
  var selectedContacts = [];
  var searchKeyword = '';

  function fetchAndDisplayData(page) {
    frappe.show_progress("Loading..", 70, 100, "Please wait");
    frappe.call({
      method: "ivm.api.fetch_contacts_from_apollo",
      args: { page: page,searchKeyword:searchKeyword},
      callback: function (r) {
        if (r.message && r.message.contacts) {
          console.log(r.message.contacts)
          frappe.hide_progress();

          data = r.message.contacts;

          var tableHTML =
            '<table id="contact-table" class="table table-bordered">';
          tableHTML +=
            "<thead><tr><th>Name</th><th>Title</th><th>Email</th><th>Select</th></tr></thead>";
          tableHTML += "<tbody>";

          data.forEach(function (contact) {
            tableHTML += "<tr>";
            tableHTML += "<td>" + contact.name + "</td>";
            tableHTML += "<td>" + contact.title + "</td>";
            tableHTML += "<td>" + contact.email + "</td>";
            tableHTML +=
            '<td><input type="checkbox" data-id="' + contact.id + '"' +
            (contact.disabled ? ' disabled' : '') + '></td>'
                        tableHTML += "</tr>";
          });

          tableHTML += "</tbody></table>";
          var pageOptionsHTML = [];
          for (var i = 1; i <= r.message.pagination.total_pages; i++) {
            pageOptionsHTML.push(i);
          }

          let d = new frappe.ui.Dialog({
            title: "Contact Information",
            fields: [
              {
                label: "Page",
                fieldname: "selected_page",
                fieldtype: "Select",
                options: pageOptionsHTML,
                default: selectedPage.toString(),
                onchange: function (e) {
                  e.stopPropagation(); 
                  selectedPage = d.get_value("selected_page");
                  changedata(selectedPage,searchKeyword, selectedContacts);
                },
              },

              {
                fieldname: 'column_break_123',
                fieldtype: 'Column Break',
                
           },
          //     {
          //       label: 'Sort Order',
          //       fieldname: 'sort_order',
          //       fieldtype: 'Select',
          //       options:["Ascending","Descending"],
          //   },{
          //     fieldname: 'column_break_124',
          //     fieldtype: 'Column Break',
              
          // },
            {
                label: 'Search',
                fieldname: 'search_keyword',
                fieldtype: 'Data',
                default: searchKeyword
            },{
              label: 'Search',
              fieldname: 'search_button',
              fieldtype: 'Button',
            },
            
            {
              fieldname: 'section_break_124',
              fieldtype: 'Section Break',
              
          },
              {
                label: "Data",
                fieldname: "data",
                fieldtype: "HTML",
                options: tableHTML,
              },
            ],
            primary_action_label: "OK",
            primary_action: function () {

              d.hide();
              frappe.show_progress("Loading..", 70, 100, "Please wait");

              frappe.call({
                method: "ivm.api.createLeads",
                args: { selectedContacts: selectedContacts },
                callback: function (r) {
                  frappe.hide_progress();
                },
              });
            },
          });
          d.$wrapper.find(".modal-dialog").css({
          "max-width": "800px",
          "width": "80%",
          "margin": "30px auto",
            "border": "1px solid #e5e5e5",
          });
        
          d.show();
          d.$wrapper.find('[data-fieldname="search_button"]').off('click').on('click', function (e) {
            e.stopPropagation(); 
            console.log(e);
            searchKeyword = d.get_value("search_keyword");
            console.log(searchKeyword);
            changedata(selectedPage, searchKeyword, selectedContacts);
        });
        
        
          d.$wrapper.find("input[type=checkbox]").change(function () {
            var contactId = $(this).attr("data-id");
            var selectedContact = data.find(
              (contact) => contact.id === contactId
            );
            if (this.checked) {
              selectedContacts.push(selectedContact);
            } else {
              var index = selectedContacts.findIndex(
                (contact) => contact.id === contactId
              );
              if (index !== -1) {
                selectedContacts.splice(index, 1);
              }
            }
          });
        } else {
          frappe.msgprint("No data available.");
        }
      },
    });
  }

  fetchAndDisplayData(selectedPage);
}
function changedata(selectedPage,searchKeyword, selectedContacts) {

  var table = $("#contact-table");
  table.find("tbody").remove();
  frappe.show_progress("Loading..", 70, 100, "Please wait");

  frappe.call({
    method: "ivm.api.fetch_contacts_from_apollo",
    args: { page: selectedPage,searchKeyword:searchKeyword },
    callback: function (r) {
      if (r.message && r.message.contacts) {
        frappe.hide_progress();
        var newData = r.message.contacts;

        var newTbody = $("<tbody></tbody>");

        $.each(newData, function (index, contact) {
          var newRow = $("<tr></tr>");
          newRow.append("<td>" + contact.name + "</td>");
          newRow.append("<td>" + contact.title + "</td>");
          newRow.append("<td>" + contact.email + "</td>");
          newRow.append(
            '<td><input type="checkbox" data-id="' + contact.id + '"' +
(contact.disabled ? ' disabled' : '') + '></td>'
          )

          newTbody.append(newRow);
        });

        table.append(newTbody);
        newTbody.find("input[type=checkbox]").change(function () {
          var contactId = $(this).attr("data-id");
          var selectedContact = newData.find(
            (contact) => contact.id === contactId
          );
          if (this.checked) {
            selectedContacts.push(selectedContact);
          } else {
            var index = selectedContacts.findIndex(
              (contact) => contact.id === contactId
            );
            if (index !== -1) {
              selectedContacts.splice(index, 1);
            }
          }
        });
      }
    },
  });
}
