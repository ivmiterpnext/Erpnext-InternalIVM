// ---------------------------------------------------------------------------
// Sites tab – table of Deal Location Information docs linked to this CRM Deal
// ---------------------------------------------------------------------------

const SITE_DOCTYPE = "Deployment Location";

const SITE_LIST_FIELDS = [
  "name", "location_name", "locale",
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
// Comments tab – FCRM Notes linked to this CRM Deal
// ---------------------------------------------------------------------------

const NOTES_API = "ivm.deployments.event_handlers.deal_notes";

function renderNotesTab(frm) {
  if (frm.is_new()) return;

  const wrapper = frm.fields_dict.custom_notes_html?.$wrapper;
  if (!wrapper) return;

  wrapper.empty();

  frappe.call({
    method: `${NOTES_API}.get_notes`,
    args: { deal_name: frm.doc.name },
    callback(r) {
      const notes = r.message || [];
      const $container = $('<div class="deal-notes-container"></div>').appendTo(wrapper);

      // New Note button
      $(`<div class="text-right pb-3">
          <button class="btn btn-sm small new-note-btn">
            <svg class="icon icon-sm"><use href="#icon-add"></use></svg>
            ${__("New Note")}
          </button>
        </div>`)
        .appendTo($container)
        .find(".new-note-btn")
        .on("click", () => addDealNote(frm));

      if (!notes.length) {
        $container.append(
          '<div class="text-muted pt-6" style="min-height:100px;text-align:center;">' +
            __("No Notes") +
          "</div>"
        );
        return;
      }

      const $list = $('<div class="all-notes"></div>').appendTo($container);

      notes.forEach((note) => {
        const $row = $(`
          <div class="comment-content p-3 row" data-note="${note.name}"
               style="border:1px solid var(--border-color);border-bottom:none;">
            <div class="mb-2 head col-xs-3">
              <div class="row">
                <div class="col-xs-2">${frappe.avatar(note.owner)}</div>
                <div class="col-xs-10">
                  <div class="font-weight-bold ellipsis" title="${frappe.utils.escape_html(note.owner)}">
                    ${frappe.utils.escape_html(note.owner)}
                  </div>
                  <div class="small text-muted">
                    ${frappe.datetime.global_date_format(note.modified)}
                  </div>
                </div>
              </div>
            </div>
            <div class="col-xs-8">
              <div class="font-weight-bold mb-1">${frappe.utils.escape_html(note.title)}</div>
              <div class="note-content">${note.content || ""}</div>
            </div>
            <div class="col-xs-1 text-right">
              <span class="edit-note-btn btn btn-link" style="padding:0.2rem;">
                <svg class="icon icon-sm"><use xlink:href="#icon-edit"></use></svg>
              </span>
              <span class="delete-note-btn btn btn-link pl-2" style="padding:0.2rem;">
                <svg class="icon icon-xs"><use xlink:href="#icon-delete"></use></svg>
              </span>
            </div>
          </div>
        `).appendTo($list);

        $row.find(".edit-note-btn").on("click", () => editDealNote(frm, note));
        $row.find(".delete-note-btn").on("click", () => deleteDealNote(frm, note));
      });

      // Bottom border on last row
      $list.find(".comment-content:last-child").css("border-bottom", "1px solid var(--border-color)");
    },
  });
}

function addDealNote(frm) {
  const d = new frappe.ui.Dialog({
    title: __("Add a Note"),
    fields: [
      { label: "Title", fieldname: "title", fieldtype: "Data", reqd: 1 },
      { label: "Content", fieldname: "content", fieldtype: "Text Editor", reqd: 1, enable_mentions: true },
    ],
    primary_action(values) {
      frappe.call({
        method: `${NOTES_API}.add_note`,
        args: { deal_name: frm.doc.name, title: values.title, content: values.content },
        freeze: true,
        callback(r) {
          if (!r.exc) {
            renderNotesTab(frm);
          }
          d.hide();
        },
      });
    },
    primary_action_label: __("Add"),
  });
  d.show();
}

function editDealNote(frm, note) {
  const d = new frappe.ui.Dialog({
    title: __("Edit Note"),
    fields: [
      { label: "Title", fieldname: "title", fieldtype: "Data", reqd: 1, default: note.title },
      { label: "Content", fieldname: "content", fieldtype: "Text Editor", default: note.content },
    ],
    primary_action(values) {
      frappe.call({
        method: `${NOTES_API}.edit_note`,
        args: { note_name: note.name, title: values.title, content: values.content },
        freeze: true,
        callback(r) {
          if (!r.exc) {
            renderNotesTab(frm);
            d.hide();
          }
        },
      });
    },
    primary_action_label: __("Done"),
  });
  d.show();
}

function deleteDealNote(frm, note) {
  frappe.confirm(
    __("Delete this note?"),
    () => {
      frappe.call({
        method: `${NOTES_API}.delete_note`,
        args: { note_name: note.name },
        freeze: true,
        callback(r) {
          if (!r.exc) {
            renderNotesTab(frm);
          }
        },
      });
    }
  );
}

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Status filtering – only show statuses matching the deal's pipeline
// (or statuses with no pipeline set, i.e. shared across all pipelines)
// ---------------------------------------------------------------------------

function applyStatusFilter(frm) {
  frm.set_query("status", () => {
    const pipeline = frm.doc.custom_pipeline;
    if (!pipeline) {
      // No pipeline selected – show all statuses
      return {};
    }
    return {
      query: "ivm.deals.queries.get_statuses_for_pipeline",
      filters: { pipeline: pipeline },
    };
  });
}

// ---------------------------------------------------------------------------

function applyDealTypeVisibility(frm) {
  const isExisting = frm.doc.custom_deal_type === "Existing Business";
  frm.toggle_display("custom_client_id", isExisting);
  frm.toggle_reqd("custom_client_id", isExisting);
}

frappe.ui.form.on("CRM Deal", {
  refresh(frm) {
    renderSitesTab(frm);
    renderNotesTab(frm);
    applyStatusFilter(frm);
    applyDealTypeVisibility(frm);

    // "View in HubSpot" button
    if (frm.doc.custom_hubspot_deal_id) {
      frm.add_custom_button(__("View in HubSpot"), () => {
        frappe.xcall(
          "ivm.ivm_integrations.hubspot.hubspot_client.get_hubspot_deal_url",
          { deal_id: frm.doc.custom_hubspot_deal_id }
        ).then((url) => {
          window.open(url, "_blank");
        });
      });
    }
  },

  custom_deal_type(frm) {
    applyDealTypeVisibility(frm);
  },

  custom_pipeline(frm) {
    // Re-apply filter when pipeline changes; clear status if it no longer fits
    applyStatusFilter(frm);
  },
});
