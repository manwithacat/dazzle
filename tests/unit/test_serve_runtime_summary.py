"""Tests for #989 fix — serve banner shows audit/jobs/tenancy counts.

Pre-fix, `dazzle serve` printed entity / surface / workspace
counts but not the new runtime primitives. A misconfigured
`audit on UnknownEntity:` registered nothing silently — operator
only found out when no audit rows showed up.

Now `_echo_runtime_summary` adds one banner line per primitive
the AppSpec actually declares (no extra lines for primitives the
user doesn't use).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from typing import Any
from unittest.mock import patch

from dazzle.cli.runtime_impl.serve import _echo_runtime_summary


@dataclass
class _Iso:
    mode: str = "shared_schema"


@dataclass
class _Tenancy:
    isolation: _Iso = field(default_factory=_Iso)
    admin_personas: list[str] = field(default_factory=list)
    per_tenant_config: dict[str, str] = field(default_factory=dict)


@dataclass
class _Audit:
    entity: str


@dataclass
class _Job:
    name: str
    triggers: list[Any] = field(default_factory=list)
    schedule: Any = None


@dataclass
class _AppSpec:
    audits: list[_Audit] = field(default_factory=list)
    jobs: list[_Job] = field(default_factory=list)
    tenancy: _Tenancy | None = None


def _capture(spec: _AppSpec) -> str:
    """Run `_echo_runtime_summary` and return what it printed."""
    buf = StringIO()
    with patch("typer.echo", lambda msg="": buf.write(str(msg) + "\n")):
        _echo_runtime_summary(spec)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Empty AppSpec — nothing printed
# ---------------------------------------------------------------------------


class TestEmpty:
    def test_no_primitives_no_output(self):
        spec = _AppSpec()
        assert _capture(spec) == ""

    def test_empty_audits_no_audit_line(self):
        spec = _AppSpec(audits=[], jobs=[_Job(name="x")], tenancy=None)
        out = _capture(spec)
        assert "audit" not in out.lower()


# ---------------------------------------------------------------------------
# Audit summary
# ---------------------------------------------------------------------------


class TestAuditSummary:
    def test_one_audit_block_singular(self):
        spec = _AppSpec(audits=[_Audit(entity="Ticket")])
        out = _capture(spec)
        assert "1 audit block (1 entity tracked)" in out

    def test_multi_audit_blocks_plural(self):
        spec = _AppSpec(audits=[_Audit(entity="Ticket"), _Audit(entity="Comment")])
        out = _capture(spec)
        assert "2 audit blocks (2 entities tracked)" in out


# ---------------------------------------------------------------------------
# Jobs summary
# ---------------------------------------------------------------------------


class TestJobsSummary:
    def test_only_triggered(self):
        spec = _AppSpec(jobs=[_Job(name="x", triggers=[object()])])
        out = _capture(spec)
        assert "1 background job (1 triggered)" in out

    def test_only_scheduled(self):
        spec = _AppSpec(jobs=[_Job(name="x", schedule=object())])
        out = _capture(spec)
        assert "1 background job (1 scheduled)" in out

    def test_mixed(self):
        spec = _AppSpec(
            jobs=[
                _Job(name="a", triggers=[object()]),
                _Job(name="b", triggers=[object()]),
                _Job(name="c", schedule=object()),
                _Job(name="d", schedule=object()),
            ]
        )
        out = _capture(spec)
        assert "4 background jobs (2 triggered, 2 scheduled)" in out

    def test_neither(self):
        # Job with neither triggers nor schedule (malformed but
        # defensive) — banner just shows the count.
        spec = _AppSpec(jobs=[_Job(name="x")])
        out = _capture(spec)
        assert "1 background job" in out


# ---------------------------------------------------------------------------
# Tenancy summary
# ---------------------------------------------------------------------------


class TestTenancySummary:
    def test_just_mode(self):
        spec = _AppSpec(tenancy=_Tenancy())
        out = _capture(spec)
        assert "Tenancy: shared_schema" in out

    def test_with_admin_personas(self):
        spec = _AppSpec(tenancy=_Tenancy(admin_personas=["super_admin", "support"]))
        out = _capture(spec)
        assert "2 admin personas" in out

    def test_with_per_tenant_config(self):
        spec = _AppSpec(
            tenancy=_Tenancy(per_tenant_config={"locale": "str", "feature_billing": "bool"})
        )
        out = _capture(spec)
        assert "2 per-tenant config keys" in out

    def test_singular_admin_persona(self):
        spec = _AppSpec(tenancy=_Tenancy(admin_personas=["support"]))
        out = _capture(spec)
        assert "1 admin persona" in out
        assert "personas" not in out  # singular form


# ---------------------------------------------------------------------------
# All three together — the dogfood case
# ---------------------------------------------------------------------------


class TestAllThree:
    def test_full_summary_emits_three_lines(self):
        spec = _AppSpec(
            audits=[_Audit(entity="Ticket"), _Audit(entity="Comment")],
            jobs=[
                _Job(name="a", triggers=[object()]),
                _Job(name="b", triggers=[object()]),
                _Job(name="c", schedule=object()),
                _Job(name="d", schedule=object()),
            ],
            tenancy=_Tenancy(
                admin_personas=["manager"],
                per_tenant_config={
                    "sla_response_minutes": "int",
                    "default_ticket_priority": "str",
                    "feature_internal_notes": "bool",
                },
            ),
        )
        out = _capture(spec)
        # Each primitive has exactly one summary line.
        assert "audit blocks" in out
        assert "background jobs" in out
        assert "Tenancy:" in out
        # Three new banner lines total.
        assert out.count("\n") == 3
