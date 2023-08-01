frappe.ui.form.on("Task", {
    parent_task: function (frm) {
        cur_frm.clear_table("child_tasks")
        frappe.call({
            method: "ivm.api.get_child_tasks",
            args: {
                'parent_task': frm.doc.parent_task
            },
            callback: function (data) {
                if (data) {
                    // Loop through the received tasks and append rows
                    frm.set_df_property('child_tasks', 'hidden', 0)
                    const tasks = data.message[0];
                    for (let i = 0; i < tasks.length; i++) {
                        let task = tasks[i];
                        let row = frappe.model.add_child(frm.doc, 'child_tasks');
                        row.subject = task.subject;
                        row.task = task.name;
                    }
                }
                // Refresh the child table
                frm.refresh_field('child_tasks');
            }
        });
    }
});
