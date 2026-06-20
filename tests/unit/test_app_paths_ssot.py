"""#1426 drift gate: the `/app` page-route path formula has ONE home —
``dazzle.page.app_paths``. Route registration and every outbound link must derive
paths from it, so they can't drift into the silent dead-link footgun.

Forbids raw re-derivations creeping back into the page layer:
  * the slug rule ``<name>.lower().replace("_", "-")`` (use ``app_paths.entity_slug``)
  * f-string ``/app`` path construction like ``f"{app_prefix}/{slug}/{id}"``
    (use ``app_paths.list_path`` / ``detail_path`` / ``create_path`` / ``edit_path``)

The plural-redirect SOURCE (``to_api_plural(...).replace("_", "-")``) is a different
formula and is allow-listed.
"""

from pathlib import Path

import pytest

_PAGE_FILES = [
    "src/dazzle/page/converters/template_compiler.py",
    "src/dazzle/http/runtime/page_routes.py",
    "src/dazzle/page/runtime/workspace_renderer.py",
]

_REPO = Path(__file__).resolve().parents[2]


def _code_lines(path: Path):
    """Yield (lineno, line) for non-comment, non-blank source lines."""
    for i, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield i, raw


@pytest.mark.parametrize("rel", _PAGE_FILES)
def test_no_inline_slug_rule(rel):
    """The slug rule must not be inlined — call ``app_paths.entity_slug`` instead.
    Allow-listed: the plural-redirect source (``to_api_plural(...).replace``)."""
    path = _REPO / rel
    offenders = [
        (n, ln.strip())
        for n, ln in _code_lines(path)
        if '.lower().replace("_", "-")' in ln and "to_api_plural" not in ln
    ]
    assert not offenders, (
        f"{rel}: inline slug rule(s) — route through dazzle.page.app_paths.entity_slug:\n"
        + "\n".join(f"  L{n}: {ln}" for n, ln in offenders)
    )


@pytest.mark.parametrize("rel", _PAGE_FILES)
def test_no_raw_app_path_fstrings(rel):
    """No raw f-string ``/app`` path construction — use the app_paths builders."""
    path = _REPO / rel
    offenders = []
    for n, ln in _code_lines(path):
        if 'f"' not in ln and "f'" not in ln:
            continue
        # An f-string that builds an /app route from a slug variable.
        has_prefix = "{app_prefix}/{" in ln or "/app/{" in ln
        builds_path = "/{{id}}" in ln or "/create" in ln or ln.rstrip().endswith('slug}"')
        if has_prefix and builds_path:
            offenders.append((n, ln.strip()))
    assert not offenders, (
        f"{rel}: raw /app path f-string(s) — use dazzle.page.app_paths builders:\n"
        + "\n".join(f"  L{n}: {ln}" for n, ln in offenders)
    )


def test_app_paths_is_importable_and_canonical():
    """The SSOT module exposes exactly the path builders callers depend on."""
    from dazzle.page import app_paths

    for fn in ("entity_slug", "list_path", "create_path", "detail_path", "edit_path"):
        assert callable(getattr(app_paths, fn)), f"app_paths.{fn} missing"
