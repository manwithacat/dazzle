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
    @pytest.mark.parametrize(
        ("env_vars", "expected"),
        [
            ({}, False),  # default — analytics enabled
            ({"DAZZLE_ENV": "dev"}, True),
            ({"DAZZLE_ENV": "development"}, True),
            ({"DAZZLE_ENV": "test"}, True),
            ({"DAZZLE_ENV": "production"}, False),
            ({"DAZZLE_MODE": "trial"}, True),
            ({"DAZZLE_MODE": "qa"}, True),
            ({"DAZZLE_ENV": "DEV"}, True),  # case-insensitive
            # FORCE=1 escape hatch overrides dev/trial
            ({"DAZZLE_ENV": "dev", "DAZZLE_ANALYTICS_FORCE": "1"}, False),
            ({"DAZZLE_MODE": "trial", "DAZZLE_ANALYTICS_FORCE": "1"}, False),
            # Only "1" bypasses; other values ignored
            ({"DAZZLE_ENV": "dev", "DAZZLE_ANALYTICS_FORCE": "true"}, True),
        ],
        ids=[
            "default_enabled",
            "dev_env",
            "development_env",
            "test_env",
            "production_env_enabled",
            "trial_mode",
            "qa_mode",
            "case_insensitive",
            "force_overrides_dev",
            "force_overrides_trial",
            "force_must_be_exactly_one",
        ],
    )
    def test_globally_disabled(self, monkeypatch, env_vars, expected) -> None:
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
        assert analytics_globally_disabled() is expected


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
