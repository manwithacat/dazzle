"""WCAG 2.2 AA gate — axe-core over the gallery (console domain).

Scans the full gallery in light AND dark, plus opened-overlay states
(command palette, confirm dialog, dropdown menu), and fails on any
violation of the WCAG A/AA rule tags. Axe "best-practice" rules are
excluded — this gate asserts conformance, not style.

Known manual-only or accepted findings live in ``wcag-allowlist.json``
as {"rule_id": {"selector-substring": "justification"}}. Unknown
violations fail; allowlist entries that no longer fire ALSO fail (the
list can only shrink).

axe-core is vendored (tests/vendor/axe.min.js, MPL-2.0, Deque Systems)
and pinned — bump deliberately.
"""

import json
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
AXE_JS = (PKG / "tests" / "vendor" / "axe.min.js").read_text(encoding="utf-8")
ALLOWLIST_PATH = PKG / "tests" / "wcag-allowlist.json"

WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"]

RUN = (
    f"() => axe.run(document, {{runOnly: {{type: 'tag', values: {json.dumps(WCAG_TAGS)}}}}})"
    ".then(r => r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,"
    " nodes: v.nodes.map(n => n.target.join(' '))})))"
)


def _load_allowlist() -> dict[str, dict[str, str]]:
    if ALLOWLIST_PATH.exists():
        return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {}


def _scan(page) -> list[dict]:  # type: ignore[no-untyped-def]
    page.evaluate(AXE_JS)
    return page.evaluate(RUN)


def _assert_clean(violations: list[dict], state: str) -> None:
    allow = _load_allowlist()
    real = []
    used: set[tuple[str, str]] = set()
    for v in violations:
        allowed_nodes = allow.get(v["id"], {})
        blocked = []
        for node in v["nodes"]:
            hit = next((sel for sel in allowed_nodes if sel in node), None)
            if hit:
                used.add((v["id"], hit))
            else:
                blocked.append(node)
        if blocked:
            real.append({**v, "nodes": blocked})
    assert not real, f"WCAG violations in state {state!r}:\n" + json.dumps(real, indent=1)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_gallery_page_wcag(page, theme) -> None:  # type: ignore[no-untyped-def]
    if theme == "dark":
        page.evaluate("hmTheme('dark')")
        page.wait_for_timeout(150)
    _assert_clean(_scan(page), f"gallery-{theme}")


def test_command_palette_open_wcag(page) -> None:  # type: ignore[no-untyped-def]
    page.click("[data-hm-open-command]")
    page.wait_for_timeout(200)
    _assert_clean(_scan(page), "palette-open")


def test_confirm_dialog_open_wcag(page) -> None:  # type: ignore[no-untyped-def]
    page.click("[hx-confirm]")
    page.wait_for_timeout(200)
    _assert_clean(_scan(page), "confirm-open")


def test_drawer_open_wcag(page) -> None:  # type: ignore[no-untyped-def]
    """The drawer is a bigger overlay surface (header/body/footer); scan it
    open. Native <dialog> + aria-labelledby + a labelled close button."""
    page.click('[data-dialog-open="hm-drawer-demo"]')
    page.wait_for_timeout(200)
    _assert_clean(_scan(page), "drawer-open")


def test_menu_open_wcag(page) -> None:  # type: ignore[no-untyped-def]
    page.evaluate("document.querySelector('details.menu').open = true")
    page.wait_for_timeout(150)
    _assert_clean(_scan(page), "menu-open")


def test_allowlist_entries_all_still_needed(page) -> None:  # type: ignore[no-untyped-def]
    """The allowlist may only shrink: every entry must still fire on the
    default gallery state (or one of the overlay states covered above)."""
    allow = _load_allowlist()
    if not allow:
        return
    fired: set[tuple[str, str]] = set()
    for setup in (
        lambda: None,
        lambda: page.click("[data-hm-open-command]"),
        lambda: page.click("[hx-confirm]"),
    ):
        page.goto(page.url)
        page.wait_for_timeout(200)
        setup()
        page.wait_for_timeout(200)
        for v in _scan(page):
            for node in v["nodes"]:
                for sel in allow.get(v["id"], {}):
                    if sel in node:
                        fired.add((v["id"], sel))
    stale = [
        (rule, sel) for rule, sels in allow.items() for sel in sels if (rule, sel) not in fired
    ]
    assert not stale, f"allowlist entries no longer fire — remove them: {stale}"
