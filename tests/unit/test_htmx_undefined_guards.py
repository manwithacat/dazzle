"""Tests for #980 — guard against `htmx is not defined` race in JS callsites.

Background: htmx.min.js and dz-alpine.js both use `defer`, so document
order should make htmx available — but cache misses, extension-loaded
scripts, or aggressive script blockers can race. Several Alpine
component methods call `htmx.ajax(...)` directly in user-event handlers;
without a guard the user gets a silent ReferenceError mid-action.

Fix per #980: every `htmx.ajax(...)` / `htmx.process(...)` /
`htmx.swap(...)` call in dz-alpine.js or other dz JS files must be
guarded by a `typeof htmx !== "undefined"` check (or be inside a
function that early-returns when htmx is missing). This test scans
the JS for un-guarded uses.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_DIR = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js"

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


def test_htmx_calls_in_dz_alpine_are_guarded() -> None:
    """Every htmx.X(...) call in dz-alpine.js must be preceded by a guard."""
    path = JS_DIR / "dz-alpine.js"
    raw = path.read_text()
    js = _strip_comments(raw)
    unguarded: list[str] = []
    for match in _HTMX_CALL_RE.finditer(js):
        # Compute line in the original (un-stripped) text using a
        # fingerprint of the call site.
        if not _is_guarded(js, match.start()):
            # Map back to original line via the call's text.
            call_text_idx = raw.find(match.group(0), max(0, match.start() - 50))
            line_no = raw[:call_text_idx].count("\n") + 1 if call_text_idx >= 0 else 0
            unguarded.append(f"line ~{line_no}: htmx.{match.group(1)}(...)")
    assert not unguarded, (
        "Unguarded `htmx.X(...)` calls in dz-alpine.js (#980 — silent "
        "ReferenceError on script-load-order race):\n"
        + "\n".join(f"  - {u}" for u in unguarded)
        + '\n\nWrap each in `if (typeof htmx === "undefined") return;` '
        "or similar early-return guard."
    )


def test_htmx_calls_in_dashboard_builder_are_guarded() -> None:
    """Every htmx.X(...) call in dashboard-builder.js must be guarded."""
    path = JS_DIR / "dashboard-builder.js"
    if not path.exists():
        return
    raw = path.read_text()
    js = _strip_comments(raw)
    unguarded: list[str] = []
    for match in _HTMX_CALL_RE.finditer(js):
        if not _is_guarded(js, match.start()):
            call_text_idx = raw.find(match.group(0), max(0, match.start() - 50))
            line_no = raw[:call_text_idx].count("\n") + 1 if call_text_idx >= 0 else 0
            unguarded.append(f"line ~{line_no}: htmx.{match.group(1)}(...)")
    assert not unguarded, (
        "Unguarded `htmx.X(...)` calls in dashboard-builder.js (#980):\n"
        + "\n".join(f"  - {u}" for u in unguarded)
    )
