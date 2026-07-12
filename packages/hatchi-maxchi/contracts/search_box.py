"""HYPERPART: search-box — FTS search region (input + aria-live results).

Dual-lock unit is the region root. HTMX endpoint / coaching text are
host-owned; the chrome (input row + live results panel) is dual-locked.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="search-box",
    root="[data-dz-search-box]",
    nodes=(
        Node(
            "[data-dz-search-box]",
            attrs={"data-dz-search-box": Present()},
        ),
    ),
)


class SearchBox(BaseModel):
    """FTS search region shell.

    - ``name`` → field name / results id suffix
    - ``label`` → accessible label (falls back to placeholder)
    - ``placeholder`` → input placeholder (load-bearing for coaching CSS)
    - ``coaching_message`` → empty-state coaching line
    - ``endpoint`` → hx-get target for debounced search
    - ``results_html`` → optional trusted initial results panel body
      (default coaching empty state)
    """

    name: str = "q"
    label: str = ""
    placeholder: str = "Search…"
    coaching_message: str = "Type a title or keyword"
    endpoint: str = ""
    results_html: str = Field(
        default="",
        description="Trusted initial body for the aria-live results panel.",
    )


EXEMPLARS: list[SearchBox] = [
    SearchBox(
        name="records",
        label="Search records",
        placeholder="Search records…",
        coaching_message="Type a title or keyword",
        endpoint="/mock/search",
    ),
    SearchBox(name="empty", endpoint=""),
]


def render(s: SearchBox) -> str:
    """Model → search-box region."""
    results_id = f"dz-search-results-{html.escape(s.name, quote=True)}"
    endpoint = html.escape(s.endpoint, quote=True)
    placeholder = html.escape(s.placeholder or "Search…", quote=True)
    label_text = html.escape(s.label or s.placeholder or "Search")
    coaching = html.escape(s.coaching_message or "Type a title or keyword")
    results_body = s.results_html.strip() or (f'<div class="dz-search-box-empty">{coaching}</div>')
    return (
        f'<div class="dz-search-box-region" data-dz-search-box>'
        f'<div class="dz-search-box-input-row">'
        f'<label for="{results_id}-input" class="visually-hidden">{label_text}</label>'
        f'<input id="{results_id}-input" type="search" name="q" '
        f'class="dz-search-box-input" placeholder="{placeholder}" '
        f'autocomplete="off" '
        f'hx-get="{endpoint}" '
        f'hx-trigger="input changed delay:250ms, search" '
        f'hx-target="#{results_id}" '
        f'hx-swap="innerHTML">'
        f"</div>"
        f'<div id="{results_id}" class="dz-search-box-results" '
        f'role="region" aria-live="polite">'
        f"{results_body}"
        f"</div>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "SearchBox",
    "EXEMPLARS",
    "render",
]
