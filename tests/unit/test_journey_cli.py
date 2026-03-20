"""Tests for dazzle e2e journey CLI — preflight logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer


class TestJourneyPreflight:
    def test_playwright_not_importable(self) -> None:
        from dazzle.cli.e2e import _journey_preflight

        with (
            patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}),
            patch("importlib.import_module", side_effect=ImportError("no playwright")),
            pytest.raises(typer.Exit),
        ):
            _journey_preflight("http://localhost:3000", Path("/tmp/fake"))

    def test_credential_file_missing(self, tmp_path: Path) -> None:
        from dazzle.cli.e2e import _journey_preflight

        with (
            patch("dazzle.cli.e2e._check_playwright", return_value=True),
            pytest.raises(typer.Exit),
        ):
            _journey_preflight("http://localhost:3000", tmp_path)

    def test_deployment_unreachable(self, tmp_path: Path) -> None:
        from dazzle.cli.e2e import _journey_preflight

        # Create credential file
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        (dazzle_dir / "test_personas.toml").write_text(
            '[personas.admin]\nemail = "a@b.c"\npassword = "p"\n'
        )

        with (
            patch("dazzle.cli.e2e._check_playwright", return_value=True),
            patch("dazzle.cli.e2e._check_deployment", return_value=(False, "Connection refused")),
            pytest.raises(typer.Exit),
        ):
            _journey_preflight("http://localhost:3000", tmp_path)

    def test_all_checks_pass(self, tmp_path: Path) -> None:
        from dazzle.cli.e2e import _journey_preflight

        # Create credential file
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        (dazzle_dir / "test_personas.toml").write_text(
            '[personas.admin]\nemail = "a@b.c"\npassword = "p"\n'
        )

        with (
            patch("dazzle.cli.e2e._check_playwright", return_value=True),
            patch("dazzle.cli.e2e._check_deployment", return_value=(True, "OK")),
        ):
            # Should not raise
            _journey_preflight("http://localhost:3000", tmp_path)
