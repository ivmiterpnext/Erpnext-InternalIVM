// Machine child table constants — JS copy of the canonical definitions
// in ivm/deals/constants.py.  Keep in sync when machine types change.
const DL_MACHINE_DETAIL_TABLES = [
    "smartstation_details",
    "smartlocker_details",
    "smartsync_details",
    "smartvault_details",
    "smartcenter_details",
];

const DL_TABLE_TO_QUANTITY = {
    smartstation_details: "number_of_machines",
    smartlocker_details: "number_of_primary_lockers",
    smartsync_details: "number_of_secondary_lockers",
    smartcenter_details: "number_of_kiosks",
    smartvault_details: "number_of_vaults",
};

function updateDLQuantities(frm) {
    let changed = false;
    for (const [table_field, qty_field] of Object.entries(DL_TABLE_TO_QUANTITY)) {
        const count = (frm.doc[table_field] || []).length;
        if (frm.doc[qty_field] !== count) {
            frm.doc[qty_field] = count;
            frm.refresh_field(qty_field);
            changed = true;
        }
    }
    if (changed) frm.dirty();
}

// Register child table add/remove handlers for quantity auto-calc + bins editor
const DL_CHILD_DOCTYPE_TO_TABLE = {
    "Deployment SmartStation Details": "smartstation_details",
    "Deployment SmartLocker Details": "smartlocker_details",
    "Deployment SmartSync Details": "smartsync_details",
    "Deployment SmartVault Details": "smartvault_details",
    "Deployment SmartCenter Details": "smartcenter_details",
};

for (const [dt, table_field] of Object.entries(DL_CHILD_DOCTYPE_TO_TABLE)) {
    const handlers = {};
    handlers[table_field + "_add"] = (frm) => updateDLQuantities(frm);
    handlers[table_field + "_remove"] = (frm) => updateDLQuantities(frm);

    if (dt === "Deployment SmartLocker Details" || dt === "Deployment SmartSync Details") {
        handlers.form_render = (frm, cdt, cdn) => injectBinsEditor(frm, cdt, cdn);
    }

    frappe.ui.form.on(dt, handlers);
}

frappe.ui.form.on("Deployment Location", {
    refresh(frm) {
        // Always open on the first tab
        frm.set_active_tab(frm.layout.tabs[0]);

        setupMachineDetailGrids(frm, DL_MACHINE_DETAIL_TABLES);
        updateDLQuantities(frm);

        if (frm.doc.crm_deal) {
            frm.add_custom_button(__("Back to Deal"), () => {
                if (frm.is_dirty()) {
                    frappe.confirm(
                        __("You have unsaved changes. Discard and return to the deal?"),
                        () => {
                            // Clear local cache for this doc so stale data doesn't linger
                            frappe.model.clear_doc(frm.doctype, frm.docname);
                            frappe.set_route("Form", "CRM Deal", frm.doc.crm_deal);
                        }
                    );
                } else {
                    frappe.set_route("Form", "CRM Deal", frm.doc.crm_deal);
                }
            });
        }
    },

    before_save(frm) {
        validateUniqueMachineNames(frm, DL_MACHINE_DETAIL_TABLES);
        updateDLQuantities(frm);
    },
});
