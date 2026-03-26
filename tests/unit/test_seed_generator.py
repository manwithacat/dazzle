"""Tests for DSL-driven reference data seeding (#428).

Covers:
- SeedTemplateSpec IR type
- Seed row generation (rolling_window)
- Template variable rendering
- Match field resolution
- Parser integration (seed: block)
"""

import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# IR: SeedTemplateSpec
# ---------------------------------------------------------------------------


class TestSeedTemplateSpec:
    def test_defaults(self) -> None:
        from dazzle.core.ir.seed import SeedStrategy, SeedTemplateSpec

        spec = SeedTemplateSpec()
        assert spec.strategy == SeedStrategy.ROLLING_WINDOW
        assert spec.window_start == -1
        assert spec.window_end == 3
        assert spec.month_anchor == 1
        assert spec.match_field is None
        assert spec.fields == []

    def test_custom_values(self) -> None:
        from dazzle.core.ir.seed import SeedFieldTemplate, SeedTemplateSpec

        spec = SeedTemplateSpec(
            window_start=-2,
            window_end=5,
            month_anchor=9,
            match_field="name",
            fields=[
                SeedFieldTemplate(field="name", template="{y}/{y1_short}"),
                SeedFieldTemplate(field="start_date", template="{y}-09-01"),
            ],
        )
        assert spec.window_start == -2
        assert spec.window_end == 5
        assert spec.month_anchor == 9
        assert spec.match_field == "name"
        assert len(spec.fields) == 2

    def test_entity_spec_has_seed_template(self) -> None:
        from dazzle.core.ir.domain import EntitySpec
        from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
        from dazzle.core.ir.seed import SeedTemplateSpec

        entity = EntitySpec(
            name="AcademicYear",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=50),
                    modifiers=[FieldModifier.UNIQUE],
                ),
            ],
            seed_template=SeedTemplateSpec(
                window_start=-1,
                window_end=3,
                match_field="name",
            ),
        )
        assert entity.seed_template is not None
        assert entity.seed_template.window_start == -1


# ---------------------------------------------------------------------------
# Generator: generate_seed_rows
# ---------------------------------------------------------------------------


class TestGenerateSeedRows:
    def _make_template(self, **kwargs: Any) -> Any:
        from dazzle.core.ir.seed import SeedFieldTemplate, SeedTemplateSpec

        fields = kwargs.pop(
            "fields",
            [
                SeedFieldTemplate(field="name", template="{y}/{y1_short}"),
                SeedFieldTemplate(field="start_date", template="{y}-09-01"),
                SeedFieldTemplate(field="end_date", template="{y1}-08-31"),
                SeedFieldTemplate(field="is_current", template="y == current_year"),
            ],
        )
        return SeedTemplateSpec(fields=fields, **kwargs)

    def test_generates_correct_number_of_rows(self) -> None:
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=-1, window_end=3)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 6, 15))
        # -1, 0, 1, 2, 3 = 5 rows
        assert len(rows) == 5

    def test_academic_year_names(self) -> None:
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=-1, window_end=2)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 6, 15))
        names = [r["name"] for r in rows]
        assert names == ["2024/25", "2025/26", "2026/27", "2027/28"]

    def test_start_and_end_dates(self) -> None:
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=0, window_end=0)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 1, 1))
        assert rows[0]["start_date"] == "2025-09-01"
        assert rows[0]["end_date"] == "2026-08-31"

    def test_is_current_flag(self) -> None:
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=-1, window_end=1)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 6, 15))
        is_current = {r["name"]: r["is_current"] for r in rows}
        assert is_current["2024/25"] == "false"
        assert is_current["2025/26"] == "true"
        assert is_current["2026/27"] == "false"

    def test_financial_year_format(self) -> None:
        from dazzle.core.ir.seed import SeedFieldTemplate
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(
            window_start=0,
            window_end=0,
            fields=[
                SeedFieldTemplate(field="name", template="FY{y}/{y1_short}"),
                SeedFieldTemplate(field="start", template="{y}-04-01"),
                SeedFieldTemplate(field="end", template="{y1}-03-31"),
            ],
        )
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 6, 15))
        assert rows[0]["name"] == "FY2025/26"
        assert rows[0]["start"] == "2025-04-01"
        assert rows[0]["end"] == "2026-03-31"

    def test_empty_window_returns_single_row(self) -> None:
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=0, window_end=0)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 1, 1))
        assert len(rows) == 1

    def test_y_short_format(self) -> None:
        from dazzle.core.ir.seed import SeedFieldTemplate
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(
            window_start=0,
            window_end=0,
            fields=[SeedFieldTemplate(field="label", template="{y_short}/{y1_short}")],
        )
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2025, 1, 1))
        assert rows[0]["label"] == "25/26"

    def test_century_boundary(self) -> None:
        """Ensure year 2099/2100 works correctly."""
        from dazzle.seed.generator import generate_seed_rows

        tmpl = self._make_template(window_start=0, window_end=0)
        rows = generate_seed_rows(tmpl, reference_date=datetime.date(2099, 1, 1))
        assert rows[0]["name"] == "2099/00"


# ---------------------------------------------------------------------------
# Match field resolution
# ---------------------------------------------------------------------------


class TestResolveMatchField:
    def test_explicit_match_field(self) -> None:
        from dazzle.seed.generator import resolve_match_field

        tmpl = MagicMock()
        tmpl.match_field = "name"
        assert resolve_match_field(tmpl, None) == "name"

    def test_falls_back_to_unique_field(self) -> None:
        from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
        from dazzle.seed.generator import resolve_match_field

        tmpl = MagicMock()
        tmpl.match_field = None
        entity = MagicMock()
        entity.fields = [
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="code",
                type=FieldType(kind=FieldTypeKind.STR),
                modifiers=[FieldModifier.UNIQUE],
            ),
        ]
        assert resolve_match_field(tmpl, entity) == "code"

    def test_no_match_field_returns_none(self) -> None:
        from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
        from dazzle.seed.generator import resolve_match_field

        tmpl = MagicMock()
        tmpl.match_field = None
        entity = MagicMock()
        entity.fields = [
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[],
            ),
        ]
        assert resolve_match_field(tmpl, entity) is None


# ---------------------------------------------------------------------------
# Seed runner
# ---------------------------------------------------------------------------


class TestSeedRunner:
    @pytest.mark.asyncio
    async def test_creates_missing_rows(self) -> None:
        from unittest.mock import AsyncMock

        from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
        from dazzle.core.ir.seed import SeedFieldTemplate, SeedTemplateSpec
        from dazzle_back.runtime.seed_runner import run_seed_templates

        entity = MagicMock()
        entity.name = "AcademicYear"
        entity.fields = [
            FieldSpec(
                name="name",
                type=FieldType(kind=FieldTypeKind.STR),
                modifiers=[FieldModifier.UNIQUE],
            ),
        ]
        entity.seed_template = SeedTemplateSpec(
            window_start=0,
            window_end=0,
            fields=[SeedFieldTemplate(field="name", template="{y}/{y1_short}")],
        )

        appspec = MagicMock()
        appspec.domain.entities = [entity]

        repo = AsyncMock()
        repo.list.return_value = {"items": [], "total": 0}
        repo.create.return_value = {"id": "new-1", "name": "2026/27"}

        count = await run_seed_templates(appspec, {"AcademicYear": repo})
        assert count == 1
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_existing_rows(self) -> None:
        from unittest.mock import AsyncMock

        from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
        from dazzle.core.ir.seed import SeedFieldTemplate, SeedTemplateSpec
        from dazzle_back.runtime.seed_runner import run_seed_templates

        entity = MagicMock()
        entity.name = "AcademicYear"
        entity.fields = [
            FieldSpec(
                name="name",
                type=FieldType(kind=FieldTypeKind.STR),
                modifiers=[FieldModifier.UNIQUE],
            ),
        ]
        entity.seed_template = SeedTemplateSpec(
            window_start=0,
            window_end=0,
            fields=[SeedFieldTemplate(field="name", template="{y}/{y1_short}")],
        )

        appspec = MagicMock()
        appspec.domain.entities = [entity]

        repo = AsyncMock()
        repo.list.return_value = {"items": [{"id": "existing", "name": "2026/27"}], "total": 1}

        count = await run_seed_templates(appspec, {"AcademicYear": repo})
        assert count == 1
        repo.create.assert_not_called()


# ---------------------------------------------------------------------------
# Parser: seed block
# ---------------------------------------------------------------------------


class TestSeedParser:
    def _parse(self, dsl: str) -> Any:
        """Parse DSL and return the fragment."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        return fragment

    def _get_entity(self, dsl: str, name: str) -> Any:
        fragment = self._parse(dsl)
        for e in fragment.entities:
            if e.name == name:
                return e
        return None

    def test_parse_entity_with_seed(self) -> None:
        dsl = """
module test_app
app test "Test"

entity AcademicYear "Academic Year":
  id: uuid pk
  name: str(50) unique
  start_date: date
  end_date: date
  is_current: bool

  seed:
    strategy: rolling_window
    window_start: -1
    window_end: 3
    month_anchor: 9
    match_field: name
    fields:
      name: "{y}/{y1_short}"
      start_date: "{y}-09-01"
      end_date: "{y1}-08-31"
      is_current: "y == current_year"
"""
        entity = self._get_entity(dsl, "AcademicYear")
        assert entity is not None
        assert entity.seed_template is not None
        assert entity.seed_template.window_start == -1
        assert entity.seed_template.window_end == 3
        assert entity.seed_template.month_anchor == 9
        assert entity.seed_template.match_field == "name"
        assert len(entity.seed_template.fields) == 4
        assert entity.seed_template.fields[0].field == "name"
        assert entity.seed_template.fields[0].template == "{y}/{y1_short}"

    def test_parse_entity_without_seed(self) -> None:
        dsl = """
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""
        entity = self._get_entity(dsl, "Task")
        assert entity is not None
        assert entity.seed_template is None

    def test_parse_seed_minimal(self) -> None:
        """Seed block with just fields (defaults for everything else)."""
        dsl = """
module test_app
app test "Test"

entity FiscalYear "Fiscal Year":
  id: uuid pk
  code: str(20) unique

  seed:
    fields:
      code: "FY{y}/{y1_short}"
"""
        entity = self._get_entity(dsl, "FiscalYear")
        assert entity is not None
        assert entity.seed_template is not None
        assert entity.seed_template.strategy.value == "rolling_window"
        assert entity.seed_template.window_start == -1
        assert entity.seed_template.window_end == 3
        assert len(entity.seed_template.fields) == 1
