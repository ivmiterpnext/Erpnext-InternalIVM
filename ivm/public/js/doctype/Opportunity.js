frappe.ui.form.on("Opportunity", {
  refresh: function(frm) {
    if (frm.doc.sales_stage =='Closed Won'){
      frm.add_custom_button(__('Create Case'),
				function() {
        frm.trigger("create_project")
        }, __('Create'));
    }
		},
  // Fetching the value of percentage field on sales_stage trigger
  sales_stage: function (frm) {
    frappe.db.get_value('Sales Stage', frm.doc.sales_stage, 'percentage').then((res) => {
      cur_frm.set_value('probability', res.message.percentage)
    })
  },
  onload: function (frm) {
    frm.set_query("deployment_address", function () {
      return {
        "filters": [
          ["Address", "address_type", "=", "Deployment"],
        ]
      }
    });
    frm.fields_dict['sales_stage'].get_query = function (doc, cdt, cdn) {
      return {
        query: 'ivm.api.arrangeing_records',
      }
    }
    $(document).ready(function () {
      $(".section-head").css({ "color": "#2490EF", 'font-size': '20px' });

    })
  },
  before_save: function (frm) {
    // Claculating the equipment_total value 

    let equipment_total = frm.doc.number_of_machines + frm.doc.number_of_primary_lockers + frm.doc.number_of_secondary_lockers + frm.doc.number_of_kiosks + frm.doc.number_of_vaults
    cur_frm.set_value('equipment_total', equipment_total)
  },
  probability: function (frm) {
    // On probability field trigger calculting the forecast_revenue

    let number_of_machines = frm.doc.number_of_machines ? frm.doc.number_of_machines : 1
    let number_of_primary_lockers = frm.doc.number_of_primary_lockers ? frm.doc.number_of_primary_lockers : 1
    let number_of_secondary_lockers = frm.doc.number_of_secondary_lockers ? frm.doc.number_of_secondary_lockers : 1
    let sv_term = Number(frm.doc.sv_term.slice(0, 2)) + 1

    let val1 = frm.doc.per_machine_mthly_lease_fee * number_of_machines
    let val2 = frm.doc.per_primary_locker_mthly_lease_fee * number_of_primary_lockers
    let val3 = frm.doc.per_secondary_locker_mthly_lease_fee * number_of_secondary_lockers
    let total = val1 + val2 + val3
    let sv_term_mul = total * sv_term

    let forecast_revenue = sv_term_mul / 100 * frm.doc.probability
    cur_frm.set_value('forecast_revenue', forecast_revenue)
  },
  create_project : function(frm){
    console.log("uma")
      var projectValues = {
            "opportunity": frm.doc.name,
            "number_of_kiosks":frm.doc.number_of_kiosks,
            "enhanced_lockers":frm.doc.enhanced_lockers,
            "expedited_delivery":frm.doc.expedited_delivery,
            "expedited_delivery_details":frm.doc.expedited_delivery_details,
            "install_type":frm.doc.install_type,
            "po_and_tracking":frm.doc.po_and_tracking,
            "vault_size":frm.doc.vault_size,
            "vault_power_configuration_details":frm.doc.vault_power_configuration_details,
            "kiosk_options":frm.doc.kiosk_options,
            "kvm_switch_options":frm.doc.kvm_switch_options,
            "network_options":frm.doc.network_options,
            "countertop_color":frm.doc.countertop_color,
            "ada_side_table":frm.doc.ada_side_table,
            "description":frm.doc.description,
            "customer":frm.doc.customer

        };
        console.log(projectValues)

          frappe.new_doc("Project",projectValues);  }

})
