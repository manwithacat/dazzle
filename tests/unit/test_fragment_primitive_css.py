"""CSS coverage test for Fragment renderer primitives.

Every CSS class the Fragment renderer emits MUST have a matching rule
in the bundled stylesheet. New primitive styling lives in
`src/dazzle_ui/runtime/static/css/components/fragment-primitives.css`.

This is a presence test, not a styling-correctness test. Visual
correctness is verified manually in a browser; this test catches the
case where a primitive emits a class that has zero rules.
"""

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CSS_DIR = _REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css"


# Classes the Fragment renderer emits for surfaces simple_task.task_list
# uses (Plan 4 scope). When more surfaces flip in Plan 5+, append here.
_REQUIRED_CLASSES: tuple[str, ...] = (
    # Surface (container with header/body/footer slots)
    "dz-surface",
    "dz-surface__header",
    "dz-surface__body",
    # Heading (level-1 used by Surface header)
    "dz-heading",
    "dz-heading--level-1",
    # Region (kind=list for task_list)
    "dz-region",
    "dz-region--kind-list",
    # Text (default tone — used inside table cells / empty state)
    "dz-text",
    "dz-text--tone-default",
    # Table — Plan 4 scope is "the Fragment Table primitive in a list region".
    # Basic .dz-table styling lives in components/table.css; list-context
    # cascade is added in fragment-primitives.css.
    "dz-table",
)


def _bundled_css_text() -> str:
    """Read every CSS file in the components/ tree + tokens/design-system."""
    parts: list[str] = []
    for path in sorted(_CSS_DIR.rglob("*.css")):
        parts.append(path.read_text())
    return "\n".join(parts)


@pytest.mark.parametrize("css_class", _REQUIRED_CLASSES)
def test_fragment_emitted_class_has_a_css_rule(css_class: str) -> None:
    """Each class in _REQUIRED_CLASSES must appear as a selector somewhere
    in the bundled CSS source files. The bundle script (`build_dist.py`)
    concatenates these, so source-presence equals bundle-presence."""
    css = _bundled_css_text()
    # Match `.<class>` followed by a non-name char (`{`, ` `, `,`, `:`,
    # `>`, `+`, `~`, `[`, or `.`). Catches both standalone selectors and
    # compound ones like `.dz-region--kind-list .dz-table`.
    pattern = re.compile(rf"\.{re.escape(css_class)}(?=[\s,{{:>~+\.\[])")
    matches = pattern.findall(css)
    assert matches, (
        f"CSS class {css_class!r} is emitted by the Fragment renderer "
        f"but has no rule in any source CSS file under {_CSS_DIR}. "
        f"Add a rule in components/fragment-primitives.css."
    )
