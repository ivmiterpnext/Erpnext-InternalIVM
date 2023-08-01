frappe.ui.form.on("Opportunity", {
    sales_stage: function (frm) {
        cur_frm.add_fetch('sales_stage', 'percentage', 'probability');
    },
    onload: function(frm){
      $(document).ready(function(){
            $(".section-head").css({"color":"#2490EF",'font-size': '20px'});
              
      })
  }
})