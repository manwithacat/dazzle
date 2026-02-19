"""Tests for v0.34.0 platform capability features.

Covers: soft delete, searchable fields, bulk import/export,
notifications, search on surfaces, and date-range reporting.
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    BulkConfig,
    BulkFormat,
    NotificationChannel,
    NotificationPreference,
    TimeBucket,
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
# Bulk import/export
# =============================================================================


class TestBulkConfig:
    def test_bulk_all(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk: all
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is True
        assert entity.bulk.export_enabled is True

    def test_bulk_import_only(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk: import
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is True
        assert entity.bulk.export_enabled is False

    def test_bulk_export_only(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk: export
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is False
        assert entity.bulk.export_enabled is True

    def test_bulk_true(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk: true
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is True
        assert entity.bulk.export_enabled is True

    def test_bulk_block_with_formats(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk:
    import: true
    export: true
    formats: [csv, json, xlsx]
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is True
        assert entity.bulk.export_enabled is True
        assert BulkFormat.CSV in entity.bulk.formats
        assert BulkFormat.JSON in entity.bulk.formats
        assert BulkFormat.XLSX in entity.bulk.formats

    def test_bulk_block_import_disabled(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
  bulk:
    import: false
    export: true
"""
        )
        entity = frag.entities[0]
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is False
        assert entity.bulk.export_enabled is True

    def test_no_bulk_default(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  title: str(200)
"""
        )
        assert frag.entities[0].bulk is None


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

    def test_audit_config_model(self):
        config = BulkConfig()
        assert config.import_enabled is True
        assert config.export_enabled is True
        assert config.formats == [BulkFormat.CSV]


# =============================================================================
# Notifications
# =============================================================================


class TestNotifications:
    def test_basic_notification(self):
        frag = _parse(
            """\
module test
entity Invoice "Invoice":
  id: uuid pk
  title: str(200)
  status: enum[draft, sent, overdue, paid]

notification invoice_overdue "Invoice Overdue":
  on: Invoice.status -> overdue
  channels: [in_app, email]
  message: "Invoice {{title}} is overdue"
  recipients: role(accountant)
  preferences: opt_out
"""
        )
        assert len(frag.notifications) == 1
        n = frag.notifications[0]
        assert n.name == "invoice_overdue"
        assert n.title == "Invoice Overdue"
        assert n.trigger.entity == "Invoice"
        assert n.trigger.field == "status"
        assert n.trigger.to_value == "overdue"
        assert n.trigger.event == "status_changed"
        assert NotificationChannel.IN_APP in n.channels
        assert NotificationChannel.EMAIL in n.channels
        assert "overdue" in n.message
        assert n.recipients.kind == "role"
        assert n.recipients.value == "accountant"
        assert n.preference == NotificationPreference.OPT_OUT

    def test_field_changed_notification(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk
  assigned_to: str(200)

notification task_assigned "Task Assigned":
  on: Task.assigned_to changed
  channels: [in_app, slack]
  message: "You have been assigned a task"
  recipients: field(assigned_to)
"""
        )
        n = frag.notifications[0]
        assert n.trigger.event == "field_changed"
        assert n.trigger.field == "assigned_to"
        assert n.trigger.to_value is None
        assert NotificationChannel.SLACK in n.channels
        assert n.recipients.kind == "field"
        assert n.recipients.value == "assigned_to"

    def test_entity_created_notification(self):
        frag = _parse(
            """\
module test
entity Order "Order":
  id: uuid pk
  total: int

notification new_order "New Order":
  on: Order created
  channels: [in_app]
  message: "New order received"
  recipients: role(admin)
"""
        )
        n = frag.notifications[0]
        assert n.trigger.event == "created"
        assert n.trigger.entity == "Order"
        assert n.trigger.field is None

    def test_notification_creator_recipient(self):
        frag = _parse(
            """\
module test
entity Ticket "Ticket":
  id: uuid pk
  title: str(200)

notification ticket_resolved "Ticket Resolved":
  on: Ticket.status -> resolved
  channels: [in_app, email]
  message: "Your ticket has been resolved"
  recipients: creator
"""
        )
        n = frag.notifications[0]
        assert n.recipients.kind == "creator"

    def test_notification_mandatory_preference(self):
        frag = _parse(
            """\
module test
entity Payment "Payment":
  id: uuid pk
  amount: int

notification payment_failed "Payment Failed":
  on: Payment.status -> failed
  channels: [in_app, email, sms]
  message: "Payment failed"
  recipients: field(customer)
  preferences: mandatory
"""
        )
        n = frag.notifications[0]
        assert n.preference == NotificationPreference.MANDATORY
        assert NotificationChannel.SMS in n.channels

    def test_notification_defaults(self):
        frag = _parse(
            """\
module test
entity Task "Task":
  id: uuid pk

notification task_created "Task Created":
  on: Task created
"""
        )
        n = frag.notifications[0]
        assert n.channels == [NotificationChannel.IN_APP]
        assert n.preference == NotificationPreference.OPT_OUT
        assert n.message == ""


# =============================================================================
# Date-range reporting on views
# =============================================================================


class TestDateRangeViews:
    def test_view_date_field_and_time_bucket(self):
        frag = _parse(
            """\
module test
view MonthlySales "Monthly Sales":
  source: Order
  date_field: created_at
  time_bucket: month
  fields:
    total: sum(amount)
"""
        )
        view = frag.views[0]
        assert view.date_field == "created_at"
        assert view.time_bucket == TimeBucket.MONTH

    def test_view_quarterly_bucket(self):
        frag = _parse(
            """\
module test
view QuarterlyRevenue "Quarterly Revenue":
  source: Invoice
  date_field: issued_at
  time_bucket: quarter
"""
        )
        view = frag.views[0]
        assert view.date_field == "issued_at"
        assert view.time_bucket == TimeBucket.QUARTER

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
        assert view.time_bucket is None


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
        """Entity using soft_delete, searchable, bulk, and audit together."""
        frag = _parse(
            """\
module test
entity Contact "Contact":
  soft_delete
  bulk: all
  audit: all
  id: uuid pk
  name: str(200) required searchable
  email: str(200) searchable
  phone: str(50)
"""
        )
        entity = frag.entities[0]
        assert entity.soft_delete is True
        assert entity.bulk is not None
        assert entity.bulk.import_enabled is True
        assert entity.audit is not None
        assert entity.audit.enabled is True
        assert entity.audit.include_field_changes is True
        assert len(entity.searchable_fields) == 2
