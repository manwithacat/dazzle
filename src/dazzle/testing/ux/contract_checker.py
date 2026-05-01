"""Contract checker — HTML assertion engine for UX contracts.

Parses rendered HTML and asserts it matches the contract's expected DOM
structure.  The function ``check_contract`` mutates the contract's *status*
and *error* fields and returns it.
"""

from __future__ import annotations

from html.parser import HTMLParser

from dazzle.testing.ux.contracts import (
    Contract,
    CreateFormContract,
    DetailViewContract,
    EditFormContract,
    ListPageContract,
    RBACContract,
    WorkspaceContract,
)
from dazzle.testing.ux.htmx_client import _extract_workspace_layout, parse_html

# ---------------------------------------------------------------------------
# Shape-nesting gate (issue #794)
# ---------------------------------------------------------------------------

# A "card chrome" is a visual card layer — has rounded corners AND a
# border or background. Two nested chrome layers read as "card within a
# card," which is the regression we want to catch.
_ROUNDED_CLASSES = (
    "rounded",
    "rounded-sm",
    "rounded-md",
    "rounded-lg",
    "rounded-xl",
    "rounded-2xl",
    "rounded-3xl",
    "rounded-full",
)


def _is_rounded_class(cls: str) -> bool:
    """Return True if a class represents a rounded-corner utility.

    Accepts both Tailwind's fixed-scale forms (``rounded``, ``rounded-md``,
    ``rounded-full``) and arbitrary-value forms (``rounded-[4px]``,
    ``rounded-[12px]``) which Dazzle's own templates use via
    ``rounded-[6px]`` in the ``region_card`` macro. Side-scoped rounded
    classes (``rounded-t-md``, ``rounded-l-[4px]``) also count.
    """
    if cls in _ROUNDED_CLASSES:
        return True
    # rounded-[...] or rounded-t-[...] / rounded-t-md etc.
    return cls.startswith("rounded-")


def _is_side_border_class(cls: str) -> bool:
    """Return True for side-scoped border classes (e.g. ``border-l-4``,
    ``border-t-[hsl(var(--primary))]``). These are accent lines, not
    a card edge, and should not count as card-chrome surface.
    """
    for side in ("border-l-", "border-r-", "border-t-", "border-b-", "border-x-", "border-y-"):
        if cls.startswith(side):
            return True
    return False


def _has_card_chrome(class_attr: str | None) -> bool:
    """Return True if a class string represents a visible card layer —
    a rounded element with a **full border** (the defining edge of a
    card surface).

    A bg-only rounded element is not chrome: it could be a progress
    bar track (``rounded-full bg-muted``), a kanban column backdrop
    (``rounded-[6px] bg-muted/0.4``), or a decorative tile. A card
    reads as a card because of its edge, not its fill. So we require
    a non-side border to flag the element as card chrome.

    Side-scoped borders (``border-l-4``, ``border-t-red-500``) are
    accents, not a card edge, and explicitly excluded.
    """
    if not class_attr:
        return False
    classes = class_attr.split()
    has_rounded = any(_is_rounded_class(c) for c in classes)
    if not has_rounded:
        return False
    has_full_border = any(
        c == "border" or (c.startswith("border-") and not _is_side_border_class(c)) for c in classes
    )
    return has_full_border


class _NestedChromeScanner(HTMLParser):
    """Track a tag stack and flag any chrome layer whose ancestors
    include another chrome layer.

    Reports tuples of ``(outer_tag, inner_tag)`` for each nested pair
    found. Self-closing/void tags are ignored as ancestors since they
    cannot contain other elements.
    """

    _VOID = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
    )

    # Only block-level container tags can visually read as a "card".
    # Status badges (span), buttons, links, form inputs, and table cells
    # are not cards — they're inline / form / tabular elements. Scoping
    # the gate to block containers avoids false positives like a
    # status-badge span inside a region_card (span has bg + rounded,
    # but is visually a pill label, not a card layer).
    _CARD_CANDIDATE_TAGS = frozenset(
        {"div", "article", "section", "aside", "nav", "main", "header", "footer", "li"}
    )

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, bool]] = []  # (tag, is_chrome)
        self.nested: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._VOID:
            return
        attr_map = dict(attrs)
        is_chrome = tag in self._CARD_CANDIDATE_TAGS and _has_card_chrome(attr_map.get("class"))
        if is_chrome:
            for ancestor_tag, ancestor_chrome in self._stack:
                if ancestor_chrome:
                    self.nested.append((ancestor_tag, tag))
                    break
        self._stack.append((tag, is_chrome))

    def handle_endtag(self, tag: str) -> None:
        # Close tags in a resilient way — browsers don't always balance.
        while self._stack and self._stack[-1][0] != tag:
            self._stack.pop()
        if self._stack:
            self._stack.pop()


def find_nested_chromes(html: str) -> list[tuple[str, str]]:
    """Return a list of (outer_tag, inner_tag) for each nested chrome
    pair found. A return of [] means the page has no card-within-a-card
    structures. Exposed for use by workspace and detail contract
    checkers.
    """
    scanner = _NestedChromeScanner()
    scanner.feed(html)
    return scanner.nested


class _DuplicateTitleScanner(HTMLParser):
    """Walk each card chrome container and collect every ``<h1>``..``<h4>``
    text it contains. Exposed via :func:`find_duplicate_titles_in_cards`.

    A card with multiple heading descendants bearing the same text means
    the card header is printed twice — the exact counter AegisMark
    reported for #794 (``page.get_by_text("Grade Distribution") == 3``).
    The #794 second follow-up stripped the duplicate from ``region_card``,
    but nothing was gating against re-introduction.

    The scanner treats a "card" as either:
      - any element carrying ``data-card-id`` (the dashboard slot's
        canonical identifier), OR
      - any chrome-bearing container (rounded + full border) — same
        heuristic the nested-chrome gate uses for consistency.

    Heading text is normalised by stripping and collapsing whitespace
    so that ``<h3>\\n  Grade Distribution  </h3>`` matches
    ``<h3>Grade Distribution</h3>``.
    """

    _HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__()
        # Stack of (tag, is_card, titles_seen_within_card).
        # titles_seen_within_card is a list[str] when the element is a
        # card; None otherwise.
        self._stack: list[tuple[str, bool, list[str] | None]] = []
        # Stack of currently-open heading tags and their accumulating text.
        self._open_headings: list[list[str]] = []
        # (card_tag, duplicated_title_text) pairs collected at card close.
        self.duplicates: list[tuple[str, str]] = []

    @staticmethod
    def _is_card(tag: str, attrs_map: dict[str, str | None]) -> bool:
        # Dashboard slots are marked with data-card-id.
        if "data-card-id" in attrs_map:
            return True
        # Or any chrome container (rounded + full border).
        if tag in _NestedChromeScanner._CARD_CANDIDATE_TAGS and _has_card_chrome(
            attrs_map.get("class")
        ):
            return True
        return False

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(text.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _NestedChromeScanner._VOID:
            return
        attrs_map = dict(attrs)
        if self._is_card(tag, attrs_map):
            self._stack.append((tag, True, []))
        else:
            self._stack.append((tag, False, None))
        if tag in self._HEADING_TAGS:
            self._open_headings.append([])

    def handle_data(self, data: str) -> None:
        if self._open_headings:
            self._open_headings[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HEADING_TAGS and self._open_headings:
            text = self._normalise("".join(self._open_headings.pop()))
            if text:
                # Attach to every enclosing card that's still open.
                for _t, is_card, titles in self._stack:
                    if is_card and titles is not None:
                        titles.append(text)
        # Pop the tag stack, resilient to unbalanced close tags.
        while self._stack and self._stack[-1][0] != tag:
            self._stack.pop()
        if not self._stack:
            return
        popped_tag, is_card, titles = self._stack.pop()
        if is_card and titles:
            seen: set[str] = set()
            for title in titles:
                if title in seen:
                    self.duplicates.append((popped_tag, title))
                seen.add(title)


def find_duplicate_titles_in_cards(html: str) -> list[tuple[str, str]]:
    """Return ``(card_tag, duplicated_title_text)`` for every card that
    contains the same heading text more than once.

    A result of ``[]`` means every card in the page has at most one
    copy of any given heading. Regression gate for #794's duplicate-
    title finding (``page.get_by_text("Grade Distribution") == 3``):
    the dashboard slot printed the title in its header, the region
    partial printed it again in ``region_card``, so the same heading
    appeared twice inside the outer card.
    """
    scanner = _DuplicateTitleScanner()
    scanner.feed(html)
    return scanner.duplicates


# ---------------------------------------------------------------------------
# Hidden primary-action gate (issue #801 — INV-9)
# ---------------------------------------------------------------------------

# A "primary action" is a destructive/state-changing button a user may
# need to take on a customisable surface (remove a card, delete a row,
# dismiss a notice, close a modal-less panel, …). When these are placed
# inside an ``opacity-0 group-hover:opacity-100`` ancestor — a common
# "keep the toolbar out of the way until the user hovers" idiom — touch
# users can't reach them at all and keyboard users have to know to
# hover with the pointer first. Regression gate for #799 / #801.
import re as _re  # noqa: E402  (kept local so the top-of-file imports stay clean)

_PRIMARY_ACTION_LABEL = _re.compile(
    r"^(remove|delete|dismiss|close|archive|unarchive|disable|deactivate|revoke)\b",
    _re.IGNORECASE,
)

# Ancestors that carry an Alpine conditional are treated as modals/
# menus — their opacity-0 is part of an orchestrated reveal driven by
# ``open`` state, not a hover-only affordance. Skip the gate when any
# ancestor has one of these attrs.
_ALPINE_CONDITIONAL_ATTRS = ("x-show", "x-if", "x-cloak")

# A non-hover reveal path means keyboard/touch users can also reach
# the action — seeing any of these alongside an opacity-0 class is
# enough to pass the gate.
_NON_HOVER_REVEAL_PREFIXES = (
    "focus-within:opacity-",
    "focus:opacity-",
    "peer-focus:opacity-",
    "group-focus:opacity-",
    "group-focus-within:opacity-",
)

_HOVER_REVEAL_PREFIXES = (
    "group-hover:opacity-",
    "hover:opacity-",
    "peer-hover:opacity-",
)


def _classify_opacity_visibility(classes: list[str], where: str) -> str | None:
    """Return a reason string if ``classes`` contains ``opacity-0`` and
    no non-hover reveal, or ``None`` if the action is reachable.
    """
    if "opacity-0" not in classes:
        return None
    joined = " ".join(classes)
    if any(p in joined for p in _NON_HOVER_REVEAL_PREFIXES):
        return None
    if any(p in joined for p in _HOVER_REVEAL_PREFIXES):
        return f"{where} opacity-0 revealed only on pointer hover"
    return f"{where} opacity-0 with no reveal — permanently invisible"


class _HiddenPrimaryActionScanner(HTMLParser):
    """Walk the DOM and flag primary-action buttons whose visibility
    path is pointer-hover only.

    Exposed via :func:`find_hidden_primary_actions`. Same tag-stack
    shape as :class:`_NestedChromeScanner` — keeps the scanner family
    consistent for future maintainers.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, dict[str, str | None]]] = []
        self.hidden: list[tuple[str, str]] = []

    @staticmethod
    def _is_primary_action(tag: str, attrs_map: dict[str, str | None]) -> bool:
        aria = attrs_map.get("aria-label") or ""
        if not aria or not _PRIMARY_ACTION_LABEL.match(aria.strip()):
            return False
        if tag == "button":
            return True
        return tag == "a" and attrs_map.get("role") == "button"

    def _under_alpine_conditional(self) -> bool:
        for _tag, attrs in self._stack:
            if any(a in attrs for a in _ALPINE_CONDITIONAL_ATTRS):
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _NestedChromeScanner._VOID:
            return
        attrs_map = dict(attrs)
        if self._is_primary_action(tag, attrs_map) and not self._under_alpine_conditional():
            reason = self._classify(attrs_map)
            if reason:
                label = (attrs_map.get("aria-label") or "").strip()
                self.hidden.append((label, reason))
        self._stack.append((tag, attrs_map))

    def handle_endtag(self, tag: str) -> None:
        while self._stack and self._stack[-1][0] != tag:
            self._stack.pop()
        if self._stack:
            self._stack.pop()

    def _classify(self, btn_attrs: dict[str, str | None]) -> str | None:
        btn_classes = (btn_attrs.get("class") or "").split()
        direct = _classify_opacity_visibility(btn_classes, "button itself")
        if direct:
            return direct
        for ancestor_tag, attrs in reversed(self._stack):
            classes = (attrs.get("class") or "").split()
            reason = _classify_opacity_visibility(classes, f"<{ancestor_tag}> ancestor")
            if reason:
                return reason
        return None


def find_hidden_primary_actions(html: str) -> list[tuple[str, str]]:
    """Return ``(aria_label, reason)`` for each primary-action button
    whose only visibility path is pointer hover (or no reveal at all).

    A primary action is a button (or ``<a role="button">``) whose
    ``aria-label`` starts with Remove / Delete / Dismiss / Close /
    Archive / Unarchive / Disable / Deactivate / Revoke. A result of
    ``[]`` means every such action on the page is reachable by
    keyboard or touch users. Gate for #799 / #801 (INV-9).

    Alpine conditional containers (``x-show`` / ``x-if`` / ``x-cloak``)
    are treated as orchestrated reveals and their ``opacity-0`` is not
    flagged — the gate targets the "keep the toolbar hidden until the
    user hovers the parent card" idiom specifically.
    """
    scanner = _HiddenPrimaryActionScanner()
    scanner.feed(html)
    return scanner.hidden


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Tags = list[tuple[str, dict[str, str | None]]]


def _has_attr_containing(tags: Tags, attr: str, substring: str) -> bool:
    """Return True if any tag has *attr* whose value contains *substring*."""
    for _tag_name, attrs in tags:
        val = attrs.get(attr)
        if val is not None and substring in val:
            return True
    return False


def _has_tag_with_attr(tags: Tags, tag: str, attr: str, value: str) -> bool:
    """Return True if a specific *tag* has *attr* with exact *value*."""
    for tag_name, attrs in tags:
        if tag_name == tag and attrs.get(attr) == value:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-type checkers
# ---------------------------------------------------------------------------


def _check_list_page(contract: ListPageContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Must have data-dazzle-table="Entity" (on a container div, not the table itself)
    if not _has_attr_containing(tags, "data-dazzle-table", contract.entity):
        errors.append(f'Missing element with data-dazzle-table="{contract.entity}" for list page')

    # Must have at least one row with hx-get (clickable row)
    if not _has_attr_containing(tags, "hx-get", f"/app/{contract.entity.lower()}/"):
        # Also accept /tasks style paths
        if not _has_attr_containing(tags, "hx-get", ""):
            errors.append("No clickable rows found (expected hx-get on <tr>)")

    # Note: create link presence depends on the persona's CREATE permission,
    # which is verified by the RBAC create contract. Don't assert it here
    # since the list page may be checked with a LIST-only persona.

    return errors


def _check_create_form(contract: CreateFormContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Must have <form> with hx-post
    if not _has_attr_containing(tags, "hx-post", ""):
        errors.append("Missing <form> with hx-post attribute")

    # Check required fields have inputs
    input_names: set[str] = set()
    for tag_name, attrs in tags:
        if tag_name in ("input", "textarea", "select"):
            name = attrs.get("name")
            if name:
                input_names.add(name)

    for field_name in contract.required_fields:
        if field_name not in input_names:
            errors.append(f"Missing required field input: {field_name}")

    # Must have a submit button
    has_submit = False
    for tag_name, attrs in tags:
        if tag_name == "button" and attrs.get("type") == "submit":
            has_submit = True
            break
    if not has_submit:
        errors.append("Missing submit button")

    return errors


def _check_edit_form(contract: EditFormContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Must have <form> with hx-post or hx-put (edit forms use hx-put)
    has_form = _has_attr_containing(tags, "hx-post", "") or _has_attr_containing(tags, "hx-put", "")
    if not has_form:
        errors.append("Missing <form> with hx-post or hx-put attribute")

    # Must have a submit button
    has_submit = False
    for tag_name, attrs in tags:
        if tag_name == "button" and attrs.get("type") == "submit":
            has_submit = True
            break
    if not has_submit:
        errors.append("Missing submit button")

    return errors


def _check_detail_view(contract: DetailViewContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Check edit link if expected
    if contract.has_edit:
        has_edit = False
        for tag_name, attrs in tags:
            if tag_name == "a":
                href = attrs.get("href", "") or ""
                if "edit" in href.lower():
                    has_edit = True
                    break
        if not has_edit:
            errors.append("Missing edit link (expected <a> with href containing 'edit')")

    # Check delete button if expected
    if contract.has_delete:
        if not _has_attr_containing(tags, "hx-delete", ""):
            errors.append("Missing delete button (expected element with hx-delete attribute)")

    # Check transition buttons
    for transition in contract.transitions:
        parts = transition.split("\u2192")
        if len(parts) == 2:
            target_state = parts[1].strip()
            # Look for hx-put with hx-vals containing the target state
            found = False
            for _tag_name, attrs in tags:
                hx_put = attrs.get("hx-put")
                hx_vals = attrs.get("hx-vals", "") or ""
                if hx_put and target_state in hx_vals:
                    found = True
                    break
            if not found:
                errors.append(
                    f"Missing transition button for {transition} "
                    f"(expected hx-put with hx-vals containing '{target_state}')"
                )

    return errors


def _check_workspace(
    contract: WorkspaceContract,
    tags: Tags,
    html: str | None = None,
) -> list[str]:
    errors: list[str] = []

    # Collect regions from three sources to cover both the classic and
    # post-#948 server-rendered dashboard templates:
    #
    #   1. `data-dz-region-name` attributes — classic non-dashboard workspaces
    #      and any region wrapper still using the legacy attribute.
    #   2. `data-card-region` attributes — dashboard workspaces after the
    #      #948 refactor (`workspace/_content.html` server-renders each card
    #      with `data-card-id` / `data-card-region` / `data-card-col-span`).
    #      The JSON data island and Alpine `<template x-for>` were removed
    #      in that cycle, so this attribute is now the SSR declaration of
    #      record.
    #   3. The `dz-workspace-layout` JSON data island — kept for backward
    #      compatibility with any older template path that still emits it.
    #      Closes the false-positive originally reported in #803.
    found_regions: set[str] = set()
    for _tag_name, attrs in tags:
        region = attrs.get("data-dz-region-name") or attrs.get("data-card-region")
        if region:
            found_regions.add(region)

    if html:
        layout = _extract_workspace_layout(html)
        if isinstance(layout, dict):
            for card in layout.get("cards") or []:
                if isinstance(card, dict):
                    region = card.get("region")
                    if isinstance(region, str):
                        found_regions.add(region)

    for region in contract.regions:
        if region not in found_regions:
            errors.append(
                f"Missing region '{region}' "
                f'(expected element with data-dz-region-name="{region}" '
                f"or an entry in the dz-workspace-layout JSON cards[])"
            )

    return errors


def _check_rbac(contract: RBACContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Determine if the action element is present based on operation type
    operation = contract.operation
    found = False

    if operation in ("create", "CREATE"):
        # Look for create link
        for tag_name, attrs in tags:
            if tag_name == "a":
                href = attrs.get("href", "") or ""
                if "create" in href.lower():
                    found = True
                    break

    elif operation in ("update", "UPDATE"):
        # Look for edit link
        for tag_name, attrs in tags:
            if tag_name == "a":
                href = attrs.get("href", "") or ""
                if "edit" in href.lower():
                    found = True
                    break

    elif operation in ("delete", "DELETE"):
        # Look for delete button
        if _has_attr_containing(tags, "hx-delete", ""):
            found = True

    elif operation in ("list", "LIST"):
        # Look for the entity container (data-dazzle-table or data-entity)
        if _has_attr_containing(tags, "data-dazzle-table", contract.entity):
            found = True
        elif _has_attr_containing(tags, "data-entity", contract.entity):
            found = True

    if contract.expected_present and not found:
        errors.append(
            f"Expected {contract.operation} action for {contract.entity} "
            f"to be present for persona '{contract.persona}', but not found"
        )
    elif not contract.expected_present and found:
        errors.append(
            f"Expected {contract.operation} action for {contract.entity} "
            f"to be absent for persona '{contract.persona}', but it was found"
        )

    return errors


# ---------------------------------------------------------------------------
# Dispatcher map
# ---------------------------------------------------------------------------

_CHECKERS = {
    ListPageContract: _check_list_page,
    CreateFormContract: _check_create_form,
    EditFormContract: _check_edit_form,
    DetailViewContract: _check_detail_view,
    WorkspaceContract: _check_workspace,
    RBACContract: _check_rbac,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_contract(contract: Contract, html: str) -> Contract:
    """Parse *html* and verify it satisfies *contract*.

    Mutates ``contract.status`` and ``contract.error`` in place and returns
    the contract for convenience.

    Workspace and detail-view contracts additionally get a shape-nesting
    pass that flags "card within a card" — a chrome layer (rounded +
    border/background) whose ancestor is also a chrome layer. This
    catches regressions like issue #794.
    """
    tags = parse_html(html)
    checker = _CHECKERS.get(type(contract))
    if checker is None:
        contract.status = "failed"
        contract.error = f"No checker registered for {type(contract).__name__}"
        return contract

    # Workspace checker needs the raw HTML so it can parse the
    # `dz-workspace-layout` JSON data island — the regions declared
    # there are the authoritative source for dashboard workspaces
    # (see #803).
    if isinstance(contract, WorkspaceContract):
        errors = _check_workspace(contract, tags, html)
    else:
        errors = checker(contract, tags)  # type: ignore[operator]

    # Shape-nesting gate — applies to contracts that render a page with
    # visible card layers. List pages show cards too, but the list itself
    # is a table, so we focus on workspaces and detail views where the
    # nested-chrome regression was observed (#794).
    if isinstance(contract, WorkspaceContract | DetailViewContract):
        nested = find_nested_chromes(html)
        if nested:
            pairs = ", ".join(f"{outer}>{inner}" for outer, inner in nested[:3])
            more = f" (+ {len(nested) - 3} more)" if len(nested) > 3 else ""
            errors.append(
                f"Nested card chrome detected — a rounded+bordered/background "
                f"element has an ancestor with the same chrome: {pairs}{more}. "
                f"Card chrome must live on exactly one layer."
            )

        # Hidden primary-action gate (INV-9, issue #801) — flags
        # Remove/Delete/Dismiss/… buttons whose only visibility path
        # is pointer hover, which locks out touch users and hurts
        # keyboard discoverability.
        hidden = find_hidden_primary_actions(html)
        if hidden:
            pairs = ", ".join(f'"{label}" ({reason[:60]})' for label, reason in hidden[:3])
            more = f" (+ {len(hidden) - 3} more)" if len(hidden) > 3 else ""
            errors.append(
                f"Hover-only primary actions detected — {pairs}{more}. "
                f"Primary actions (Remove/Delete/Dismiss/…) must be reachable "
                f"without pointer hover — add focus-within:opacity-* or keep "
                f"the element always visible."
            )

    if errors:
        contract.status = "failed"
        contract.error = "; ".join(errors)
    else:
        contract.status = "passed"
        contract.error = None
    return contract
