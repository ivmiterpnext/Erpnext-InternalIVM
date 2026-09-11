frappe.ui.form.on('Pick List', {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('Export to Excel'), () => {
				window.open(
					`/api/method/ivm.warehouse.services.pick_list.export_pick_list_cost_excel?pick_list=${encodeURIComponent(frm.doc.name)}`
				);
			});
		}
	}
});
