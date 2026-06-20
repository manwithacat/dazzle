"""archetype: profile generates a (tenant_id, identity_id)-keyed table (Plan 3c)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


def _profile_table():
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    app = load_project_appspec(Path("fixtures/tenant_rls"))
    pk = app.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(app.domain.entities, pk))
    md = build_metadata(
        convert_entities(app.domain.entities), partition_key=pk, tenant_scoped=scoped
    )
    return md.tables["MemberProfile"], scoped


def test_profile_table_has_tenant_identity_unique() -> None:
    t, scoped = _profile_table()
    cols = {c.name for c in t.columns}
    assert {"id", "tenant_id", "identity_id", "display_name"} <= cols
    # MemberProfile is tenant-scoped (carries the injected tenant_id).
    assert "MemberProfile" in scoped
    # The (tenant_id, identity_id) tenant-scoped unique exists (not a global
    # unique on identity_id alone — the same person may have a profile per org).
    uniques = [
        tuple(c.name for c in con.columns)
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert any(set(u) == {"tenant_id", "identity_id"} for u in uniques), uniques
    # And NO standalone global unique on identity_id alone.
    assert not any(set(u) == {"identity_id"} for u in uniques), uniques


def test_is_profile_survives_conversion() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities

    app = load_project_appspec(Path("fixtures/tenant_rls"))
    prof = next(e for e in convert_entities(app.domain.entities) if e.name == "MemberProfile")
    assert prof.is_profile is True
    assert {f.name for f in prof.fields} >= {"identity_id", "tenant_id"}
