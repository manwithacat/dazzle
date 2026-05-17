"""Dogfood gate — every framework example DSL must pass its own RBAC
lint with zero `no_scope_rule` warnings (#1123, v0.71.19).

Pre-v0.71.19, the framework's own example DSLs emitted 56 such
warnings across 4 of the 5 examples — the lint was firing on the
canonical demo code adopters copy as a starting point, which trained
adopters to ignore the warning class as noise.

v0.71.19 ships write-op scope enforcement and updates every example
to declare meaningful `scope: update:` / `scope: delete:` rules. This
test pins the dogfood property: if any future change reintroduces
`no_scope_rule` warnings into an example, this gate fails — the
example must be fixed (with a real scope rule) or annotated (with a
tutorial-only comment + `unprotected_entity` marker if the entity is
genuinely RBAC-free).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.rbac.matrix import generate_access_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"

# All 5 framework examples that ship as part of the canonical
# adopter-facing demo set. Each must pass its own lint as part of
# the dogfood gate. New examples added to `examples/` are caught
# by `test_every_examples_dir_under_lint`.
_KNOWN_EXAMPLES = [
    "simple_task",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
    "contact_manager",
    # v0.71.15 — renderer extension worked example (#1117). Has no
    # permit: rules at all, so no PERMIT_NO_SCOPE warnings can fire —
    # included to keep the discovery gate honest.
    "custom_renderer",
]


@pytest.mark.parametrize("example_name", _KNOWN_EXAMPLES)
def test_example_dsl_has_zero_no_scope_rule_warnings(example_name: str) -> None:
    """No `no_scope_rule` warnings on any of the framework's
    examples. This is the dogfood claim from #1123 — adopters
    reading the examples must see the canonical write-op scope
    idiom, not 56 squashed warnings."""
    project_root = EXAMPLES_DIR / example_name
    if not project_root.exists():
        pytest.skip(f"Example directory missing: {project_root}")

    appspec = load_project_appspec(project_root)
    matrix = generate_access_matrix(appspec)

    no_scope = [w for w in matrix.warnings if w.kind == "no_scope_rule"]
    assert no_scope == [], (
        f"Example `{example_name}` has {len(no_scope)} `no_scope_rule` "
        f"warning(s). The framework dogfoods the canonical write-op "
        f"scope pattern via these examples (#1123) — either add the "
        f"scope rule per `docs/reference/rbac-scope.md`, or if the "
        f"entity is intentionally RBAC-free, annotate it with a "
        f"tutorial-only comment. First three: "
        f"{[f'{w.entity}.{w.operation} ({w.role})' for w in no_scope[:3]]}"
    )


def test_every_examples_dir_under_lint() -> None:
    """Auto-discover any new example added to `examples/` so the
    gate catches it. Lists every subdirectory with a `dazzle.toml`
    and asserts each is named in `_KNOWN_EXAMPLES` (or the test list
    must be updated). Prevents the dogfood gate from silently
    shrinking when a new example is added."""
    discovered = [
        d.name for d in EXAMPLES_DIR.iterdir() if d.is_dir() and (d / "dazzle.toml").exists()
    ]
    missing = sorted(set(discovered) - set(_KNOWN_EXAMPLES))
    assert not missing, (
        f"New examples added to `examples/` are not covered by the RBAC "
        f"dogfood gate: {missing}. Add them to `_KNOWN_EXAMPLES` in this "
        f"file, then ensure each passes the per-example test."
    )
