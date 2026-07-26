"""Swap / identity contract (ADR-0054, HM decision 0012).

Orthogonal to DomContract dual-lock (part shape). Validates:

* sole ownership of stable ids (no duplicates in a fragment)
* no nested region hooks (data-dz-region inside data-dz-region)
* HTMX *inner* swap responses do not re-own the target slot's identity

Used by ``tools/template_lint.py`` and unit tests. Keep pure stdlib —
no FastAPI / Playwright.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser

from contracts._kit import DomContract, Node, Present

# Surface required by the contract-module sweep (test_contracts.py). This
# module is not a dual-lock Hyperpart — it documents the region *identity*
# substrate that swap/innerHTML fragments must respect (ADR-0054).
DOM_CONTRACT = DomContract(
    part="swap-identity",
    root="[data-dz-region]",
    nodes=(
        Node(
            "[data-dz-region]",
            attrs={"data-dz-region": Present()},
        ),
    ),
)

_ID_RE = re.compile(r"""(?<![A-Za-z0-9_-])id\s*=\s*(["'])(.*?)\1""", re.I | re.DOTALL)


class _RegionDepthParser(HTMLParser):
    """Count nested data-dz-region via a full open-tag stack."""

    def __init__(self) -> None:
        super().__init__()
        self.open: list[tuple[str, bool, str]] = []  # (tag, is_region, name)
        self.violations: list[str] = []
        self._void = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v if v is not None else "") for k, v in attrs}
        is_region = "data-dz-region" in ad
        name = ad.get("data-dz-region-name") or ""
        if is_region:
            for _t, anc_reg, anc_name in self.open:
                if anc_reg:
                    if name and anc_name and name == anc_name:
                        self.violations.append(
                            f"nested data-dz-region name={name!r} inside same name"
                        )
                    else:
                        self.violations.append(
                            f"nested data-dz-region name={name or '(none)'!r} "
                            f"inside name={anc_name or '(none)'!r}"
                        )
                    break
        if tag.lower() not in self._void:
            self.open.append((tag.lower(), is_region, name))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] == t:
                del self.open[i:]
                break


def find_duplicate_ids(html: str) -> list[str]:
    """Return id values that appear more than once (excluding template holes)."""
    ids: list[str] = []
    for m in _ID_RE.finditer(html):
        val = m.group(2).strip()
        if not val or "{{" in val or "{%" in val:
            continue
        ids.append(val)
    counts = Counter(ids)
    return sorted(i for i, n in counts.items() if n > 1)


def find_nested_region_hooks(html: str) -> list[str]:
    """Return human-readable violations for nested data-dz-region hooks."""
    p = _RegionDepthParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 — malformed fixture still report what we have
        pass
    seen: set[str] = set()
    out: list[str] = []
    for v in p.violations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def bare_region_id_for_card_body(target_id: str) -> str | None:
    """If target is ``region-{name}-{card_id}``, return ``region-{name}``.

    Region names in Dazzle DSL use underscores, not hyphens. Card ids are
    typically ``card-N`` or an opaque token after the first ``-`` following
    the region name segment.
    """
    tid = target_id.lstrip("#").strip()
    if not tid.startswith("region-"):
        return None
    body = tid[len("region-") :]
    m = re.match(r"^([a-zA-Z0-9_]+)-(card-.+)$", body)
    if m:
        return f"region-{m.group(1)}"
    m = re.match(r"^([a-zA-Z0-9_]+)-(\d+)$", body)
    if m:
        return f"region-{m.group(1)}"
    parts = body.split("-")
    if len(parts) >= 2 and re.match(r"^[a-zA-Z0-9_]+$", parts[0]):
        return f"region-{parts[0]}"
    return None


def validate_inner_swap_response(response_html: str, target_id: str) -> list[str]:
    """Validate a fragment meant for innerHTML/innerMorph into ``#target_id``.

    Violations:
    * response re-declares ``id=target_id`` (would nest under inner swap)
    * response re-declares bare ``region-{name}`` when target is card body
    * response root is data-dz-region chrome when target is a region slot
    * nested data-dz-region hooks or duplicate ids inside the response
    """
    out: list[str] = []
    tid = target_id.lstrip("#").strip()
    if not tid:
        return out

    ids = [m.group(2).strip() for m in _ID_RE.finditer(response_html)]
    ids = [i for i in ids if i and "{{" not in i]

    if tid in ids:
        out.append(
            f"inner-swap response re-declares id={tid!r} "
            f"(slot already owns this id — return body-only)"
        )

    bare = bare_region_id_for_card_body(tid)
    if bare and bare in ids:
        out.append(
            f"inner-swap response re-declares bare id={bare!r} while target is card body {tid!r}"
        )

    stripped = response_html.lstrip()
    if re.match(r"^<[^>]*\bdata-dz-region\b", stripped, re.I):
        if tid.startswith("region-") or tid.endswith("-body") or "region" in tid:
            out.append(
                "inner-swap response root carries data-dz-region chrome; "
                "slot should own the hook — return typed body only"
            )

    for v in find_nested_region_hooks(response_html):
        out.append(v)

    for dup in find_duplicate_ids(response_html):
        out.append(f"duplicate id={dup!r} inside response fragment")

    return out


def validate_fragment_identity(html: str) -> list[str]:
    """Fragment-level identity checks (no target context)."""
    out: list[str] = []
    for dup in find_duplicate_ids(html):
        out.append(f"duplicate id={dup!r}")
    for v in find_nested_region_hooks(html):
        out.append(v)
    return out


__all__ = [
    "DOM_CONTRACT",
    "bare_region_id_for_card_body",
    "find_duplicate_ids",
    "find_nested_region_hooks",
    "validate_fragment_identity",
    "validate_inner_swap_response",
]
