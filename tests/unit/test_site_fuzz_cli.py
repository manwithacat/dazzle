"""Tests for `scripts/site_fuzz.py` — CLI shape + persona handling.

The fuzzer itself is integration-only (needs a running browser +
dazzle serve). These tests cover the parts that should not require
a live server:

  * CLI parser accepts the documented flags
  * Persona id stripping (`admin@example.test` → `admin`)
  * Default seed surfaces bias toward `/app`
  * `Finding` dataclass shape
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Skip cleanly when playwright isn't installed — the fuzzer imports
# `playwright.sync_api` at module top.
pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "site_fuzz.py"


@pytest.fixture(scope="module")
def fuzz_module():
    """Import scripts/site_fuzz.py as a module without it being on
    sys.path."""
    spec = importlib.util.spec_from_file_location("site_fuzz", SCRIPT)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["site_fuzz"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


class TestCliParser:
    def test_defaults_loaded(self, fuzz_module, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["site_fuzz.py"])
        args = fuzz_module.parse_args()
        assert args.base == fuzz_module.DEFAULT_BASE
        assert args.persona == fuzz_module.DEFAULT_PERSONA_EMAIL
        assert args.browser == "chromium"
        assert args.headed is False
        assert args.race_probability == 0.15

    def test_persona_override(self, fuzz_module, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["site_fuzz.py", "--persona", "support@example.test"])
        args = fuzz_module.parse_args()
        assert args.persona == "support@example.test"

    def test_seed_url_repeatable(self, fuzz_module, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "site_fuzz.py",
                "--seed-url",
                "/app/tickets",
                "--seed-url",
                "/app/comments",
            ],
        )
        args = fuzz_module.parse_args()
        assert args.seed_url == ["/app/tickets", "/app/comments"]

    def test_no_race_aliased_to_zero(self, fuzz_module, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["site_fuzz.py", "--no-race"])
        args = fuzz_module.parse_args()
        # parse_args itself doesn't apply the alias — main() does.
        # Verify the flag is captured so main can act on it.
        assert args.no_race is True


# ---------------------------------------------------------------------------
# Persona id stripping
# ---------------------------------------------------------------------------


class TestPersonaIdStripping:
    def test_full_email_strips_to_id(self, fuzz_module):
        # The login flow strips `@example.test` before POSTing to
        # /qa/magic-link, which expects a bare persona_id.
        f = fuzz_module.Fuzzer(
            base="http://localhost:3000",
            email="admin@example.test",
            browser_name="chromium",
            headed=False,
            race_probability=0.0,
            back_probability=0.0,
            findings_path=Path("/tmp/test-findings.jsonl"),
            seed=42,
        )
        # Mirror the inline split done in _login.
        assert f.email.split("@", 1)[0] == "admin"

    def test_bare_id_passes_through(self, fuzz_module):
        f = fuzz_module.Fuzzer(
            base="http://localhost:3000",
            email="support",
            browser_name="chromium",
            headed=False,
            race_probability=0.0,
            back_probability=0.0,
            findings_path=Path("/tmp/test-findings.jsonl"),
            seed=42,
        )
        # Bare id has no `@` → split returns the same string.
        assert f.email.split("@", 1)[0] == "support"


# ---------------------------------------------------------------------------
# Seed surfaces
# ---------------------------------------------------------------------------


class TestSeedSurfaces:
    def test_default_seeds_bias_to_app(self, fuzz_module):
        # Three /app entries vs one / entry — fuzz spends most time
        # under the workspace shell where race conditions live.
        seeds = fuzz_module.SEED_SURFACES
        app_count = sum(1 for s in seeds if s.startswith("/app"))
        marketing_count = sum(1 for s in seeds if s == "/")
        assert app_count >= 3
        assert marketing_count == 1

    def test_custom_seeds_override_defaults(self, fuzz_module):
        f = fuzz_module.Fuzzer(
            base="http://localhost:3000",
            email="admin@example.test",
            browser_name="chromium",
            headed=False,
            race_probability=0.0,
            back_probability=0.0,
            findings_path=Path("/tmp/test-findings.jsonl"),
            seed=None,
            seed_surfaces=["/app/tickets"],
        )
        assert f.seed_surfaces == ["/app/tickets"]

    def test_default_seeds_when_none_passed(self, fuzz_module):
        f = fuzz_module.Fuzzer(
            base="http://localhost:3000",
            email="admin@example.test",
            browser_name="chromium",
            headed=False,
            race_probability=0.0,
            back_probability=0.0,
            findings_path=Path("/tmp/test-findings.jsonl"),
            seed=None,
        )
        assert f.seed_surfaces == list(fuzz_module.SEED_SURFACES)


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------


class TestFinding:
    def test_finding_default_context_empty_dict(self, fuzz_module):
        f = fuzz_module.Finding(
            iter=1,
            url="http://localhost/app",
            category="console-error",
            severity="high",
            message="boom",
        )
        assert f.context == {}

    def test_high_severity_categories_documented(self, fuzz_module):
        # Operator runs --abort-on-error to stop on these — make
        # sure the constant stays aligned with the docstring's
        # "Categories" section.
        for cat in (
            "page-error",
            "htmx-swap-error",
            "htmx-response-error",
            "navigation-timeout",
            "dialog",
        ):
            assert cat in fuzz_module.HIGH_SEVERITY
