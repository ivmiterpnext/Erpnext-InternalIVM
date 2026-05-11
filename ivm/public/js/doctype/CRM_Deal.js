// ---------------------------------------------------------------------------
// Sites tab – table of Deal Location Information docs linked to this CRM Deal
// ---------------------------------------------------------------------------

const SITE_DOCTYPE = "Deal Location Information";

const SITE_LIST_FIELDS = [
  "name", "location_name", "locale", "equipment_type",
  "number_of_machines", "number_of_primary_lockers",
  "number_of_secondary_lockers", "number_of_kiosks", "number_of_vaults",
];

function renderSitesTab(frm) {
  if (frm.is_new()) return;

  const wrapper = frm.fields_dict.custom_locations_html?.$wrapper;
  if (!wrapper) return;

  wrapper.empty();

  const $container = $('<div class="deal-sites-container"></div>').appendTo(wrapper);

  // Load existing sites, then add button below
  frappe.call({
    method: "frappe.client.get_list",
    args: {
      doctype: SITE_DOCTYPE,
      filters: { crm_deal: frm.doc.name },
      fields: SITE_LIST_FIELDS,
      order_by: "creation asc",
    },
    callback(r) {
      const sites = r.message || [];

      // Total device counts across all sites
      renderDeviceTotals($container, sites);

      if (!sites.length) {
        $container.append('<p class="text-muted">No sites yet.</p>');
      } else {
        renderSitesTable($container, sites, frm);
      }

      // Add Site button after the table
      $(`<button class="btn btn-xs btn-primary mb-3">+ Add Site</button>`)
        .appendTo($container)
        .on("click", () => addNewSite(frm));
    },
  });
}

function renderDeviceTotals($container, sites) {
  const totals = {
    SmartStations: 0,
    SmartLockers: 0,
    SmartSyncs: 0,
    SmartCenters: 0,
    SmartVaults: 0,
  };

  sites.forEach((s) => {
    totals.SmartStations += s.number_of_machines || 0;
    totals.SmartLockers += s.number_of_primary_lockers || 0;
    totals.SmartSyncs += s.number_of_secondary_lockers || 0;
    totals.SmartCenters += s.number_of_kiosks || 0;
    totals.SmartVaults += s.number_of_vaults || 0;
  });

  const $row = $('<div class="row mb-3" style="font-size:13px;"></div>').appendTo($container);

  for (const [label, count] of Object.entries(totals)) {
    $row.append(`
      <div class="col text-center">
        <div class="text-muted small">${label}</div>
        <div class="font-weight-bold" style="font-size:16px;">${count}</div>
      </div>
    `);
  }
}

function renderSitesTable($container, sites, frm) {
  const $table = $(`
    <table class="table table-bordered table-hover" style="font-size: 13px;">
      <thead>
        <tr>
          <th>Location</th>
          <th>Locale</th>
          <th>Equipment Type</th>
          <th class="text-center">SS</th>
          <th class="text-center">SL</th>
          <th class="text-center">SSy</th>
          <th class="text-center">SC</th>
          <th class="text-center">SV</th>
          <th style="width:60px;"></th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  `).appendTo($container);

  const $tbody = $table.find("tbody");

  sites.forEach((site) => {
    const equipTotal = (site.number_of_machines || 0)
      + (site.number_of_primary_lockers || 0)
      + (site.number_of_secondary_lockers || 0)
      + (site.number_of_kiosks || 0)
      + (site.number_of_vaults || 0);

    const $row = $(`
      <tr style="cursor: pointer;" data-site="${site.name}">
        <td>${frappe.utils.escape_html(site.location_name || site.name)}</td>
        <td>${frappe.utils.escape_html(site.locale || "")}</td>
        <td>${frappe.utils.escape_html(site.equipment_type || "")}</td>
        <td class="text-center">${site.number_of_machines || 0}</td>
        <td class="text-center">${site.number_of_primary_lockers || 0}</td>
        <td class="text-center">${site.number_of_secondary_lockers || 0}</td>
        <td class="text-center">${site.number_of_kiosks || 0}</td>
        <td class="text-center">${site.number_of_vaults || 0}</td>
        <td class="text-center">
          <button class="btn btn-xs btn-danger btn-delete-site"
                  title="Delete">&times;</button>
        </td>
      </tr>
    `).appendTo($tbody);

    // Click row -> navigate to site form
    $row.on("click", (e) => {
      if ($(e.target).hasClass("btn-delete-site")) return;
      frappe.set_route("Form", SITE_DOCTYPE, site.name);
    });

    // Delete button
    $row.find(".btn-delete-site").on("click", (e) => {
      e.stopPropagation();
      frappe.confirm(
        `Delete site "${site.location_name || site.name}"?`,
        () => {
          frappe.call({
            method: "frappe.client.delete",
            args: { doctype: SITE_DOCTYPE, name: site.name },
            callback() {
              frappe.show_alert({ message: "Site deleted", indicator: "red" });
              renderSitesTab(frm);
            },
          });
        }
      );
    });
  });
}

function addNewSite(frm) {
  // Save the CRM Deal first if dirty, then navigate to a new site form
  const doNavigate = () => {
    frappe.route_options = { crm_deal: frm.doc.name };
    frappe.set_route("Form", SITE_DOCTYPE, "new");
  };

  if (frm.dirty()) {
    frm.save().then(doNavigate);
  } else {
    doNavigate();
  }
}

// ---------------------------------------------------------------------------

frappe.ui.form.on("CRM Deal", {
  refresh(frm) {
    renderSitesTab(frm);
  },
});
