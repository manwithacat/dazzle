"""HYPERPART: search-select — FK typeahead shell + fixed result-row anatomy.

Two surfaces, one Hyperpart:

1. **Widget shell** — hidden FK + typeahead input + listbox panel. Controller
   only opens/closes (``data-dz-open`` / ``aria-expanded``).
2. **Result rows** — the search exchange returns a *fixed* HTML micro-pattern
   (name / optional secondary / optional media). Domain data *maps into*
   those slots; agents must not invent a new combobox per entity or per media
   shape.

Selection is a second exchange per row (``hx-get`` on the row → confirm
fragment + hidden FK filled server-side). The form posts the hidden input,
never the visible text.
"""

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node

# Widget shell (always present). Result rows are swapped in by the search
# exchange — see DOM_CONTRACT_RESULT_ROW + SearchResultRow.
DOM_CONTRACT = DomContract(
    part="search-select",
    root='[data-dz-widget="search_select"]',
    nodes=(Node('[data-dz-widget="search_select"]', attrs={}),),
)

# Listbox option micro-pattern (search exchange body). Validate against a
# row fragment, not the empty shell.
DOM_CONTRACT_RESULT_ROW = DomContract(
    part="search-select-result",
    root=".dz-search-result-row",
    nodes=(
        Node(".dz-search-result-row", attrs={}),
        Node(".dz-search-result-name", attrs={}),
    ),
)


class SearchResultRow(BaseModel):
    """One listbox option the search exchange emits.

    Map *any* domain record into this shape:

    - ``id`` → select-exchange query param (FK to store)
    - ``name`` → primary line (required for AT + scan)
    - ``secondary`` → optional meta (company no., email, SKU, …)
    - ``media_html`` → optional leading 2rem slot (initials span, ``<img>``,
      icon ``<svg>``). Empty string = text-only row.
    - ``select_url`` / ``results_target`` → the row's own ``hx-get`` wiring
    """

    id: str
    name: str
    secondary: str = ""
    media_html: str = Field(
        default="",
        description="Trusted HTML for the media slot (already escaped/SSR-safe).",
    )
    select_url: str
    results_target: str  # e.g. "#hm-ss-results" or "#search-results-company"


class SearchSelectShell(BaseModel):
    """SSR seed for the typeahead widget (before any search)."""

    field_name: str
    field_id: str = "field"
    input_id: str = "search-input"
    results_id: str = "search-results"
    search_url: str
    placeholder: str = "Search…"
    prompt: str = "Type at least 3 characters to search..."
    initial_value: str = ""
    initial_label: str = ""
    debounce_ms: int = 300
    blur_grace_ms: int = 200
    confirm_dwell_ms: int = 1500


EXEMPLARS: list[SearchResultRow] = [
    SearchResultRow(
        id="co-aurora",
        name="Aurora Energy Ltd",
        secondary="Company no. 09182736 · Utilities",
        select_url="/app/fragments/select?source=companies&id=co-aurora",
        results_target="#search-results-company",
    ),
    SearchResultRow(
        id="user-jd",
        name="Jordan Dias",
        secondary="jordan@acme.example · Ops",
        media_html='<span aria-hidden="true">JD</span>',
        select_url="/app/fragments/select?source=users&id=user-jd",
        results_target="#search-results-assignee",
    ),
    SearchResultRow(
        id="sku-42",
        name="Sensor pack · SP-42",
        secondary="SKU · In stock (14)",
        media_html=(
            '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2">'
            '<rect x="3" y="3" width="18" height="18" rx="2"/>'
            '<path d="M3 9h18M9 21V9"/></svg>'
        ),
        select_url="/app/fragments/select?source=products&id=sku-42",
        results_target="#search-results-product",
    ),
]


def render_result_row(row: SearchResultRow) -> str:
    """Model → one listbox option (the search-exchange fragment unit)."""
    media = ""
    if row.media_html.strip():
        media = f'<div class="dz-search-result-media">{row.media_html}</div>'
    secondary = ""
    if row.secondary:
        secondary = f'<div class="dz-search-result-secondary">{html.escape(row.secondary)}</div>'
    return (
        f'<div class="dz-search-result-row" role="option" '
        f'tabindex="-1" '
        f'data-dz-result-id="{html.escape(row.id, quote=True)}" '
        f'hx-get="{html.escape(row.select_url, quote=True)}" '
        f'hx-target="{html.escape(row.results_target, quote=True)}" '
        f'hx-swap="innerHTML">'
        f"{media}"
        f'<div class="dz-search-result-body">'
        f'<div class="dz-search-result-name">{html.escape(row.name)}</div>'
        f"{secondary}"
        f"</div></div>"
    )


def render_result_list(rows: list[SearchResultRow], *, empty_q: str = "") -> str:
    """Search exchange body: N rows, or the empty prompt."""
    if not rows:
        msg = (
            f'No results found for "{html.escape(empty_q)}"'
            if empty_q
            else "Type at least 3 characters to search..."
        )
        return f'<div class="dz-search-result-empty">{msg}</div>'
    return "".join(render_result_row(r) for r in rows)


def render_shell(shell: SearchSelectShell) -> str:
    """Widget shell only (prompt in the listbox)."""
    return (
        f'<div class="dz-search-select" data-dz-widget="search_select" '
        f'data-dz-blur-grace-ms="{shell.blur_grace_ms}" '
        f'data-dz-confirm-dwell-ms="{shell.confirm_dwell_ms}">'
        f'<input type="hidden" name="{html.escape(shell.field_name, quote=True)}" '
        f'id="{html.escape(shell.field_id, quote=True)}" '
        f'value="{html.escape(shell.initial_value, quote=True)}">'
        f'<input type="text" id="{html.escape(shell.input_id, quote=True)}" '
        f'class="dz-search-select-input" '
        f'placeholder="{html.escape(shell.placeholder, quote=True)}" '
        f'autocomplete="off" role="combobox" aria-expanded="false" '
        f'aria-controls="{html.escape(shell.results_id, quote=True)}" '
        f'aria-autocomplete="list" aria-haspopup="listbox" '
        f'value="{html.escape(shell.initial_label, quote=True)}" '
        f'hx-get="{html.escape(shell.search_url, quote=True)}" '
        f'hx-trigger="keyup changed delay:{shell.debounce_ms}ms" '
        f'hx-target="#{html.escape(shell.results_id, quote=True)}" '
        f'hx-params="q">'
        f'<div id="{html.escape(shell.results_id, quote=True)}" role="listbox" '
        f'class="dz-search-select-results">'
        f'<div class="dz-search-select-prompt" role="option" aria-disabled="true">'
        f"{html.escape(shell.prompt)}</div></div></div>"
    )


# Alias used by build_site / dual-lock exemplar path (first EXEMPLAR → live box).
def render(row: SearchResultRow) -> str:
    return render_result_row(row)


__all__ = [
    "DOM_CONTRACT",
    "DOM_CONTRACT_RESULT_ROW",
    "SearchResultRow",
    "SearchSelectShell",
    "EXEMPLARS",
    "render",
    "render_result_row",
    "render_result_list",
    "render_shell",
]
