"""ensure_missing_entity_columns — dev create_all twin for DSL field adds."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from sqlalchemy import create_engine, inspect

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.sa_schema import build_metadata, ensure_missing_entity_columns

ROOT = Path(__file__).resolve().parents[2]


def test_ensure_missing_entity_columns_adds_nullable_dsl_fields(tmp_path) -> None:
    """Existing table missing a nullable DSL column is ALTER-ed on ensure."""
    appspec = load_project_appspec(ROOT / "examples" / "invoice_ops")
    entities = list(appspec.domain.entities)
    metadata = build_metadata(entities, surfaces=list(appspec.surfaces))

    # Fresh sqlite file: create tables from a *stripped* User without department.
    url = f"sqlite:///{tmp_path / 't.db'}"
    engine = create_engine(url)
    # Create only a subset of columns to simulate pre-org_structure schema.
    from sqlalchemy import Column, MetaData, Table, Text

    stale = MetaData()
    Table(
        "User",
        stale,
        Column("id", Text(), primary_key=True),
        Column("email", Text(), nullable=False),
        Column("name", Text(), nullable=False),
        Column("tenant_id", Text(), nullable=False),
        Column("created_at", Text(), nullable=True),
    )
    # Also need Tenant for FK-free sqlite path — skip full FK graph.
    stale.create_all(engine)

    before = {c["name"] for c in inspect(engine).get_columns("User")}
    assert "department" not in before
    assert "job_title" not in before

    # Build metadata for User alone matching live shape + new cols via full meta
    # ensure against full appspec metadata (only alters existing User table).
    added = ensure_missing_entity_columns(engine, metadata)
    assert any(a.endswith(".department") for a in added), added
    assert any(a.endswith(".job_title") for a in added), added

    after = {c["name"] for c in inspect(engine).get_columns("User")}
    assert "department" in after
    assert "job_title" in after

    # Idempotent second pass.
    again = ensure_missing_entity_columns(engine, metadata)
    assert again == [] or all("department" not in a and "job_title" not in a for a in again)

    engine.dispose()


def test_ensure_missing_entity_columns_no_op_when_fresh(tmp_path) -> None:
    appspec = load_project_appspec(ROOT / "examples" / "simple_task")
    metadata = build_metadata(list(appspec.domain.entities), surfaces=list(appspec.surfaces))
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    metadata.create_all(engine)
    added = ensure_missing_entity_columns(engine, metadata)
    assert added == []
    engine.dispose()
