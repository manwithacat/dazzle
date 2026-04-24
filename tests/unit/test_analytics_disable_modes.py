"""Tests for dev/trial/qa analytics-disable semantics (v0.61.0 Phase 4).

When DAZZLE_ENV=dev or DAZZLE_MODE=trial, analytics must NOT emit — even
when the app declares providers. This prevents automated agents from
polluting real GA / Plausible datasets.

The escape hatch `DAZZLE_ANALYTICS_FORCE=1` re-enables emission for the
framework devs exercising the stack itself.
"""

from __future__ import annotations

import pytest

from dazzle.compliance.analytics import (
    analytics_globally_disabled,
    resolve_active_providers,
)
from dazzle.compliance.analytics.consent import build_decided_state
from dazzle.core.ir import AnalyticsProviderInstance, AnalyticsSpec


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """Every test starts with a clean environment — DAZZLE_* unset."""
    for key in ("DAZZLE_ENV", "DAZZLE_MODE", "DAZZLE_ANALYTICS_FORCE"):
        monkeypatch.delenv(key, raising=False)


def _spec_with_gtm():
    return AnalyticsSpec(providers=[AnalyticsProviderInstance(name="gtm", params={"id": "GTM-X"})])


class TestAnalyticsGloballyDisabled:
    def test_default_environment_enabled(self):
        assert analytics_globally_disabled() is False

    def test_dev_env_disables(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        assert analytics_globally_disabled() is True

    def test_development_env_disables(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "development")
        assert analytics_globally_disabled() is True

    def test_test_env_disables(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "test")
        assert analytics_globally_disabled() is True

    def test_production_env_enabled(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "production")
        assert analytics_globally_disabled() is False

    def test_trial_mode_disables(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_MODE", "trial")
        assert analytics_globally_disabled() is True

    def test_qa_mode_disables(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_MODE", "qa")
        assert analytics_globally_disabled() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "DEV")
        assert analytics_globally_disabled() is True

    def test_force_overrides_dev(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        monkeypatch.setenv("DAZZLE_ANALYTICS_FORCE", "1")
        assert analytics_globally_disabled() is False

    def test_force_overrides_trial(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_MODE", "trial")
        monkeypatch.setenv("DAZZLE_ANALYTICS_FORCE", "1")
        assert analytics_globally_disabled() is False

    def test_force_must_be_exactly_one(self, monkeypatch):
        """Only DAZZLE_ANALYTICS_FORCE=1 bypasses. Other values ignored."""
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        monkeypatch.setenv("DAZZLE_ANALYTICS_FORCE", "true")
        assert analytics_globally_disabled() is True


class TestResolveActiveProvidersIntegration:
    def _granted_state(self):
        return build_decided_state(
            analytics=True,
            advertising=True,
            personalization=True,
            functional=True,
        )

    def test_providers_return_normally_when_enabled(self):
        active = resolve_active_providers(_spec_with_gtm(), self._granted_state())
        assert len(active) == 1
        assert active[0]["name"] == "gtm"

    def test_providers_suppressed_in_dev(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        active = resolve_active_providers(_spec_with_gtm(), self._granted_state())
        assert active == []

    def test_providers_suppressed_in_trial(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_MODE", "trial")
        active = resolve_active_providers(_spec_with_gtm(), self._granted_state())
        assert active == []

    def test_providers_suppressed_in_qa(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_MODE", "qa")
        active = resolve_active_providers(_spec_with_gtm(), self._granted_state())
        assert active == []

    def test_force_reenables_in_dev(self, monkeypatch):
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        monkeypatch.setenv("DAZZLE_ANALYTICS_FORCE", "1")
        active = resolve_active_providers(_spec_with_gtm(), self._granted_state())
        assert len(active) == 1
