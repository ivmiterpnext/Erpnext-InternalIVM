frappe.ui.form.on("Opportunity", {
  // Fetching the value of percentage field on sales_stage trigger
  sales_stage: function (frm) {
    frappe.db.get_value('Sales Stage', frm.doc.sales_stage, 'percentage').then((res) => {
      cur_frm.set_value('probability', res.message.percentage)
    })
  },
  onload: function (frm) {
    $(document).ready(function () {
      $(".section-head").css({ "color": "#2490EF", 'font-size': '20px' });

    })
  },
  before_save: function (frm) {
    // Claculating the equipment_total value 

    let equipment_total = frm.doc.number_of_machines + frm.doc.number_of_primary_lockers + frm.doc.number_of_secondary_lockers
    cur_frm.set_value('equipment_total', equipment_total)
  },
  probability: function (frm) {
    // On probabilityfield trigger calculting the forecast_revenue

    let number_of_machines = frm.doc.number_of_machines ? frm.doc.number_of_machines : 1
    let number_of_primary_lockers = frm.doc.number_of_primary_lockers ? frm.doc.number_of_primary_lockers : 1
    let number_of_secondary_lockers = frm.doc.number_of_secondary_lockers ? frm.doc.number_of_secondary_lockers : 1
    let sv_term = Number(frm.doc.sv_term.slice(0, 2)) + 1

    let total_forecast_revenue = frm.doc.per_machine_mthly_lease_fee * number_of_machines + frm.doc.per_primary_locker_mthly_lease_fee * number_of_primary_lockers + frm.doc.per_secondary_locker_mthly_lease_fee * number_of_secondary_lockers * sv_term
    console.log(total_forecast_revenue, "total_forecast_revenue")


    let forecast_revenue = total_forecast_revenue / 100 * frm.doc.probability
    cur_frm.set_value('forecast_revenue', forecast_revenue)
  }

})
