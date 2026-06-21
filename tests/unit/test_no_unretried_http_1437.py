"""#1437: outbound HTTP in the runtime/agent layers must be a conscious choice.

Every production outbound request already routes through the retry helper
(`dazzle.core.http_client.async_retrying_request` / `retrying_request`). Raw
`httpx.*` / `requests.*` client-creation or request calls in `src/dazzle/http` and
`src/dazzle/agent` must carry a `# DZ-HTTP-NORETRY <reason>` marker — so a new
un-retried outbound call can't land silently; it has to declare itself (one-shot,
stream, test-agent, or "driven by async_retrying_request below").

This is the enforcement the smells round asked for; the retry-helper itself lives in
`dazzle.core.http_client` (outside the scanned layers).
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOTS = [
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http",
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "agent",
]

# httpx/requests attributes that open a connection or make a request.
_HTTP_CALLS = {
    "AsyncClient",
    "Client",
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "request",
    "stream",
}
_MARKER = "DZ-HTTP-NORETRY"


def _unmarked_http_calls(path: Path) -> list[int]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _HTTP_CALLS:
            continue
        base = node.func.value
        if not (isinstance(base, ast.Name) and base.id in ("httpx", "requests")):
            continue
        # The marker may sit anywhere across the call's span — including the
        # `) as client:  # …` closing line ruff-format produces for a wrapped call —
        # or one line before (the enclosing `with`). Scan the whole span ± a line.
        start = max(0, node.lineno - 2)
        end = (node.end_lineno or node.lineno) + 1
        context = " ".join(lines[start:end])
        if _MARKER not in context:
            hits.append(node.lineno)
    return hits


def test_runtime_http_calls_are_retry_marked() -> None:
    offenders: list[str] = []
    for root in _ROOTS:
        for p in root.rglob("*.py"):
            if "/tests/" in str(p):
                continue
            for ln in _unmarked_http_calls(p):
                offenders.append(f"{p}:{ln}")
    assert not offenders, (
        "Un-marked raw httpx/requests call in the runtime/agent layers (#1437). Route it "
        "through `dazzle.core.http_client.async_retrying_request`/`retrying_request`, or add a "
        "plain `# DZ-HTTP-NORETRY <reason>` comment if it's a deliberate one-shot/stream/test call:\n  "
        + "\n  ".join(offenders)
    )
