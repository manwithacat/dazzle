"""Tests for demo propose credential generation."""

from __future__ import annotations

from pathlib import Path


class TestGenerateTestPersonasToml:
    def test_generates_toml(self, tmp_path: Path) -> None:
        from dazzle.cli.demo import _generate_test_personas_toml

        blueprint = {
            "personas": [
                {"persona_name": "Teacher", "description": "A teacher"},
                {"persona_name": "Student", "description": "A student"},
            ],
        }
        _generate_test_personas_toml(tmp_path, blueprint)

        toml_path = tmp_path / ".dazzle" / "test_personas.toml"
        assert toml_path.exists()
        content = toml_path.read_text()
        assert "[personas.teacher]" in content
        assert "[personas.student]" in content
        assert "dazzle-test-2026" in content

    def test_does_not_overwrite(self, tmp_path: Path) -> None:
        from dazzle.cli.demo import _generate_test_personas_toml

        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        toml_path = dazzle_dir / "test_personas.toml"
        toml_path.write_text("existing content")

        _generate_test_personas_toml(
            tmp_path,
            {"personas": [{"persona_name": "Admin"}]},
        )
        assert toml_path.read_text() == "existing content"

    def test_no_personas_in_blueprint(self, tmp_path: Path) -> None:
        from dazzle.cli.demo import _generate_test_personas_toml

        _generate_test_personas_toml(tmp_path, {"personas": []})
        assert not (tmp_path / ".dazzle" / "test_personas.toml").exists()

    def test_reads_custom_password_from_config(self, tmp_path: Path) -> None:
        from dazzle.cli.demo import _generate_test_personas_toml

        # Write a dazzle.toml with custom password
        (tmp_path / "dazzle.toml").write_text('[demo]\ntest_password = "custom-pass-42"\n')

        _generate_test_personas_toml(
            tmp_path,
            {"personas": [{"persona_name": "Admin"}]},
        )
        content = (tmp_path / ".dazzle" / "test_personas.toml").read_text()
        assert "custom-pass-42" in content
