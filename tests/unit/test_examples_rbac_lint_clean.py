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

# Framework examples that ship as part of the canonical adopter-facing
# demo set. Each must pass its own lint as part of the dogfood gate.
# New examples added to `examples/` are caught by `test_every_examples_dir_under_lint`.
_KNOWN_EXAMPLES = [
    "simple_task",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
    "contact_manager",
    # #1174 — multi-tenant billing app. Canonical adversarial-RBAC
    # teaching example: direct-equality, FK-path, EXISTS-via-junction
    # and compound (`!=`) scope rules, exercised by the adversarial
    # suite in tests/integration/test_acme_billing_rbac.py.
    "acme_billing",
    # #1184 — multi-tenant invoice-approval / payment-ops keystone
    # example. Teaches admin_personas cross-tenant bypass, approval
    # gates, and the postgres:// URL scheme alias. Exercised by the
    # adversarial isolation suite in
    # tests/integration/test_invoice_ops_tenant_isolation.py.
    "invoice_ops",
]

# Examples that live under `examples/` but are NOT covered by the dogfood
# gate — usually because they're topic-focused demos or kitchen-sink
# fixtures rather than canonical RBAC teaching apps. v0.71.57 moved the
# previously-fixture demos into examples/; they keep their original purpose
# (showcase one capability) and don't claim to teach the write-op scope
# idiom. Each entry needs a one-line rationale.
_DOGFOOD_EXEMPT = {
    # UX component expansion demo (Quill/Flatpickr/Tom Select). RBAC is
    # standard but the focus is widget integration, not the scope idiom.
    "project_tracker",
    # Brand/asset management demo. Same shape as project_tracker.
    "design_studio",
    # LLM intent demo — focus is classification + extraction, not RBAC.
    "llm_ticket_classifier",
    # #1217 Phase 2/3 design-pressure surface for temporal / SCD support.
    # The example is deliberately incomplete in places (TODO blocks marking
    # desired-syntax for unimplemented temporal features); RBAC is present
    # but the example exists to surface Phase 3 gaps, not teach RBAC.
    "hr_records",
}


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


@pytest.mark.parametrize("example_name", _KNOWN_EXAMPLES)
def test_example_routes_are_matrix_complete(example_name: str) -> None:
    """#1420 Slice 3 / ADR-0040 D3 — no example may carry a custom route-override
    that escapes the RBAC matrix (an unbound override shadowing a generated route,
    or a `# dazzle:implements` binding naming an entity/op the AppSpec lacks).
    The framework-side form of the `dazzle rbac routes --strict` CI gate."""
    from dazzle.back.converters.surface_converter import convert_surfaces_to_services
    from dazzle.back.runtime.route_overrides import (
        discover_route_overrides,
        verify_route_matrix_completeness,
    )

    project_root = EXAMPLES_DIR / example_name
    if not project_root.exists():
        pytest.skip(f"Example directory missing: {project_root}")

    appspec = load_project_appspec(project_root)
    overrides = discover_route_overrides(project_root / "routes")
    _services, endpoints = convert_surfaces_to_services(appspec.surfaces, appspec.domain)
    generated = {(ep.method.value, ep.path) for ep in endpoints}
    violations = verify_route_matrix_completeness(appspec, overrides, generated)
    assert violations == [], (
        f"Example `{example_name}` route(s) escape the RBAC matrix:\n" + "\n".join(violations)
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
    accounted_for = set(_KNOWN_EXAMPLES) | _DOGFOOD_EXEMPT
    missing = sorted(set(discovered) - accounted_for)
    assert not missing, (
        f"New examples added to `examples/` are not covered by the RBAC "
        f"dogfood gate: {missing}. Either add them to `_KNOWN_EXAMPLES` "
        f"in this file (and ensure each passes the per-example test), "
        f"or — if the example is a topic-focused demo that doesn't claim "
        f"to teach the canonical write-op scope idiom — add it to "
        f"`_DOGFOOD_EXEMPT` with a one-line rationale."
    )
