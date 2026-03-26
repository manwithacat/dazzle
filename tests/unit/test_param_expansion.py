"""Tests for param() reference expansion to SLA, schedule, and grant_schema constructs."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.params import ParamRef


def _parse(dsl_text: str):
    """Helper: parse DSL text and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl_text, Path("test.dsl"))
    return fragment


# ---------------------------------------------------------------------------
# SLA business_hours: schedule with param()
# ---------------------------------------------------------------------------


class TestSLABusinessHoursParam:
    def test_schedule_param(self):
        dsl = """\
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: str(50)

sla TicketResponse "Ticket Response SLA":
  entity: Ticket
  starts_when: status -> open
  tiers:
    warning: 4 hours
  business_hours:
    schedule: param("sla.schedule")
    timezone: "Europe/London"
"""
        frag = _parse(dsl)
        sla = frag.slas[0]
        assert isinstance(sla.business_hours.schedule, ParamRef)
        assert sla.business_hours.schedule.key == "sla.schedule"
        assert sla.business_hours.timezone == "Europe/London"

    def test_timezone_param(self):
        dsl = """\
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: str(50)

sla TicketResponse "Ticket Response SLA":
  entity: Ticket
  starts_when: status -> open
  tiers:
    warning: 4 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: param("sla.timezone")
"""
        frag = _parse(dsl)
        sla = frag.slas[0]
        assert sla.business_hours.schedule == "Mon-Fri 09:00-17:00"
        assert isinstance(sla.business_hours.timezone, ParamRef)
        assert sla.business_hours.timezone.key == "sla.timezone"
        assert sla.business_hours.timezone.default == "UTC"

    def test_static_business_hours_still_works(self):
        dsl = """\
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: str(50)

sla TicketResponse "Ticket Response SLA":
  entity: Ticket
  starts_when: status -> open
  tiers:
    warning: 4 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
"""
        frag = _parse(dsl)
        sla = frag.slas[0]
        assert sla.business_hours.schedule == "Mon-Fri 09:00-17:00"
        assert sla.business_hours.timezone == "Europe/London"


# ---------------------------------------------------------------------------
# SLA tier duration_value with param()
# ---------------------------------------------------------------------------


class TestSLATierParam:
    def test_tier_duration_param(self):
        dsl = """\
module test_mod

entity Ticket "Ticket":
  id: uuid pk
  status: str(50)

sla TicketResponse "Ticket Response SLA":
  entity: Ticket
  starts_when: status -> open
  tiers:
    warning: param("sla.warning_hours") hours
    breach: 8 hours
"""
        frag = _parse(dsl)
        sla = frag.slas[0]
        warning_tier = sla.tiers[0]
        assert isinstance(warning_tier.duration_value, ParamRef)
        assert warning_tier.duration_value.key == "sla.warning_hours"
        assert warning_tier.duration_value.param_type == "int"
        assert warning_tier.duration_unit == "hours"
        # Static tier still works
        breach_tier = sla.tiers[1]
        assert breach_tier.duration_value == 8
        assert breach_tier.duration_unit == "hours"


# ---------------------------------------------------------------------------
# Schedule cron and timezone with param()
# ---------------------------------------------------------------------------


class TestScheduleParam:
    def test_cron_param(self):
        dsl = """\
module test_mod

schedule daily_report "Daily Report":
  cron: param("schedule.cron")
  timezone: "Europe/London"

  steps:
    - step generate:
        service: generate_report
        timeout: 5m
"""
        frag = _parse(dsl)
        sched = frag.schedules[0]
        assert isinstance(sched.cron, ParamRef)
        assert sched.cron.key == "schedule.cron"
        assert sched.timezone == "Europe/London"

    def test_timezone_param(self):
        dsl = """\
module test_mod

schedule daily_report "Daily Report":
  cron: "0 8 * * *"
  timezone: param("schedule.tz")

  steps:
    - step generate:
        service: generate_report
        timeout: 5m
"""
        frag = _parse(dsl)
        sched = frag.schedules[0]
        assert sched.cron == "0 8 * * *"
        assert isinstance(sched.timezone, ParamRef)
        assert sched.timezone.key == "schedule.tz"

    def test_timeout_param(self):
        dsl = """\
module test_mod

schedule daily_report "Daily Report":
  cron: "0 8 * * *"
  timeout: param("schedule.timeout")

  steps:
    - step generate:
        service: generate_report
        timeout: 5m
"""
        frag = _parse(dsl)
        sched = frag.schedules[0]
        assert isinstance(sched.timeout_seconds, ParamRef)
        assert sched.timeout_seconds.key == "schedule.timeout"
        assert sched.timeout_seconds.param_type == "int"

    def test_static_schedule_still_works(self):
        dsl = """\
module test_mod

schedule daily_report "Daily Report":
  cron: "0 8 * * *"
  timezone: "Europe/London"
  timeout: 1h

  steps:
    - step generate:
        service: generate_report
        timeout: 5m
"""
        frag = _parse(dsl)
        sched = frag.schedules[0]
        assert sched.cron == "0 8 * * *"
        assert sched.timezone == "Europe/London"
        assert sched.timeout_seconds == 3600


# ---------------------------------------------------------------------------
# Grant schema max_duration with param()
# ---------------------------------------------------------------------------


class TestGrantSchemaParam:
    def test_max_duration_param(self):
        dsl = """\
module test_mod

entity Department "Department":
  id: uuid pk
  name: str(100)

grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(admin)
    approval: required
    expiry: required
    max_duration: param("grant.max_duration")
"""
        frag = _parse(dsl)
        gs = frag.grant_schemas[0]
        rel = gs.relations[0]
        assert isinstance(rel.max_duration, ParamRef)
        assert rel.max_duration.key == "grant.max_duration"
        assert rel.max_duration.param_type == "str"

    def test_static_max_duration_still_works(self):
        dsl = """\
module test_mod

entity Department "Department":
  id: uuid pk
  name: str(100)

grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(admin)
    approval: required
    expiry: required
    max_duration: 90d
"""
        frag = _parse(dsl)
        gs = frag.grant_schemas[0]
        rel = gs.relations[0]
        assert rel.max_duration == "90d"


# ---------------------------------------------------------------------------
# Helper method unit tests
# ---------------------------------------------------------------------------


class TestParseHelpers:
    """Test _parse_string_or_param and _parse_int_or_param helpers directly via DSL parsing."""

    def test_string_or_param_returns_string(self):
        """SLA schedule with a literal string exercises _parse_string_or_param."""
        dsl = """\
module test_mod

entity T "T":
  id: uuid pk
  status: str(50)

sla S "S":
  entity: T
  starts_when: status -> open
  tiers:
    warning: 1 hours
  business_hours:
    schedule: "weekdays"
"""
        frag = _parse(dsl)
        assert frag.slas[0].business_hours.schedule == "weekdays"
        assert isinstance(frag.slas[0].business_hours.schedule, str)

    def test_string_or_param_returns_param_ref(self):
        """SLA schedule with param() exercises _parse_string_or_param returning ParamRef."""
        dsl = """\
module test_mod

entity T "T":
  id: uuid pk
  status: str(50)

sla S "S":
  entity: T
  starts_when: status -> open
  tiers:
    warning: 1 hours
  business_hours:
    schedule: param("bh.schedule")
"""
        frag = _parse(dsl)
        assert isinstance(frag.slas[0].business_hours.schedule, ParamRef)

    def test_int_or_param_returns_int(self):
        """SLA tier with literal int exercises _parse_int_or_param."""
        dsl = """\
module test_mod

entity T "T":
  id: uuid pk
  status: str(50)

sla S "S":
  entity: T
  starts_when: status -> open
  tiers:
    warning: 42 hours
"""
        frag = _parse(dsl)
        assert frag.slas[0].tiers[0].duration_value == 42
        assert isinstance(frag.slas[0].tiers[0].duration_value, int)

    def test_int_or_param_returns_param_ref(self):
        """SLA tier with param() exercises _parse_int_or_param returning ParamRef."""
        dsl = """\
module test_mod

entity T "T":
  id: uuid pk
  status: str(50)

sla S "S":
  entity: T
  starts_when: status -> open
  tiers:
    warning: param("tier.val") hours
"""
        frag = _parse(dsl)
        assert isinstance(frag.slas[0].tiers[0].duration_value, ParamRef)
        assert frag.slas[0].tiers[0].duration_value.param_type == "int"
