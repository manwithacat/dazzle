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
from dazzle.testing.ux.htmx_client import parse_html

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


def _has_card_chrome(class_attr: str | None) -> bool:
    """Return True if a class string represents a visible card layer —
    a rounded element that also has a border or background colour.
    """
    if not class_attr:
        return False
    classes = class_attr.split()
    has_rounded = any(c in _ROUNDED_CLASSES for c in classes)
    if not has_rounded:
        return False
    has_surface = any(
        c == "border" or c.startswith("border-") or c.startswith("bg-") for c in classes
    )
    return has_surface


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

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[tuple[str, bool]] = []  # (tag, is_chrome)
        self.nested: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._VOID:
            return
        attr_map = dict(attrs)
        is_chrome = _has_card_chrome(attr_map.get("class"))
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


def _check_workspace(contract: WorkspaceContract, tags: Tags) -> list[str]:
    errors: list[str] = []

    # Check each expected region.
    # Framework templates emit the namespaced `data-dz-region-name` attribute
    # (matches the `dz` prefix convention used across all runtime data-*).
    found_regions: set[str] = set()
    for _tag_name, attrs in tags:
        region = attrs.get("data-dz-region-name")
        if region:
            found_regions.add(region)

    for region in contract.regions:
        if region not in found_regions:
            errors.append(
                f"Missing region '{region}' "
                f'(expected element with data-dz-region-name="{region}")'
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

    if errors:
        contract.status = "failed"
        contract.error = "; ".join(errors)
    else:
        contract.status = "passed"
        contract.error = None
    return contract
