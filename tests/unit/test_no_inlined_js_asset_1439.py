"""#1439 (ADR-0003): a full JavaScript asset must live in `static/js/` and be served,
never inlined as a Python string literal.

The canonical violation was `page/runtime/realtime_client.py`'s 974-line module — a
900+-char `_REALTIME_CLIENT_JS_INLINE` blob plus `REALTIME_CLIENT_JS` alias and
`get_realtime_client_js()` wrapper — a second source of truth that drifted from (and
outlived) the `static/js/realtime.js` it duplicated. The HTMX/SSE migration orphaned
the whole module; it was deleted in v0.83.81.

This gate keeps that class from returning: no `.py` under `src/dazzle` may embed a
large (>= 4 KB) string literal that is recognisably a JavaScript program. Small inline
snippets (a handful of event-handler lines in a renderer) stay under the threshold;
a full client asset trips it and must be moved to `static/js/` and served.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "src" / "dazzle"
_THRESHOLD = 4000  # chars — well above any legitimate inline snippet, below a real asset
_JS_MARKERS = ("addEventListener", "querySelector", "new WebSocket", "document.create")


def _inlined_js_blobs(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) >= _THRESHOLD
            and "function" in node.value
            and any(m in node.value for m in _JS_MARKERS)
        ):
            out.append(f"{path}:{node.lineno} ({len(node.value)} chars)")
    return out


def test_no_full_js_asset_inlined_in_python() -> None:
    offenders: list[str] = []
    for p in _ROOT.rglob("*.py"):
        offenders.extend(_inlined_js_blobs(p))
    assert not offenders, (
        "A full JavaScript asset is inlined as a Python string literal (ADR-0003 / #1439). "
        "Move it to `static/js/` and serve it — an inlined copy becomes a second source of "
        "truth that drifts (cf. the deleted realtime_client.py):\n  " + "\n  ".join(offenders)
    )
