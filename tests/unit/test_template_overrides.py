"""Tests for the project-level template override system (v0.29.0).

Covers:
- create_jinja_env() with project_templates_dir
- Project templates shadow framework templates
- dz:// prefix accesses framework originals
- configure_project_templates() reconfigures the singleton
- Semantic block tags in layout templates
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment


@pytest.fixture()
def framework_templates_dir() -> Path:
    """Return the framework templates directory."""
    return Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates"


class TestCreateJinjaEnv:
    """create_jinja_env() loader configuration."""

    def test_without_project_dir_loads_framework(self, framework_templates_dir: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        # Should be able to load a framework template
        tpl = env.get_template("base.html")
        assert tpl is not None

    def test_with_project_dir_shadows_framework(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        # Create a project template that shadows a framework template
        (tmp_path / "base.html").write_text("<html>PROJECT BASE</html>")

        env = create_jinja_env(tmp_path)
        tpl = env.get_template("base.html")
        rendered = tpl.render()
        assert "PROJECT BASE" in rendered

    def test_dz_prefix_accesses_framework_originals(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        # Shadow base.html with a project version
        (tmp_path / "base.html").write_text("<html>PROJECT</html>")

        env = create_jinja_env(tmp_path)
        # dz:// prefix should still get the framework original
        tpl = env.get_template("dz://base.html")
        rendered = tpl.render()
        assert "PROJECT" not in rendered
        assert "Dazzle" in rendered or "DOCTYPE" in rendered

    def test_project_extends_framework_via_dz_prefix(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        # Create a project template that extends the framework layout
        override_content = (
            '{% extends "dz://layouts/app_shell.html" %}\n'
            "{% block sidebar_brand %}\n"
            "<h1>My Custom Brand</h1>\n"
            "{% endblock %}\n"
        )
        layout_dir = tmp_path / "layouts"
        layout_dir.mkdir()
        (layout_dir / "app_shell.html").write_text(override_content)

        env = create_jinja_env(tmp_path)
        tpl = env.get_template("layouts/app_shell.html")
        rendered = tpl.render(nav_items=[], app_name="Test")
        assert "My Custom Brand" in rendered
        # The rest of the shell should still render
        assert "main-content" in rendered

    def test_nonexistent_project_dir_uses_framework_only(self) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env(Path("/nonexistent/dir"))
        tpl = env.get_template("base.html")
        assert tpl is not None

    def test_fallback_to_framework_for_non_overridden_templates(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        # Project dir is valid but has no templates
        env = create_jinja_env(tmp_path)
        # Should still find framework templates
        tpl = env.get_template("base.html")
        assert tpl is not None

    def test_custom_filters_registered(self) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        assert "currency" in env.filters
        assert "dateformat" in env.filters
        assert "badge_class" in env.filters
        assert "bool_icon" in env.filters
        assert "timeago" in env.filters
        assert "slugify" in env.filters


class TestConfigureProjectTemplates:
    """configure_project_templates() reconfigures the singleton."""

    def test_reconfigures_singleton(self, tmp_path: Path) -> None:
        import dazzle_ui.runtime.template_renderer as mod

        # Save original
        original_env = mod._env

        try:
            (tmp_path / "base.html").write_text("<html>CONFIGURED</html>")
            mod.configure_project_templates(tmp_path)

            env = mod.get_jinja_env()
            tpl = env.get_template("base.html")
            assert "CONFIGURED" in tpl.render()
        finally:
            # Restore original singleton
            mod._env = original_env


class TestSemanticBlocks:
    """Semantic {% block %} tags in layout templates allow targeted overrides."""

    def _get_env(self) -> Environment:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        return create_jinja_env()

    def test_app_shell_has_navbar_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "layouts/app_shell.html")[0]
        assert "{% block navbar %}" in source

    def test_app_shell_has_sidebar_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "layouts/app_shell.html")[0]
        assert "{% block sidebar %}" in source

    def test_app_shell_has_sidebar_brand_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "layouts/app_shell.html")[0]
        assert "{% block sidebar_brand %}" in source

    def test_app_shell_has_sidebar_nav_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "layouts/app_shell.html")[0]
        assert "{% block sidebar_nav %}" in source

    def test_app_shell_has_sidebar_footer_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "layouts/app_shell.html")[0]
        assert "{% block sidebar_footer %}" in source

    def test_detail_view_has_header_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/detail_view.html")[0]
        assert "{% block detail_header %}" in source

    def test_detail_view_has_fields_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/detail_view.html")[0]
        assert "{% block detail_fields %}" in source

    def test_detail_view_has_transitions_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/detail_view.html")[0]
        assert "{% block detail_transitions %}" in source

    def test_form_has_header_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/form.html")[0]
        assert "{% block form_header %}" in source

    def test_form_has_fields_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/form.html")[0]
        assert "{% block form_fields %}" in source

    def test_form_has_actions_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/form.html")[0]
        assert "{% block form_actions %}" in source

    def test_table_has_header_block(self) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, "components/filterable_table.html")[0]
        assert "{% block table_header %}" in source
