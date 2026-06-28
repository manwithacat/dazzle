"""Detector behaviour for the spec-narrative pipeline."""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.spec_narrative.detectors import (
    REGISTRY,
    always,
    has_database_rls,
    has_rls,
    is_multi_tenant,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(rel: str):
    return load_project_appspec(REPO_ROOT / rel)


def test_has_rls_fires_for_scoped_fixture():
    assert has_rls(_load("fixtures/rbac_validation")) is True


def test_has_rls_false_for_plain_app():
    # custom_renderer is a scope-free probe fixture (no `scope:` rules).
    assert has_rls(_load("fixtures/custom_renderer")) is False


def test_has_database_rls_requires_shared_schema_tenancy():
    # tenant_rls uses shared_schema tenancy → real Postgres RLS.
    assert has_database_rls(_load("fixtures/tenant_rls")) is True
    # rbac_validation has scope rules but NO tenancy → app-layer filtering only,
    # NOT database-enforced RLS. This is the false-positive the split prevents.
    assert has_rls(_load("fixtures/rbac_validation")) is True
    assert has_database_rls(_load("fixtures/rbac_validation")) is False


def test_is_multi_tenant_fires_for_tenant_fixture():
    assert is_multi_tenant(_load("fixtures/tenant_rls")) is True


def test_always_is_always_true():
    assert always(_load("examples/simple_task")) is True


def test_registry_values_are_callable_and_return_bool():
    app = _load("examples/simple_task")
    for name, fn in REGISTRY.items():
        result = fn(app)
        assert isinstance(result, bool), f"{name} did not return bool"
