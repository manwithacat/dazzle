"""Tests for dazzle quality init scaffolding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "cli" / "quality_templates"

EXPECTED_TEMPLATES = {"nightly.md", "actions.md", "ux-actions.md", "quality.md"}

PLACEHOLDERS = [
    "persona_list",
    "workspace_list",
    "entity_list",
    "entity_count",
    "persona_workspace_table",
    "site_url",
]


class TestTemplatesExist:
    """Verify that template files are present and contain expected placeholders."""

    def test_all_templates_exist(self) -> None:
        actual = {f.name for f in TEMPLATES_DIR.glob("*.md")}
        assert actual == EXPECTED_TEMPLATES

    @pytest.mark.parametrize("template_name", sorted(EXPECTED_TEMPLATES))
    def test_template_is_non_empty(self, template_name: str) -> None:
        content = (TEMPLATES_DIR / template_name).read_text()
        assert len(content) > 20, f"{template_name} is suspiciously short"

    def test_nightly_has_persona_and_entity_placeholders(self) -> None:
        content = (TEMPLATES_DIR / "nightly.md").read_text()
        assert "{persona_list}" in content
        assert "{entity_count}" in content
        assert "{workspace_list}" in content
        assert "{site_url}" in content

    def test_actions_has_entity_and_persona_placeholders(self) -> None:
        content = (TEMPLATES_DIR / "actions.md").read_text()
        assert "{entity_list}" in content
        assert "{persona_list}" in content

    def test_ux_actions_has_workspace_table_placeholder(self) -> None:
        content = (TEMPLATES_DIR / "ux-actions.md").read_text()
        assert "{persona_workspace_table}" in content

    def test_date_left_as_literal(self) -> None:
        """The {date} placeholder should NOT be in the placeholder list — it stays literal."""
        for name in EXPECTED_TEMPLATES:
            content = (TEMPLATES_DIR / name).read_text()
            # {date} may appear in template text and must survive interpolation
            if "{date}" in content:
                assert "date" not in PLACEHOLDERS


class TestInterpolation:
    """Verify placeholder interpolation replaces all placeholders."""

    def _interpolate(self, content: str) -> str:
        values = {
            "persona_list": "- admin\n- member",
            "workspace_list": "- dashboard\n- inbox",
            "entity_list": "- Task\n- User",
            "entity_count": "2",
            "persona_workspace_table": "| Persona | Workspace |\n|---------|------|",
            "site_url": "http://localhost:3000",
        }
        for key, value in values.items():
            content = content.replace("{" + key + "}", value)
        return content

    @pytest.mark.parametrize("template_name", sorted(EXPECTED_TEMPLATES))
    def test_all_placeholders_replaced(self, template_name: str) -> None:
        raw = (TEMPLATES_DIR / template_name).read_text()
        result = self._interpolate(raw)
        for ph in PLACEHOLDERS:
            assert "{" + ph + "}" not in result, (
                f"Placeholder {{{ph}}} not replaced in {template_name}"
            )

    def test_date_survives_interpolation(self) -> None:
        """The {date} token must remain after interpolation."""
        for name in EXPECTED_TEMPLATES:
            raw = (TEMPLATES_DIR / name).read_text()
            if "{date}" in raw:
                result = self._interpolate(raw)
                assert "{date}" in result, f"{{date}} should survive interpolation in {name}"


class TestInitCommand:
    """Test the init command writes files correctly."""

    def _make_appspec(
        self,
        *,
        personas: list[str] | None = None,
        workspaces: list[tuple[str, list[str]]] | None = None,
        entities: list[str] | None = None,
    ) -> MagicMock:
        appspec = MagicMock()

        # Personas
        if personas:
            persona_mocks = []
            for name in personas:
                p = MagicMock()
                p.id = name
                p.name = name
                persona_mocks.append(p)
            appspec.personas = persona_mocks
        else:
            appspec.personas = []

        # Workspaces
        if workspaces:
            ws_mocks = []
            for ws_name, ws_personas in workspaces:
                ws = MagicMock()
                ws.name = ws_name
                ws.personas = ws_personas
                ws_mocks.append(ws)
            appspec.workspaces = ws_mocks
        else:
            appspec.workspaces = []

        # Entities
        entity_mocks = []
        for name in entities or []:
            e = MagicMock()
            e.name = name
            entity_mocks.append(e)
        appspec.domain.entities = entity_mocks

        return appspec

    def test_writes_all_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        appspec = self._make_appspec(
            personas=["admin", "member"],
            workspaces=[("dashboard", ["admin", "member"])],
            entities=["Task", "User"],
        )

        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _root: appspec,
        )

        from dazzle.cli.quality import init_command

        init_command()

        output_dir = tmp_path / ".claude" / "commands"
        assert output_dir.exists()
        for name in EXPECTED_TEMPLATES:
            assert (output_dir / name).exists(), f"Missing output file: {name}"

    def test_interpolated_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        appspec = self._make_appspec(
            personas=["admin"],
            workspaces=[("dashboard", ["admin"])],
            entities=["Task"],
        )

        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _root: appspec,
        )

        from dazzle.cli.quality import init_command

        init_command()

        nightly = (tmp_path / ".claude" / "commands" / "nightly.md").read_text()
        assert "- admin" in nightly
        assert "1 entities" in nightly
        assert "{persona_list}" not in nightly

    def test_minimal_appspec_no_personas_no_workspaces(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        appspec = self._make_appspec(personas=None, workspaces=None, entities=[])

        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _root: appspec,
        )

        from dazzle.cli.quality import init_command

        init_command()

        nightly = (tmp_path / ".claude" / "commands" / "nightly.md").read_text()
        assert "(no personas defined)" in nightly
        assert "(no workspaces defined)" in nightly
        assert "0 entities" in nightly

    def test_date_placeholder_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        appspec = self._make_appspec(entities=["Task"])

        monkeypatch.setattr(
            "dazzle.cli.utils.load_project_appspec",
            lambda _root: appspec,
        )

        from dazzle.cli.quality import init_command

        init_command()

        nightly = (tmp_path / ".claude" / "commands" / "nightly.md").read_text()
        assert "{date}" in nightly
