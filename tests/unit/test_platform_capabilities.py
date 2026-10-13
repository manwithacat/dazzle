"""Tests for v0.34.0 platform capability features.

Covers: soft delete, searchable fields,
search on surfaces, and date-range reporting.
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import (
    ManagedBy,
)


def _parse(dsl: str):
    """Parse DSL text and return the module fragment."""
    _, _, _, _, _, frag = parse_dsl(dsl, Path("test.dz"))
    return frag


# =============================================================================
# Soft delete
# =============================================================================


class TestSoftDelete:
    def test_soft_delete_flag(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  soft_delete
  id: uuid pk
  title: str(200)
"""
        )
        assert frag.entities[0].soft_delete is True

    def test_no_soft_delete_default(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
"""
        )
        assert frag.entities[0].soft_delete is False


# =============================================================================
# managed_by lifecycle-ownership marker (#1333)
# =============================================================================


class TestManagedBy:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("route", ManagedBy.ROUTE),
            ("pipeline", ManagedBy.PIPELINE),
            ("wizard", ManagedBy.WIZARD),
            ("external", ManagedBy.EXTERNAL),
        ],
    )
    def test_managed_by_values(self, value, expected):
        frag = _parse(
            f"""\
module test
entity OnboardingProgress "Onboarding Progress":
  managed_by: {value}
  id: uuid pk
  title: str(200)
"""
        )
        assert frag.entities[0].managed_by is expected

    def test_managed_by_default_none(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
"""
        )
        assert frag.entities[0].managed_by is None

    def test_managed_by_rejects_unknown_value(self):
        with pytest.raises(ParseError, match="managed_by"):
            _parse(
                """\
module test
entity Task "Task":
  managed_by: bogus
  id: uuid pk
"""
            )

    def test_managed_by_does_not_touch_domain(self):
        """The marker is orthogonal to `domain` — it must NOT reclassify the
        business domain (the whole point vs. `domain: platform`)."""
        frag = _parse(
            """\
module test
entity Invoice "Invoice":
  managed_by: pipeline
  domain: billing
  id: uuid pk
"""
        )
        entity = frag.entities[0]
        assert entity.managed_by is ManagedBy.PIPELINE
        assert entity.domain == "billing"

    def test_managed_by_usable_as_identifier_in_patterns(self):
        """`managed_by` is in KEYWORD_AS_IDENTIFIER_TYPES (like soft_delete),
        so it stays legal as an identifier in value positions — e.g. a
        patterns tag — even though it dispatches as a keyword at entity-body
        statement position (the same as every other entity keyword)."""
        frag = _parse(
            """\
module test
entity Thing "Thing":
  patterns: managed_by, audited
  id: uuid pk
"""
        )
        assert "managed_by" in frag.entities[0].patterns


# =============================================================================
# Searchable fields
# =============================================================================


class TestSearchableFields:
    def test_searchable_modifier(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200) searchable
  description: text searchable
  status: str(50)
"""
        )
        entity = frag.entities[0]
        searchable = entity.searchable_fields
        assert len(searchable) == 2
        assert searchable[0].name == "title"
        assert searchable[1].name == "description"

    def test_searchable_with_other_modifiers(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200) required searchable
"""
        )
        entity = frag.entities[0]
        assert entity.fields[1].is_searchable is True
        assert entity.fields[1].is_required is True


# =============================================================================
# Search on surfaces
# =============================================================================


class TestSurfaceSearch:
    def test_search_field_list(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  search: [title, description]
"""
        )
        surface = frag.surfaces[0]
        assert surface.search_fields == ["title", "description"]

    def test_search_single_field(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  search: title
"""
        )
        surface = frag.surfaces[0]
        assert surface.search_fields == ["title"]

    def test_no_search_default(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
"""
        )
        surface = frag.surfaces[0]
        assert surface.search_fields == []


# =============================================================================
# Audit trail enhancement
# =============================================================================


class TestAuditEnhancement:
    def test_audit_includes_field_changes_by_default(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  audit: all
"""
        )
        entity = frag.entities[0]
        assert entity.audit is not None
        assert entity.audit.enabled is True
        assert entity.audit.include_field_changes is True


# =============================================================================
# Date-range reporting on views
# =============================================================================


class TestDateRangeViews:
    def test_view_date_field(self):
        frag = _parse(
            """\
module test
view MonthlySales "Monthly Sales":
  source: Order
  date_field: created_at
  fields:
    total: sum(amount)
"""
        )
        view = frag.views[0]
        assert view.date_field == "created_at"

    def test_view_no_date_range_default(self):
        frag = _parse(
            """\
module test
view SimpleView "Simple":
  source: Task
"""
        )
        view = frag.views[0]
        assert view.date_field is None


# =============================================================================
# Date-range on workspace regions
# =============================================================================


class TestDateRangeWorkspaceRegions:
    def test_workspace_region_date_range(self):
        frag = _parse(
            """\
module test
entity Invoice "Invoice":
  id: uuid pk
  issued_at: date

workspace billing "Billing":
  recent_invoices:
    source: Invoice
    date_field: issued_at
    date_range
    sort: issued_at desc
"""
        )
        ws = frag.workspaces[0]
        region = ws.regions[0]
        assert region.date_field == "issued_at"
        assert region.date_range is True

    def test_workspace_region_no_date_range_default(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)

workspace dashboard "Dashboard":
  tasks:
    source: Task
"""
        )
        ws = frag.workspaces[0]
        region = ws.regions[0]
        assert region.date_field is None
        assert region.date_range is False


# =============================================================================
# Combined features round-trip
# =============================================================================


class TestCombinedFeatures:
    def test_entity_with_all_new_features(self):
        """Entity using soft_delete, searchable, and audit together."""
        frag = _parse(
            """\
module test
entity Contact "Contact":
  soft_delete
  audit: all
  id: uuid pk
  name: str(200) required searchable
  email: str(200) searchable
  phone: str(50)
"""
        )
        entity = frag.entities[0]
        assert entity.soft_delete is True
        assert entity.audit is not None
        assert entity.audit.enabled is True
        assert entity.audit.include_field_changes is True
        assert len(entity.searchable_fields) == 2
