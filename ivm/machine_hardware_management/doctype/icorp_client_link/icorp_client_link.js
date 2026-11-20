frappe.ui.form.on("iCorp Client Link", {
	refresh: function (frm) {
		render_child_clients(frm);
	},
});

function render_child_clients(frm) {
	const field = frm.get_field("child_clients_html");
	if (!field) return;

	field.$wrapper.empty();
	frm.toggle_display("child_clients_html", false);

	if (frm.is_new()) return;

	const docname = frm.doc.name;

	frappe.call({
		method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.get_child_clients",
		args: { parent_client: frm.doc.name },
		callback: function (r) {
			if (frm.doc.name !== docname) return;

			const children = r.message || [];
			if (!children.length) return;

			let rows = children
				.map(function (c) {
					const customer_display = c.customer || "—";
					return `
						<tr>
							<td><a href="/app/icorp-client-link/${encodeURIComponent(
								c.name
							)}">${frappe.utils.escape_html(c.display_label)}</a></td>
							<td>${frappe.utils.escape_html(customer_display)}</td>
							<td>${c.sv_machine_count_active || 0}</td>
						</tr>`;
				})
				.join("");

			const html = `
				<div style="margin-top: 10px;">
					<b>${__("Child clients ({0})", [children.length])}</b>
					<table class="table table-bordered" style="margin-top: 6px;">
						<thead>
							<tr>
								<th>${__("Client")}</th>
								<th>${__("Customer")}</th>
								<th>${__("Machines")}</th>
							</tr>
						</thead>
						<tbody>${rows}</tbody>
					</table>
				</div>`;

			field.$wrapper.html(html);
			frm.toggle_display("child_clients_html", true);
		},
	});
}
