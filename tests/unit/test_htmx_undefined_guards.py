"""Tests for #980 — guard against `htmx is not defined` race in JS callsites.

Background: htmx.min.js and dz-utils.js both use `defer`, so document
order should make htmx available — but cache misses, extension-loaded
scripts, or aggressive script blockers can race. Several Alpine
component methods call `htmx.ajax(...)` directly in user-event handlers;
without a guard the user gets a silent ReferenceError mid-action.

Fix per #980: every `htmx.ajax(...)` / `htmx.process(...)` /
`htmx.swap(...)` call in dz-utils.js or other dz JS files must be
guarded by a `typeof htmx !== "undefined"` check (or be inside a
function that early-returns when htmx is missing). This test scans
the JS for un-guarded uses.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_DIR = REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "js"

# Match `htmx.X(` calls (htmx.ajax, htmx.process, htmx.swap, etc.).
# Skip the property-access form `htmx.config` since it's a read, not a call.
_HTMX_CALL_RE = re.compile(r"\bhtmx\.([a-z]+)\(")

# Match the canonical guard expression in any of these forms:
#   typeof htmx === "undefined"
#   typeof htmx === 'undefined'
#   typeof htmx !== "undefined"
#   typeof htmx !== 'undefined'
_HTMX_GUARD_RE = re.compile(r"typeof\s+htmx\s+[!=]==\s+['\"]undefined['\"]")


def _strip_comments(text: str) -> str:
    """Strip JS line + block comments so guard text inside docs doesn't
    confuse the gate. Conservative — handles `//` and `/* ... */`."""
    # Block comments first.
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    # Line comments.
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _find_htmx_calls(js: str) -> list[tuple[int, str]]:
    """Return list of (line_no, call_text) for every htmx.X(...) call."""
    out = []
    for match in _HTMX_CALL_RE.finditer(js):
        line_no = js[: match.start()].count("\n") + 1
        # Snippet for diagnostics.
        line_start = js.rfind("\n", 0, match.start()) + 1
        line_end = js.find("\n", match.end())
        snippet = js[line_start:line_end].strip()
        out.append((line_no, snippet))
    return out


def _is_guarded(js: str, call_pos: int, *, window: int = 1500) -> bool:
    """Check if the htmx call at `call_pos` is preceded by a guard within
    `window` chars (covers a typical function body). The guard pattern
    is permissive: any `typeof htmx [!=]== "undefined"` in the preceding
    block counts."""
    start = max(0, call_pos - window)
    block = js[start:call_pos]
    return bool(_HTMX_GUARD_RE.search(block))


def test_every_htmx_call_in_served_js_is_guarded() -> None:
    """Every htmx.X(...) call in a served dz JS file must be preceded by a guard.

    Scans the whole static/js tree, so a call added to any file is covered
    (dz-utils.js, the file #980 named, no longer calls htmx at all).
    """
    scanned = 0
    unguarded: list[str] = []
    for path in sorted(JS_DIR.glob("*.js")):
        raw = path.read_text()
        js = _strip_comments(raw)
        for match in _HTMX_CALL_RE.finditer(js):
            scanned += 1
            if not _is_guarded(js, match.start()):
                call_text_idx = raw.find(match.group(0), max(0, match.start() - 50))
                line_no = raw[:call_text_idx].count("\n") + 1 if call_text_idx >= 0 else 0
                unguarded.append(f"{path.name}:~{line_no}: htmx.{match.group(1)}(...)")
    assert scanned, "no htmx.X(...) call found in static/js; the scan is probably wrong"
    assert not unguarded, (
        "Unguarded `htmx.X(...)` calls (#980: silent ReferenceError on a "
        "script-load-order race):\n"
        + "\n".join(f"  - {u}" for u in unguarded)
        + '\n\nWrap each in `if (typeof htmx === "undefined") return;` '
        "or a similar early-return guard."
    )
