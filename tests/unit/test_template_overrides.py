"""Tests for the project-level template override system (v0.29.0).

Covers:
- create_jinja_env() with project_templates_dir
- Project templates shadow framework templates
- dz:// prefix accesses framework originals
- configure_project_templates() reconfigures the singleton
- Semantic block tags in layout templates
"""

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
        rendered = tpl.render()  # nosemgrep: direct-use-of-jinja2
        assert "PROJECT BASE" in rendered

    def test_dz_prefix_accesses_framework_originals(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        # Shadow base.html with a project version
        (tmp_path / "base.html").write_text("<html>PROJECT</html>")

        env = create_jinja_env(tmp_path)
        # dz:// prefix should still get the framework original
        tpl = env.get_template("dz://base.html")
        rendered = tpl.render()  # nosemgrep: direct-use-of-jinja2
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
        rendered = tpl.render(nav_items=[], app_name="Test")  # nosemgrep: direct-use-of-jinja2
        assert "My Custom Brand" in rendered
        # The vestigial app_shell.html stub extends base.html — verify the
        # extends chain still walks (base.html emits <!DOCTYPE html>).
        # Phase 4 (v0.67.56): chrome moved to typed AppShell; the stub
        # only preserves block hooks for the override registry.
        assert "DOCTYPE" in rendered or "<html" in rendered.lower()

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
        # badge_class was removed in favour of badge_tone — 0 template
        # consumers per the note at template_renderer.py:96.
        assert "badge_tone" in env.filters
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
            assert "CONFIGURED" in tpl.render()  # nosemgrep: direct-use-of-jinja2
        finally:
            # Restore original singleton
            mod._env = original_env


class TestSemanticBlocks:
    """Semantic {% block %} tags in layout templates allow targeted overrides."""

    def _get_env(self) -> Environment:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        return create_jinja_env()

    @pytest.mark.parametrize(
        ("template", "block_name"),
        [
            ("layouts/app_shell.html", "navbar"),
            ("layouts/app_shell.html", "sidebar"),
            ("layouts/app_shell.html", "sidebar_brand"),
            ("layouts/app_shell.html", "sidebar_nav"),
            ("layouts/app_shell.html", "sidebar_footer"),
            ("components/detail_view.html", "detail_header"),
            ("components/detail_view.html", "detail_fields"),
            ("components/detail_view.html", "detail_transitions"),
            ("components/form.html", "form_header"),
            ("components/form.html", "form_fields"),
            ("components/form.html", "form_actions"),
            ("components/filterable_table.html", "table_header"),
        ],
        ids=lambda v: v.replace("/", "_").replace(".html", "") if "/" in str(v) else str(v),
    )
    def test_template_has_block(self, template: str, block_name: str) -> None:
        env = self._get_env()
        source = env.loader.get_source(env, template)[0]
        assert f"{{% block {block_name} %}}" in source
