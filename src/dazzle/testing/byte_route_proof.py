"""Static proof: no route serves stored bytes outside serve_bytes (#1551).

Conservative + fail-safe: flags ANY StreamingResponse / FileResponse /
Response(content=...) in a *routes*.py that is not byte_serving.py and not
in ALLOWLIST. False positives (a legitimate non-storage streamer) are
resolved by adding to ALLOWLIST with a comment — never by loosening the walk.
"""

import ast
from pathlib import Path

# (file stem, function name) pairs allowed to build a streaming response
# outside byte_serving — each a NON-stored-byte streamer with a reason.
ALLOWLIST: set[tuple[str, str]] = {
    # create_static_file_routes serves the posture-gated uploads dir via
    # FileResponse; it is itself the gated static path (#1551 items 1-3).
    ("file_routes", "serve_stored_file"),
    # Prometheus scrape endpoint: returns Prometheus text exposition format,
    # not stored file bytes from Dazzle's document storage.
    ("metrics_routes", "_render_metrics"),
    # HTML fragment utility: generates HTML strings from in-memory content,
    # not stored file bytes.
    ("fragment_routes", "_html"),
    # Framework JS bundle: serves in-process bytes compiled at startup,
    # not stored file bytes.
    ("site_routes", "serve_site_js"),
    # Framework CSS bundle: serves in-process bytes compiled at startup,
    # not stored file bytes.
    ("site_routes", "serve_dazzle_css"),
    # SAML SP metadata endpoint: returns XML generated from the app config,
    # an authentication protocol response, not stored file bytes.
    ("saml_routes", "saml_metadata"),
    # SAML SLS (Single Logout Service): returns plain-text error or logout
    # responses as part of the SAML protocol, not stored file bytes.
    ("saml_routes", "saml_sls"),
    # SAML logout helper: returns a plain-text "logged out" response with
    # cookies cleared, not stored file bytes.
    ("saml_routes", "_logged_out_response"),
    # S3-backed object storage proxy (#942): serves bytes from project-declared
    # [storage.<name>] backends (S3/GCS/etc.) under a prefix-sandbox access
    # model. This is a different subsystem from Dazzle's document storage;
    # it has its own cookie-auth + key-sandbox access controls and does not
    # use the entity-scoped serve_bytes / ByteAudit / AccessDecision path.
    ("proxy_routes", "handler"),
    # Locale setter: returns plain-text 400 error responses for invalid locale
    # tags (validation errors), not stored file bytes.
    ("locale_routes", "set_locale"),
}

_STREAMERS = {"StreamingResponse", "FileResponse"}


def find_byte_route_violations(repo_root: Path) -> list[str]:
    """AST-walk every *routes*.py under src/dazzle/http/runtime/ and return
    a list of human-readable violations: any StreamingResponse / FileResponse /
    Response(content=...) construction that is not in ALLOWLIST.

    Returns an empty list when the boundary is sound.
    """
    runtime = repo_root / "src" / "dazzle" / "http" / "runtime"
    violations: list[str] = []
    for path in runtime.rglob("*routes*.py"):
        if path.name == "byte_serving.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            func = _enclosing_func(tree, node)
            if isinstance(node, ast.Call) and _is_stream_construct(node):
                if (path.stem, func) in ALLOWLIST:
                    continue
                violations.append(
                    f"{path.name}:{getattr(node, 'lineno', '?')} "
                    f"in {func or '<module>'} builds a streaming "
                    f"response outside serve_bytes"
                )
    return violations


def _is_stream_construct(node: ast.Call) -> bool:
    """True when the call constructs a stored-byte response candidate."""
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
    if name in _STREAMERS:
        return True
    if name == "Response":
        return any(kw.arg == "content" for kw in node.keywords)
    return False


def _enclosing_func(tree: ast.AST, target: ast.AST) -> str | None:
    """Return the name of the innermost function that contains *target*."""
    best: str | None = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                getattr(n, "lineno", 0)
                <= getattr(target, "lineno", -1)
                <= getattr(n, "end_lineno", 0)
            ):
                best = n.name
    return best
