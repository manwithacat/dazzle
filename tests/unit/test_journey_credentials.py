import logging
from pathlib import Path

import pytest

from dazzle.agent.journey_credentials import load_credentials


@pytest.fixture()
def creds_toml(tmp_path: Path) -> Path:
    """Create a .dazzle/test_personas.toml with two personas."""
    dazzle_dir = tmp_path / ".dazzle"
    dazzle_dir.mkdir()
    toml_path = dazzle_dir / "test_personas.toml"
    toml_path.write_text(
        "[personas.school_admin]\n"
        'email = "admin@oakwood.sch.uk"\n'
        'password = "test-password-123"\n'
        "\n"
        "[personas.teacher]\n"
        'email = "teacher@oakwood.sch.uk"\n'
        'password = "test-password-456"\n'
    )
    return tmp_path


class TestLoadCredentials:
    def test_load_valid_toml(self, creds_toml: Path) -> None:
        result = load_credentials(creds_toml)

        assert result == {
            "school_admin": {
                "email": "admin@oakwood.sch.uk",
                "password": "test-password-123",
            },
            "teacher": {
                "email": "teacher@oakwood.sch.uk",
                "password": "test-password-456",
            },
        }

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="test_personas.toml not found"):
            load_credentials(tmp_path)

    def test_missing_file_message_includes_path(self, tmp_path: Path) -> None:
        expected_path = tmp_path / ".dazzle" / "test_personas.toml"
        with pytest.raises(FileNotFoundError, match=str(expected_path)):
            load_credentials(tmp_path)

    def test_filter_by_persona_names(self, creds_toml: Path) -> None:
        result = load_credentials(creds_toml, persona_filter=["teacher"])

        assert result == {
            "teacher": {
                "email": "teacher@oakwood.sch.uk",
                "password": "test-password-456",
            },
        }
        assert "school_admin" not in result

    def test_filter_missing_persona_logs_warning(
        self, creds_toml: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("dazzle.agent.journey_credentials")
        logger.propagate = True
        with caplog.at_level(logging.WARNING):
            result = load_credentials(creds_toml, persona_filter=["teacher", "student"])

        assert "student" not in result
        assert "teacher" in result
        assert any("student" in record.message for record in caplog.records)

    def test_empty_toml_raises(self, tmp_path: Path) -> None:
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        toml_path = dazzle_dir / "test_personas.toml"
        toml_path.write_text("# empty file\n")

        with pytest.raises(ValueError, match="personas"):
            load_credentials(tmp_path)

    def test_empty_personas_section_raises(self, tmp_path: Path) -> None:
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        toml_path = dazzle_dir / "test_personas.toml"
        toml_path.write_text("[personas]\n")

        with pytest.raises(ValueError, match="personas"):
            load_credentials(tmp_path)

    def test_filter_none_returns_all(self, creds_toml: Path) -> None:
        result = load_credentials(creds_toml, persona_filter=None)
        assert len(result) == 2
