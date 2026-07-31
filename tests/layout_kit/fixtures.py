"""Reusable HTML body fragments for L2 actions-column geometry."""

from __future__ import annotations


def actions_column_table_body() -> str:
    """Multi-row table matching product structure + multi-word SM chips."""
    return """
<table class="dz-table-grid" style="width:100%; table-layout: fixed; border-collapse: collapse;">
  <colgroup>
    <col style="width: auto" />
    <col style="width: 8rem" />
    <col style="width: 8rem" />
    <col style="width: 8.5rem" />
    <col style="width: 7rem" />
    <col class="dz-table-col-actions" />
  </colgroup>
  <thead>
    <tr>
      <th class="dz-table-th" scope="col">Title</th>
      <th class="dz-table-th" scope="col">Status</th>
      <th class="dz-table-th" scope="col">Priority</th>
      <th class="dz-table-th" scope="col">Due Date</th>
      <th class="dz-table-th" scope="col">Assigned To</th>
      <th class="dz-table-th dz-table-th-actions" scope="col">Actions</th>
    </tr>
  </thead>
  <tbody>
    <tr class="dz-tr-row">
      <td class="dz-tr-cell">Board-visible: migrate hero CMS</td>
      <td class="dz-tr-cell">In Progress</td>
      <td class="dz-tr-cell">High</td>
      <td class="dz-tr-cell">21 Jul 2026</td>
      <td class="dz-tr-cell">manager</td>
      <td class="dz-tr-actions-cell">
        <div class="dz-tr-actions">
          <button type="button" class="dz-tr-action dz-tr-transition">Review</button>
          <button type="button" class="dz-tr-action dz-tr-transition">Todo</button>
        </div>
      </td>
    </tr>
    <tr class="dz-tr-row">
      <td class="dz-tr-cell">Unassigned backlog: refresh favicon set</td>
      <td class="dz-tr-cell">Todo</td>
      <td class="dz-tr-cell">Low</td>
      <td class="dz-tr-cell">1 Aug 2026</td>
      <td class="dz-tr-cell"></td>
      <td class="dz-tr-actions-cell">
        <div class="dz-tr-actions">
          <button type="button" class="dz-tr-action dz-tr-transition">In Progress</button>
        </div>
      </td>
    </tr>
    <tr class="dz-tr-row">
      <td class="dz-tr-cell">Prepare client kickoff agenda</td>
      <td class="dz-tr-cell">Review</td>
      <td class="dz-tr-cell">Medium</td>
      <td class="dz-tr-cell">18 Jul 2026</td>
      <td class="dz-tr-cell">member</td>
      <td class="dz-tr-actions-cell">
        <div class="dz-tr-actions">
          <button type="button" class="dz-tr-action dz-tr-transition">Done</button>
          <button type="button" class="dz-tr-action dz-tr-transition">In Progress</button>
        </div>
      </td>
    </tr>
  </tbody>
</table>
"""


def actions_resting_icons_body() -> str:
    """Single row: chips + destructive icon (emit order) for resting ghost check."""
    return """
<table class="dz-table-grid" style="width:100%;table-layout:fixed;border-collapse:collapse">
<thead><tr>
  <th class="dz-table-th">Title</th>
  <th class="dz-table-th dz-table-th-actions" scope="col">Actions</th>
</tr></thead>
<tbody>
<tr class="dz-tr-row">
  <td class="dz-tr-cell">Sample</td>
  <td class="dz-tr-actions-cell">
    <div class="dz-tr-actions">
      <button type="button" class="dz-tr-action dz-tr-transition">In Progress</button>
      <button type="button" class="dz-tr-action dz-tr-transition">Review</button>
      <button type="button" class="dz-tr-action is-destructive" aria-label="Delete">×</button>
    </div>
  </td>
</tr>
</tbody></table>
"""


ACTIONS_COLUMN_MEASURE_JS = """() => {
  const th = document.querySelector('.dz-table-th-actions');
  if (!th) return { error: 'no th' };
  const range = document.createRange();
  range.selectNodeContents(th);
  const thText = range.getBoundingClientRect();
  const thBox = th.getBoundingClientRect();
  const stripCs = getComputedStyle(document.querySelector('.dz-tr-actions'));
  const chipCs = getComputedStyle(
    document.querySelector('.dz-tr-action.dz-tr-transition')
  );
  const multi = [...document.querySelectorAll('.dz-tr-transition')]
    .find(b => (b.textContent || '').trim().includes(' '));
  const multiW = multi ? multi.getBoundingClientRect().width : null;
  const rows = [];
  for (const td of document.querySelectorAll('.dz-tr-actions-cell')) {
    const strip = td.querySelector('.dz-tr-actions');
    const last = strip && strip.lastElementChild;
    if (!last) continue;
    const lr = last.getBoundingClientRect();
    rows.push({
      lastChipRight: lr.right,
      lastChipLeft: lr.left,
      thTextRight: thText.right,
      thRight: thBox.right,
      tdRight: td.getBoundingClientRect().right,
      deltaToHeaderText: lr.right - thText.right,
      deltaToCellRight: td.getBoundingClientRect().right - lr.right,
    });
  }
  return {
    stripDisplay: stripCs.display,
    stripJustify: stripCs.justifyContent,
    stripWidth: stripCs.width,
    chipWidthCss: chipCs.width,
    multiWordChipPx: multiW,
    rows,
  };
}"""


RESTING_ICONS_MEASURE_JS = """() => {
  const th = document.querySelector('.dz-table-th-actions');
  const range = document.createRange();
  range.selectNodeContents(th);
  const thTextRight = range.getBoundingClientRect().right;
  const row = document.querySelector('.dz-tr-row');
  const chips = row.querySelectorAll('.dz-tr-transition');
  const lastChip = chips[chips.length - 1];
  const icon = row.querySelector('.dz-tr-action.is-destructive');
  if (!lastChip || !icon) return { error: 'missing chip or icon' };
  const chipR = lastChip.getBoundingClientRect();
  const iconR = icon.getBoundingClientRect();
  return {
    deltaChipToHeader: chipR.right - thTextRight,
    iconWidth: iconR.width,
    iconHeight: iconR.height,
    chipRight: chipR.right,
    thTextRight,
  };
}"""


# Cycle 1546 — measure.shell: app ≥ product content measure max-width.
SHELL_MEASURE_BODY = """
<main class="dz-app-main" id="main-product" data-dz-measure="product">
  <p>product measure</p>
</main>
<main class="dz-app-main" id="main-app" data-dz-measure="app">
  <p>app measure</p>
</main>
<main class="dz-app-main" id="main-wide" data-dz-measure="wide">
  <p>wide measure</p>
</main>
<main class="dz-app-main" id="main-full">
  <p>full bleed (no data-dz-measure)</p>
</main>
"""

SHELL_MEASURE_JS = """() => {
  const read = (id) => {
    const el = document.getElementById(id);
    if (!el) return { error: 'missing ' + id };
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      maxWidthCss: cs.maxWidth,
      widthPx: r.width,
      measure: el.getAttribute('data-dz-measure'),
    };
  };
  return {
    product: read('main-product'),
    app: read('main-app'),
    wide: read('main-wide'),
    full: read('main-full'),
  };
}"""


# Cycle 1538 — overflow.cell_no_stack: multi-chip rows stay one baseline.
CHIP_STRIP_BASELINE_MEASURE_JS = """() => {
  const strips = [...document.querySelectorAll('.dz-tr-actions')];
  if (!strips.length) return { error: 'no .dz-tr-actions strips' };
  const rows = [];
  for (const strip of strips) {
    const cs = getComputedStyle(strip);
    const kids = [...strip.children].filter(
      (el) => el.getBoundingClientRect().width > 0.5
    );
    if (kids.length < 2) continue;
    const tops = kids.map((el) => el.getBoundingClientRect().top);
    rows.push({
      childCount: kids.length,
      tops,
      flexWrap: cs.flexWrap,
      flexDirection: cs.flexDirection,
    });
  }
  if (!rows.length) return { error: 'no multi-child action strips' };
  return { rows };
}"""
