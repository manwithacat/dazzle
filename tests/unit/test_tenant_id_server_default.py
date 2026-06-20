"""The injected tenant_id column gets a current_setting server_default (Plan 1d)."""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names


def test_scoped_partition_key_has_current_setting_default() -> None:
    appspec = load_project_appspec(Path("fixtures/tenant_rls"))
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(
        convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped
    )

    project = md.tables["Project"]  # a scoped entity
    col = project.columns[pk]
    assert col.server_default is not None
    sql_text = str(col.server_default.arg)
    assert "current_setting('dazzle.tenant_id', true)" in sql_text
    assert "::" in sql_text  # explicit cast present
    # #1400: the read is NULLIF-wrapped so a pooled empty-string GUC routes to a
    # NOT NULL violation (fail-closed) rather than a raising ''::<type> cast.
    assert "NULLIF(current_setting('dazzle.tenant_id', true), '')::" in sql_text

    # The tenant root (Workspace) is NOT scoped → no current_setting default.
    ws = md.tables["Workspace"]
    ws_default = ws.columns["id"].server_default
    assert ws_default is None or "current_setting" not in str(ws_default.arg)


def test_non_tenant_build_is_unchanged() -> None:
    # Without partition_key/tenant_scoped, no current_setting default anywhere.
    appspec = load_project_appspec(Path("fixtures/tenant_rls"))
    md = build_metadata(convert_entities(appspec.domain.entities))
    for table in md.tables.values():
        for col in table.columns:
            if col.server_default is not None:
                assert "current_setting('dazzle.tenant_id'" not in str(col.server_default.arg)
