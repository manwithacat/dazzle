"""#1845: htmx 2 event names are flagged; framework JS binds the htmx 4 name.

Dazzle bundles htmx 4 (colon event names). A listener on an htmx 2 camelCase
name, or an htmx 2 ``hx-on`` spelling, never fires and nothing reports it.
"""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.core.htmx_event_hygiene import (
    HTMX4_EVENT_RENAMES,
    colon_twin_bound,
    scan_htmx_event_names,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_HTMX = REPO_ROOT / "src/dazzle/page/runtime/static/vendor/htmx.min.js"


@pytest.mark.parametrize(
    ("text", "kind", "legacy", "replacement"),
    [
        (
            'document.addEventListener("htmx:afterSettle", f);',
            "js",
            "htmx:afterSettle",
            "htmx:after:settle",
        ),
        (
            "body.addEventListener('htmx:configRequest', f)",
            "js",
            "htmx:configRequest",
            "htmx:config:request",
        ),
        ("htmx.on(`htmx:beforeSwap`, f)", "js", "htmx:beforeSwap", "htmx:before:swap"),
        ('htmx.on("htmx:load", f)', "js", "htmx:load", "htmx:after:init"),
        ('on("htmx:historyCacheMiss", f)', "js", "htmx:historyCacheMiss", None),
        (
            '<div hx-trigger="htmx:afterSwap from:body">',
            "html",
            "htmx:afterSwap",
            "htmx:after:swap",
        ),
        ('<div hx-on::after-swap="go()">', "html", "hx-on::after-swap", "htmx:after:swap"),
        (
            '<div hx-on:htmx:afterSettle="go()">',
            "html",
            "hx-on:htmx:afterSettle",
            "htmx:after:settle",
        ),
        (
            '<div hx-on--before-request="go()">',
            "html",
            "hx-on--before-request",
            "htmx:before:request",
        ),
        ('<form hx-on::load="go()">', "html", "hx-on::load", "htmx:after:init"),
        (
            'HTML = """<script>document.addEventListener("htmx:configRequest", f)</script>"""',
            "python",
            "htmx:configRequest",
            "htmx:config:request",
        ),
    ],
)
def test_flags_htmx2_names_with_the_htmx4_replacement(
    text: str, kind: str, legacy: str, replacement: str | None
) -> None:
    [finding] = scan_htmx_event_names(text, path="f", kind=kind)  # type: ignore[arg-type]
    assert (finding.legacy, finding.replacement, finding.line) == (legacy, replacement, 1)
    assert f"f:1: `{legacy}`" in finding.message


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ('document.addEventListener("htmx:after:settle", f);', "js"),
        ('x = "htmx:after:viewTransition"; y = "htmx:after:implicitInheritance";', "js"),
        ("// was htmx:afterSettle under htmx 2\n/* htmx:configRequest */", "js"),
        ('<div hx-on::after:swap="go()" hx-on:htmx:config:request="c()">', "html"),
        ('<div hx-on::error="e()" hx-on:click="c()">', "html"),
        ("<!-- htmx:afterSwap -->", "html"),
    ],
)
def test_htmx4_names_and_comments_are_clean(text: str, kind: str) -> None:
    assert scan_htmx_event_names(text, path="f", kind=kind) == []  # type: ignore[arg-type]


def test_findings_carry_line_numbers_past_stripped_comments() -> None:
    text = "/* one\n two */\n// three\nel.addEventListener('htmx:afterSwap', f)\n"
    [finding] = scan_htmx_event_names(text, path="static/js/a.js", kind="js")
    assert (finding.line, finding.column) == (4, 22)
    assert finding.message.startswith("static/js/a.js:4: ")
    assert "dz:region-loaded" in finding.message


def test_every_replacement_is_an_event_the_vendored_htmx_dispatches() -> None:
    bundle = VENDORED_HTMX.read_text(encoding="utf-8")
    for rename in HTMX4_EVENT_RENAMES.values():
        if rename.replacement is not None:
            assert f'"{rename.replacement}"' in bundle, rename
        else:
            assert rename.note, rename  # "no equivalent" always says why


# Framework self-test: would have caught dz-tags.js binding only
# `htmx:afterSettle` (#1845). HaTchi-MaXchi controllers run standalone under
# htmx 2 as well, so an htmx 2 name is allowed only beside its htmx 4 twin.
_FRAMEWORK_JS = [
    *sorted((REPO_ROOT / "src/dazzle/page/runtime/static/js").rglob("*.js")),
    *sorted((REPO_ROOT / "packages/hatchi-maxchi/controllers").rglob("*.js")),
]


@pytest.mark.parametrize("path", _FRAMEWORK_JS, ids=lambda p: p.name)
def test_framework_js_binds_the_htmx4_event_name(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(REPO_ROOT))
    orphans = [
        f.message
        for f in scan_htmx_event_names(text, path=rel, kind="js")
        if not colon_twin_bound(f, text)
    ]
    assert orphans == []


def _project_with_client_files(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    shutil.copytree(
        REPO_ROOT / "examples/simple_task", root, ignore=shutil.ignore_patterns(".dazzle")
    )
    files = {
        "static/js/a11y-fixes.js": 'document.addEventListener("htmx:afterSettle", fix);\n',
        "static/js/ok.js": 'document.addEventListener("htmx:after:settle", fix);\n',
        "static/vendor/old-lib.js": 'on("htmx:afterSwap", f);\n',
        "templates/card.html": '<div hx-on::after-swap="go()"></div>\n',
        "routes/report.py": (
            "# dazzle:route GET /report\n"
            'PAGE = """<script>\n'
            'document.body.addEventListener("htmx:configRequest", addCsrf);\n'
            '</script>"""\n'
        ),
    }
    for rel, body in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body, encoding="utf-8")
    return root


@pytest.mark.parametrize("command", ["lint", "validate"])
def test_lint_and_validate_warn_with_file_line_and_htmx4_name(tmp_path: Path, command: str) -> None:
    root = _project_with_client_files(tmp_path)
    result = CliRunner().invoke(app, [command, "-p", str(root)])
    out = result.output
    assert result.exit_code == 0, out
    assert "static/js/a11y-fixes.js:1: `htmx:afterSettle`" in out
    assert "`htmx:after:settle`" in out
    assert "templates/card.html:1: `hx-on::after-swap`" in out
    assert "routes/report.py:3: `htmx:configRequest`" in out
    assert "`htmx:config:request`" in out
    assert "ok.js" not in out and "old-lib.js" not in out
