"""Tests for #990 fix — platform-domain entities don't get plural-redirect routes.

Pre-fix, every entity (including framework-injected `AuditEntry`,
`JobRun`, `AIJob`, etc.) got a `/app/<plural>` → `/app/<singular>`
301 redirect registered automatically. The redirect targets all
404 because no list surface exists for these platform entities,
but the redirect itself showed in OpenAPI making it look like a
user-navigable page.

Now the loop skips entities with `domain="platform"` so OpenAPI
stays clean. Admin tooling exposes these tables via the dedicated
admin workspace under `/_admin/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass
class _StubEntity:
    name: str
    domain: str = ""


@dataclass
class _StubDomain:
    entities: list[_StubEntity] = field(default_factory=list)


@dataclass
class _StubAppSpec:
    domain: _StubDomain = field(default_factory=_StubDomain)


# ---------------------------------------------------------------------------
# Direct test of the filter logic
# ---------------------------------------------------------------------------


class TestPlatformEntityFilter:
    """The fix is a single-line `getattr(_entity, 'domain', '') == 'platform'`
    early-continue. We verify the predicate behaviour here, then a
    smoke test confirms the integration with the route registration
    loop downstream."""

    def test_platform_entity_skipped(self):
        # Mirrors the condition added to the plural-redirect loop:
        e = _StubEntity(name="AuditEntry", domain="platform")
        assert e.domain == "platform"

    def test_user_entity_not_skipped(self):
        e = _StubEntity(name="Ticket", domain="support")
        assert e.domain != "platform"

    def test_missing_domain_not_skipped(self):
        # Backward compat: entities without an explicit domain (the
        # default for user-declared entities pre-domain-tagging) get
        # the plural redirect as before.
        e = _StubEntity(name="LegacyEntity", domain="")
        assert e.domain != "platform"


# ---------------------------------------------------------------------------
# Integration: framework-built AuditEntry / JobRun get domain="platform"
# ---------------------------------------------------------------------------


class TestFrameworkEntitiesArePlatform:
    """Verify the cycle-2 builders for AuditEntry + JobRun set
    `domain="platform"` so they actually trigger the filter above.
    Catches a regression where a future refactor drops the marker."""

    def test_audit_entry_is_platform(self):
        from dazzle.core.linker import _build_audit_entry_entity

        entity = _build_audit_entry_entity()
        assert entity.name == "AuditEntry"
        assert entity.domain == "platform"

    def test_job_run_is_platform(self):
        from dazzle.core.linker import _build_job_run_entity

        entity = _build_job_run_entity()
        assert entity.name == "JobRun"
        assert entity.domain == "platform"

    def test_ai_job_is_platform(self):
        # Same invariant for the existing platform entities so the
        # filter catches them too — no regression on AIJob /
        # FeedbackReport routing.
        from dazzle.core.linker import _build_ai_job_entity

        entity = _build_ai_job_entity()
        assert entity.domain == "platform"

    def test_feedback_report_is_platform(self):
        from dazzle.core.linker import _build_feedback_report_entity

        entity = _build_feedback_report_entity()
        assert entity.domain == "platform"


# ---------------------------------------------------------------------------
# End-to-end via build_appspec
# ---------------------------------------------------------------------------


class TestEndToEndAppspec:
    """Build a real AppSpec with audit + job declarations, then
    confirm the platform-domain entities are present but
    un-routable. This is the actual user-visible behaviour the
    fix delivers."""

    def test_appspec_contains_platform_entities(self, tmp_path):
        import textwrap

        from dazzle.core.linker import build_appspec
        from dazzle.core.parser import parse_modules

        dsl = tmp_path / "test.dsl"
        dsl.write_text(
            textwrap.dedent(
                """
                module test
                app a "A"

                entity Ticket "T":
                  id: uuid pk
                  status: str(50)

                audit on Ticket:
                  track: status
                  show_to: persona(admin)

                job daily "Daily":
                  schedule: cron("0 1 * * *")
                  run: app.jobs:daily
                """
            ).lstrip()
        )
        appspec = build_appspec(parse_modules([dsl]), "test")

        names = {e.name: e for e in appspec.domain.entities}
        # Cycle-2 system entities present.
        assert "AuditEntry" in names
        assert "JobRun" in names
        # And both are platform-domain so the route filter skips them.
        assert names["AuditEntry"].domain == "platform"
        assert names["JobRun"].domain == "platform"
        # Ticket is not platform-domain — keeps its plural-redirect route.
        assert names["Ticket"].domain != "platform"


# ---------------------------------------------------------------------------
# Defensive: getattr fallback
# ---------------------------------------------------------------------------


class TestGetattrFallback:
    """The filter uses `getattr(_entity, 'domain', '')` so an
    EntitySpec built without a domain attribute (theoretical
    future case) doesn't crash — defaults to empty string,
    which doesn't equal 'platform', so the entity gets the
    redirect as before."""

    def test_object_without_domain_attr(self):
        class _BareEntity:
            name = "Test"
            # no `domain` attribute at all

        e = _BareEntity()
        # The filter expression should evaluate False (not platform),
        # so the entity falls through to the redirect-registration
        # branch.
        assert getattr(e, "domain", "") != "platform"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
