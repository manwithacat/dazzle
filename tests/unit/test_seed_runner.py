"""Tests for seed runner (#434)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.seed import SeedFieldTemplate, SeedTemplateSpec
from dazzle_back.runtime.seed_runner import _find_uuid_pk_field, run_seed_templates

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(
    name: str, kind: FieldTypeKind, modifiers: list[FieldModifier] | None = None
) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=FieldType(kind=kind),
        modifiers=modifiers or [],
    )


def _make_entity(
    name: str,
    fields: list[FieldSpec],
    seed_template: SeedTemplateSpec | None = None,
) -> MagicMock:
    entity = MagicMock()
    entity.name = name
    entity.fields = fields
    entity.seed_template = seed_template
    return entity


def _make_appspec(entities: list[Any]) -> MagicMock:
    appspec = MagicMock()
    appspec.domain.entities = entities
    return appspec


def _make_repo(existing_items: list[dict[str, Any]] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.list.return_value = {"items": existing_items or []}
    repo.create.return_value = None
    return repo


# ---------------------------------------------------------------------------
# _find_uuid_pk_field
# ---------------------------------------------------------------------------


class TestFindUuidPkField:
    def test_finds_uuid_pk(self) -> None:
        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID, [FieldModifier.PK]),
                _make_field("title", FieldTypeKind.STR),
            ],
        )
        assert _find_uuid_pk_field(entity) == "id"

    def test_non_uuid_pk(self) -> None:
        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.INT, [FieldModifier.PK]),
            ],
        )
        assert _find_uuid_pk_field(entity) is None

    def test_no_pk(self) -> None:
        entity = _make_entity(
            "Task",
            [
                _make_field("id", FieldTypeKind.UUID),
            ],
        )
        assert _find_uuid_pk_field(entity) is None

    def test_no_fields(self) -> None:
        entity = _make_entity("Task", [])
        assert _find_uuid_pk_field(entity) is None

    def test_custom_pk_name(self) -> None:
        entity = _make_entity(
            "Task",
            [
                _make_field("task_id", FieldTypeKind.UUID, [FieldModifier.PK]),
            ],
        )
        assert _find_uuid_pk_field(entity) == "task_id"


# ---------------------------------------------------------------------------
# run_seed_templates — UUID auto-generation
# ---------------------------------------------------------------------------


class TestRunSeedTemplatesUuidGeneration:
    @pytest.mark.asyncio
    async def test_auto_generates_uuid_when_id_missing(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[SeedFieldTemplate(field="name", template="fixed_value")],
        )
        entity = _make_entity(
            "FiscalYear",
            [
                _make_field("id", FieldTypeKind.UUID, [FieldModifier.PK]),
                _make_field("name", FieldTypeKind.STR, [FieldModifier.UNIQUE]),
            ],
            seed_template=seed_tmpl,
        )
        repo = _make_repo()
        appspec = _make_appspec([entity])

        total = await run_seed_templates(appspec, {"FiscalYear": repo})

        assert total > 0
        # Verify create was called with an id field
        call_args = repo.create.call_args[0][0]
        assert "id" in call_args
        # Verify it's a valid UUID string
        uuid.UUID(call_args["id"])

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_id(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[
                SeedFieldTemplate(field="id", template="my-custom-id"),
                SeedFieldTemplate(field="name", template="fixed_value"),
            ],
        )
        entity = _make_entity(
            "FiscalYear",
            [
                _make_field("id", FieldTypeKind.UUID, [FieldModifier.PK]),
                _make_field("name", FieldTypeKind.STR, [FieldModifier.UNIQUE]),
            ],
            seed_template=seed_tmpl,
        )
        repo = _make_repo()
        appspec = _make_appspec([entity])

        await run_seed_templates(appspec, {"FiscalYear": repo})

        call_args = repo.create.call_args[0][0]
        # Should keep the template-provided id, not auto-generate
        assert call_args["id"] == "my-custom-id"

    @pytest.mark.asyncio
    async def test_no_uuid_generation_for_int_pk(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[SeedFieldTemplate(field="name", template="fixed_value")],
        )
        entity = _make_entity(
            "Counter",
            [
                _make_field("id", FieldTypeKind.INT, [FieldModifier.PK]),
                _make_field("name", FieldTypeKind.STR, [FieldModifier.UNIQUE]),
            ],
            seed_template=seed_tmpl,
        )
        repo = _make_repo()
        appspec = _make_appspec([entity])

        await run_seed_templates(appspec, {"Counter": repo})

        call_args = repo.create.call_args[0][0]
        assert "id" not in call_args


# ---------------------------------------------------------------------------
# run_seed_templates — basic behavior
# ---------------------------------------------------------------------------


class TestRunSeedTemplatesBasic:
    @pytest.mark.asyncio
    async def test_skips_entity_without_seed_template(self) -> None:
        entity = _make_entity("Task", [_make_field("id", FieldTypeKind.UUID, [FieldModifier.PK])])
        repo = _make_repo()
        appspec = _make_appspec([entity])

        total = await run_seed_templates(appspec, {"Task": repo})

        assert total == 0
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_entity_without_repo(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[SeedFieldTemplate(field="name", template="fixed")],
        )
        entity = _make_entity("FiscalYear", [], seed_template=seed_tmpl)
        appspec = _make_appspec([entity])

        total = await run_seed_templates(appspec, {})
        assert total == 0

    @pytest.mark.asyncio
    async def test_skips_existing_rows(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[SeedFieldTemplate(field="name", template="fixed_value")],
        )
        entity = _make_entity(
            "FiscalYear",
            [
                _make_field("id", FieldTypeKind.UUID, [FieldModifier.PK]),
                _make_field("name", FieldTypeKind.STR, [FieldModifier.UNIQUE]),
            ],
            seed_template=seed_tmpl,
        )
        repo = _make_repo(existing_items=[{"id": "existing", "name": "fixed_value"}])
        appspec = _make_appspec([entity])

        total = await run_seed_templates(appspec, {"FiscalYear": repo})

        assert total > 0
        repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_create_failure(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            match_field="name",
            fields=[SeedFieldTemplate(field="name", template="fixed_value")],
        )
        entity = _make_entity(
            "FiscalYear",
            [
                _make_field("id", FieldTypeKind.UUID, [FieldModifier.PK]),
                _make_field("name", FieldTypeKind.STR, [FieldModifier.UNIQUE]),
            ],
            seed_template=seed_tmpl,
        )
        repo = _make_repo()
        repo.create.side_effect = RuntimeError("DB error")
        appspec = _make_appspec([entity])

        # Should not raise — errors are caught and logged
        total = await run_seed_templates(appspec, {"FiscalYear": repo})
        assert total == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_match_field(self) -> None:
        seed_tmpl = SeedTemplateSpec(
            fields=[SeedFieldTemplate(field="value", template="x")],
        )
        entity = _make_entity(
            "Thing",
            [_make_field("value", FieldTypeKind.STR)],
            seed_template=seed_tmpl,
        )
        repo = _make_repo()
        appspec = _make_appspec([entity])

        total = await run_seed_templates(appspec, {"Thing": repo})
        assert total == 0
        repo.create.assert_not_called()
