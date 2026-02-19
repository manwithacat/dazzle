"""Tests for experience flow state management."""

from __future__ import annotations

import time
from unittest.mock import patch

from dazzle_ui.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    create_initial_state,
    sign_state,
    verify_state,
)


class TestCookieName:
    def test_cookie_name_basic(self) -> None:
        assert cookie_name("checkout_flow") == "dz-exp-checkout_flow"

    def test_cookie_name_simple(self) -> None:
        assert cookie_name("onboarding") == "dz-exp-onboarding"


class TestSignVerifyRoundTrip:
    def test_roundtrip_basic(self) -> None:
        state = ExperienceState(step="step_1", completed=[], data={})
        raw = sign_state(state)
        result = verify_state(raw)
        assert result is not None
        assert result.step == "step_1"
        assert result.completed == []
        assert result.data == {}

    def test_roundtrip_with_data(self) -> None:
        state = ExperienceState(
            step="step_2",
            completed=["step_1"],
            data={"Client_id": "abc-123", "amount": 100},
        )
        raw = sign_state(state)
        result = verify_state(raw)
        assert result is not None
        assert result.step == "step_2"
        assert result.completed == ["step_1"]
        assert result.data == {"Client_id": "abc-123", "amount": 100}

    def test_roundtrip_preserves_started_at(self) -> None:
        ts = time.time()
        state = ExperienceState(step="step_1", started_at=ts)
        raw = sign_state(state)
        result = verify_state(raw)
        assert result is not None
        assert abs(result.started_at - ts) < 0.01


class TestTamperDetection:
    def test_tampered_payload(self) -> None:
        state = ExperienceState(step="step_1")
        raw = sign_state(state)
        # Modify the payload portion
        parts = raw.split(".")
        parts[0] = parts[0][:-3] + "xyz"
        tampered = ".".join(parts)
        assert verify_state(tampered) is None

    def test_tampered_signature(self) -> None:
        state = ExperienceState(step="step_1")
        raw = sign_state(state)
        # Modify the signature
        parts = raw.split(".")
        parts[1] = "a" * len(parts[1])
        tampered = ".".join(parts)
        assert verify_state(tampered) is None

    def test_empty_string(self) -> None:
        assert verify_state("") is None

    def test_no_separator(self) -> None:
        assert verify_state("nodothere") is None

    def test_garbage_input(self) -> None:
        assert verify_state("not.valid.base64.data") is None


class TestExpiry:
    def test_expired_state(self) -> None:
        # Create a state with started_at 25 hours ago
        old_ts = time.time() - (25 * 3600)
        state = ExperienceState(step="step_1", started_at=old_ts)
        raw = sign_state(state)
        assert verify_state(raw) is None

    def test_fresh_state(self) -> None:
        state = ExperienceState(step="step_1")
        raw = sign_state(state)
        assert verify_state(raw) is not None


class TestCreateInitialState:
    def test_creates_at_start_step(self) -> None:
        state = create_initial_state("welcome")
        assert state.step == "welcome"
        assert state.completed == []
        assert state.data == {}
        assert state.started_at > 0


class TestSigningKey:
    def test_uses_env_var(self) -> None:
        state = ExperienceState(step="step_1")
        with patch.dict("os.environ", {"DAZZLE_SECRET_KEY": "test-key-123"}):
            raw = sign_state(state)
            result = verify_state(raw)
            assert result is not None
            assert result.step == "step_1"

    def test_different_key_fails(self) -> None:
        state = ExperienceState(step="step_1")
        with patch.dict("os.environ", {"DAZZLE_SECRET_KEY": "key-a"}):
            raw = sign_state(state)
        with patch.dict("os.environ", {"DAZZLE_SECRET_KEY": "key-b"}):
            result = verify_state(raw)
            assert result is None
