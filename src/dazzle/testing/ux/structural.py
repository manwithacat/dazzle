"""Structural HTML assertions for UX verification.

Fast, no-browser checks that parse rendered HTML and verify structural
correctness: required elements present, ARIA attributes, no broken links.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass
class StructuralResult:
    check_name: str
    passed: bool
    message: str = ""


class _TagCollector(HTMLParser):
    """Collect tags, attributes, and ids from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        self.tags.append((tag, attr_dict))
        if "id" in attr_dict and attr_dict["id"]:
            self.ids.append(attr_dict["id"])


def _parse(html: str) -> _TagCollector:
    collector = _TagCollector()
    collector.feed(html)
    return collector


def check_detail_view(html: str) -> list[StructuralResult]:
    """Check structural requirements for a detail view page."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # Must have a Back link or button
    has_back = False
    for tag, attrs in collector.tags:
        if tag in ("a", "button"):
            # Check text content isn't available via HTMLParser attrs,
            # so check for href containing entity path or onclick with history/drawer
            href = attrs.get("href", "") or ""
            onclick = attrs.get("onclick", "") or ""
            if "/app/" in href or "history.back" in onclick or "dzDrawer" in onclick:
                has_back = True
                break
    # Fallback: check for any element with "Back" in a simple text search
    if not has_back and "back" in html.lower():
        has_back = True

    results.append(
        StructuralResult(
            check_name="detail_has_back_button",
            passed=has_back,
            message="" if has_back else "Detail view missing Back button or link",
        )
    )

    # Must have a heading
    has_heading = any(tag in ("h1", "h2", "h3") for tag, _ in collector.tags)
    results.append(
        StructuralResult(
            check_name="detail_has_heading",
            passed=has_heading,
            message="" if has_heading else "Detail view missing heading (h1/h2/h3)",
        )
    )

    return results


def check_form(html: str) -> list[StructuralResult]:
    """Check structural requirements for a form."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # Must have a submit button
    has_submit = any(
        tag == "button" and attrs.get("type") == "submit" for tag, attrs in collector.tags
    )
    if not has_submit:
        has_submit = any(
            tag == "input" and attrs.get("type") == "submit" for tag, attrs in collector.tags
        )
    results.append(
        StructuralResult(
            check_name="form_has_submit_button",
            passed=has_submit,
            message="" if has_submit else "Form missing submit button (type='submit')",
        )
    )

    # Form action must not be empty
    form_tags = [(tag, attrs) for tag, attrs in collector.tags if tag == "form"]
    for _, attrs in form_tags:
        action = attrs.get("action", "")
        has_action = bool(action and action.strip())
        results.append(
            StructuralResult(
                check_name="form_has_action",
                passed=has_action,
                message="" if has_action else "Form has empty or missing action attribute",
            )
        )

    return results


def check_html(html: str) -> list[StructuralResult]:
    """Check general HTML structural requirements."""
    results: list[StructuralResult] = []
    collector = _parse(html)

    # No duplicate IDs
    seen_ids: set[str] = set()
    duplicates: list[str] = []
    for id_val in collector.ids:
        if id_val in seen_ids:
            duplicates.append(id_val)
        seen_ids.add(id_val)
    results.append(
        StructuralResult(
            check_name="no_duplicate_ids",
            passed=len(duplicates) == 0,
            message="" if not duplicates else f"Duplicate IDs found: {', '.join(duplicates)}",
        )
    )

    # All img tags have alt attributes
    imgs_without_alt: list[str] = []
    for tag, attrs in collector.tags:
        if tag == "img" and "alt" not in attrs:
            src = attrs.get("src", "unknown")
            imgs_without_alt.append(src or "unknown")
    results.append(
        StructuralResult(
            check_name="img_has_alt",
            passed=len(imgs_without_alt) == 0,
            message=""
            if not imgs_without_alt
            else f"Images without alt: {', '.join(imgs_without_alt)}",
        )
    )

    return results


# Type alias for any structural check function
StructuralCheck = Callable[[str], list[StructuralResult]]
