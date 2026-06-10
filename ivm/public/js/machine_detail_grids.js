/**
 * Shared machine grid setup and bins editor.
 *
 * Used by both Project and CRM Deal forms for the deployment_smart*_details
 * child tables.
 */

/**
 * Disable inline grid editing and add CSS class for machine tables.
 * @param {object} frm - The form object
 * @param {string[]} tableFieldnames - The child table fieldnames to set up
 */
function setupMachineDetailGrids(frm, tableFieldnames) {
  tableFieldnames.forEach(fieldname => {
    const grid = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].grid;
    if (!grid) return;
    grid.allow_on_grid_editing = () => false;
    grid.wrapper.addClass('ivm-machine-detail-grid');
  });
}

/**
 * Inject the bins editor UI into a SmartLocker or SmartSync child table row.
 */
function injectBinsEditor(frm, cdt, cdn) {
  const $wrapper = cur_frm?.cur_grid?.grid_form?.wrapper;
  if (!$wrapper || $wrapper.find('.ivm-bins-injected').length) return;

  const $container = $('<div class="ivm-bins-injected" style="padding: 10px 15px 5px;"></div>');
  $wrapper.find('[data-fieldname="bins_data"]').hide().after($container);

  const row = frappe.get_doc(cdt, cdn);
  let existing = [];
  try { existing = row.bins_data ? JSON.parse(row.bins_data) : []; } catch(e) {}

  $container.html(`
    <table class="table table-bordered table-sm mb-2">
      <thead><tr>
        <th style="width:90px">Type</th>
        <th style="width:70px">#</th>
        <th style="width:80px">Size (Inches)</th>
        <th style="width:40px"></th>
      </tr></thead>
      <tbody class="ivm-bins-body"></tbody>
    </table>
    <button class="btn btn-xs btn-secondary ivm-add-bin">+ Add Row</button>
    <span class="ivm-bins-warning text-danger small ml-2" style="display:none;"></span>
  `);

  function saveBins() {
    const bins = [];
    const seen = new Set();
    let duplicate = null;
    $container.find('.ivm-bin-row').each(function() {
      const $r = $(this);
      const bin_type = $r.find('.ivm-bin-type').val();
      const entry = { bin_type, bin_size: $r.find('.ivm-bin-size').val() };
      if (bin_type === 'Storage') {
        const num = $r.find('.ivm-bin-number').val();
        if (num && seen.has(num)) duplicate = num;
        if (num) seen.add(num);
        entry.bin_number = num;
      }
      bins.push(entry);
    });
    const $warning = $container.find('.ivm-bins-warning');
    if (duplicate) {
      $warning.text(`Bin #${duplicate} is duplicated.`).show();
    } else {
      $warning.hide();
      frappe.model.set_value(cdt, cdn, 'bins_data', JSON.stringify(bins));
    }
  }

  function nextBinNumber() {
    let last = null;
    $container.find('.ivm-bin-row').each(function() {
      if ($(this).find('.ivm-bin-type').val() === 'Storage') {
        const n = parseInt($(this).find('.ivm-bin-number').val());
        if (!isNaN(n)) last = n;
      }
    });
    return last !== null ? String(last + 1) : '';
  }

  function lastRowSize() {
    const $rows = $container.find('.ivm-bin-row');
    return $rows.length ? $rows.last().find('.ivm-bin-size').val() : '4';
  }

  function setNumberState($row, isStorage) {
    const $input = $row.find('.ivm-bin-number');
    if (isStorage) {
      $input.prop('disabled', false).val($input.data('saved') || '').css('color', '');
    } else {
      $input.data('saved', $input.val()).prop('disabled', true).val('N/A').css('color', '#aaa');
    }
  }

  function addRow(bin) {
    const isNew = !bin;
    bin = bin || {};
    const type = bin.bin_type || 'Storage';
    const $row = $(`
      <tr class="ivm-bin-row">
        <td><select class="form-control form-control-sm ivm-bin-type">
          <option value="Storage">Storage</option>
          <option value="PWR">PWR</option>
        </select></td>
        <td><input type="text" inputmode="numeric" class="form-control form-control-sm ivm-bin-number" /></td>
        <td><select class="form-control form-control-sm ivm-bin-size">
          <option>4</option><option>8</option><option>12</option>
        </select></td>
        <td class="ivm-remove-bin-td"><button class="btn btn-xs btn-danger ivm-remove-bin">&times;</button></td>
      </tr>
    `);
    $row.find('.ivm-bin-type').val(type);
    $row.find('.ivm-bin-size').val(isNew ? lastRowSize() : (bin.bin_size || '4'));
    const binNum = isNew && type === 'Storage' ? nextBinNumber() : (bin.bin_number || '');
    $row.find('.ivm-bin-number').val(binNum).data('saved', String(binNum));
    setNumberState($row, type === 'Storage');

    $row.find('.ivm-bin-type').on('change', function() {
      setNumberState($row, $(this).val() === 'Storage');
      saveBins();
    });
    $row.find('.ivm-bin-number, .ivm-bin-size').on('change', saveBins);
    $row.find('.ivm-remove-bin').on('click', () => { $row.remove(); saveBins(); });
    $container.find('.ivm-bins-body').append($row);
  }

  existing.forEach(b => addRow(b));
  if (!existing.length) addRow();
  $container.find('.ivm-add-bin').on('click', () => { addRow(); saveBins(); });
}

/**
 * Validate that machine_name is unique within each device child table.
 * Call from the parent doctype's validate event.
 * @param {object} frm - The form object
 * @param {string[]} tableFieldnames - The child table fieldnames to validate
 */
function validateUniqueMachineNames(frm, tableFieldnames) {
  for (const fieldname of tableFieldnames) {
    const rows = frm.doc[fieldname] || [];
    const seen = new Set();
    for (const row of rows) {
      if (!row.machine_name) continue;
      if (seen.has(row.machine_name)) {
        frappe.throw(
          __('Duplicate machine name "{0}" in {1} (row {2})',
            [row.machine_name, frm.fields_dict[fieldname].df.label, row.idx])
        );
      }
      seen.add(row.machine_name);
    }
  }
}

// Expose globally for use in doctype JS files
Object.assign(window, { setupMachineDetailGrids, injectBinsEditor, validateUniqueMachineNames });
