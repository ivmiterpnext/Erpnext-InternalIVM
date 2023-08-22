frappe.ui.form.on("Opportunity", {
  refresh: function(frm) {
    if (frm.doc.sales_stage =='Closed Won'){
      frm.add_custom_button(__('Create Deployment'),
				function() {
          frappe.model.open_mapped_doc({
            method:"ivm.api.make_project",
            frm:frm
          })
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
})   