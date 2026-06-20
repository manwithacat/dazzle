"""Tests for experience flow state management."""

import time
from unittest.mock import patch

import pytest

from dazzle.page.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    create_initial_state,
    sign_state,
    verify_state,
)


def _tamper_payload(raw: str) -> str:
    """Replace the last 3 chars of the payload portion with 'xyz'."""
    parts = raw.split(".")
    parts[0] = parts[0][:-3] + "xyz"
    return ".".join(parts)


def _tamper_signature(raw: str) -> str:
    """Overwrite the signature portion with repeated 'a'."""
    parts = raw.split(".")
    parts[1] = "a" * len(parts[1])
    return ".".join(parts)


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
    @pytest.mark.parametrize(
        "make_input,expected",
        [
            (
                lambda: _tamper_payload(sign_state(ExperienceState(step="step_1"))),
                None,
            ),
            (
                lambda: _tamper_signature(sign_state(ExperienceState(step="step_1"))),
                None,
            ),
            (lambda: "", None),
            (lambda: "nodothere", None),
            (lambda: "not.valid.base64.data", None),
        ],
        ids=[
            "test_tampered_payload",
            "test_tampered_signature",
            "test_empty_string",
            "test_no_separator",
            "test_garbage_input",
        ],
    )
    def test_verify_state_rejects(self, make_input, expected) -> None:
        assert verify_state(make_input()) is expected


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
