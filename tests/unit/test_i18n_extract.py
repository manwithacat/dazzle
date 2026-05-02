"""Tests for `dazzle i18n extract` (#955 cycle 3).

Pinned contracts:

  * `_("...")` calls in templates + Python sources land in the catalogue.
  * Single + double quoted, escaped quotes, kwargs trail are all handled.
  * Skips dot-dirs (.git, .venv, .dazzle), node_modules, __pycache__.
  * .pot output: header metadata + sorted msgids + repo-relative refs.
  * Locations dedupe per (path, line) — multiple matches on one line OK.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.cli.i18n import (
    _read_pot_msgids,
    extract_messages,
    render_pot,
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Build a minimal project tree with templates + Python sources."""
    (tmp_path / "src").mkdir()
    (tmp_path / "templates").mkdir()
    (tmp_path / ".git").mkdir()  # should be skipped
    (tmp_path / "node_modules").mkdir()  # should be skipped
    return tmp_path


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestExtractMsgids:
    def test_double_quoted_in_template(self, project):
        _write(project / "templates" / "page.html", '<h1>{{ _("Welcome") }}</h1>')
        cat = extract_messages([project])
        assert "Welcome" in cat

    def test_single_quoted_in_python(self, project):
        _write(
            project / "src" / "view.py",
            "def greet():\n    return _('Hello there')\n",
        )
        cat = extract_messages([project])
        assert "Hello there" in cat

    def test_with_kwargs_trail(self, project):
        """`_("Welcome {name}", name=user.name)` — extractor stops at
        first arg, ignores trailing kwargs."""
        _write(
            project / "templates" / "p.html",
            '<p>{{ _("Welcome {name}", name=user.name) }}</p>',
        )
        cat = extract_messages([project])
        assert "Welcome {name}" in cat

    def test_escaped_quote_in_msgid(self, project):
        _write(
            project / "src" / "v.py",
            r'msg = _("She said \"hi\"")' + "\n",
        )
        cat = extract_messages([project])
        # Escaped quotes are unescaped in the catalogue (gettext convention)
        assert any('She said "hi"' in m for m in cat)

    def test_dedupes_msgid_with_multiple_locations(self, project):
        _write(
            project / "templates" / "a.html",
            '<h1>{{ _("Sign in") }}</h1>\n',
        )
        _write(
            project / "templates" / "b.html",
            '<h2>{{ _("Sign in") }}</h2>\n',
        )
        cat = extract_messages([project])
        assert len(cat["Sign in"]) == 2
        # Both files captured
        paths = {ref[0].name for ref in cat["Sign in"]}
        assert paths == {"a.html", "b.html"}

    def test_line_numbers_are_one_based(self, project):
        _write(
            project / "templates" / "x.html",
            '\n\n<h1>{{ _("On line 3") }}</h1>\n',
        )
        cat = extract_messages([project])
        assert cat["On line 3"][0][1] == 3

    def test_skips_dot_directories(self, project):
        """`.git`, `.venv`, `.dazzle` etc must not be scanned."""
        _write(project / ".git" / "x.py", "_('From git')\n")
        _write(project / ".venv" / "bin" / "y.py", "_('From venv')\n")
        cat = extract_messages([project])
        assert "From git" not in cat
        assert "From venv" not in cat

    def test_skips_node_modules(self, project):
        _write(project / "node_modules" / "lib" / "x.py", "_('From node_modules')\n")
        cat = extract_messages([project])
        assert "From node_modules" not in cat

    def test_skips_pycache(self, project):
        _write(project / "src" / "__pycache__" / "x.py", "_('From pycache')\n")
        cat = extract_messages([project])
        assert "From pycache" not in cat

    def test_handles_unreadable_files_silently(self, project):
        """Unreadable / binary files don't crash the extractor."""
        binary = project / "src" / "weird.py"
        binary.write_bytes(b"\xff\xfe\x00binary noise\x00\xff")
        # Should not raise
        cat = extract_messages([project])
        # No msgids extracted, but other files still work
        assert isinstance(cat, dict)

    def test_skips_other_extensions(self, project):
        """`.txt`, `.md`, `.json` etc are not scanned."""
        _write(project / "src" / "readme.txt", "_('In a text file')")
        _write(project / "src" / "data.json", '{"x": "_(\\"In JSON\\")"}')
        cat = extract_messages([project])
        assert "In a text file" not in cat
        assert "In JSON" not in cat


class TestRenderPot:
    def test_header_metadata(self, tmp_path):
        cat = {"Welcome": [(tmp_path / "x.html", 1)]}
        pot = render_pot(cat, project_name="myproj", project_version="1.2.3")
        assert "Project-Id-Version: myproj 1.2.3" in pot
        assert 'msgid ""' in pot
        assert "MIME-Version: 1.0" in pot
        assert "charset=utf-8" in pot

    def test_msgids_sorted(self, tmp_path):
        cat = {
            "zebra": [(tmp_path / "x.py", 1)],
            "apple": [(tmp_path / "x.py", 2)],
            "mango": [(tmp_path / "x.py", 3)],
        }
        pot = render_pot(cat, repo_root=tmp_path)
        # `apple` comes before `mango` comes before `zebra`
        apple_pos = pot.find('msgid "apple"')
        mango_pos = pot.find('msgid "mango"')
        zebra_pos = pot.find('msgid "zebra"')
        assert 0 < apple_pos < mango_pos < zebra_pos

    def test_repo_relative_refs(self, tmp_path):
        """`#:` reference paths should be relative to repo_root so the
        .pot diff stays clean across machines."""
        path = tmp_path / "src" / "x.py"
        path.parent.mkdir(parents=True)
        path.write_text("_('hi')\n")
        cat = {"hi": [(path, 1)]}
        pot = render_pot(cat, repo_root=tmp_path)
        assert "#: src/x.py:1" in pot
        assert str(path) not in pot  # absolute path absent

    def test_empty_catalogue_emits_just_header(self):
        pot = render_pot({})
        assert 'msgid ""' in pot
        # No body msgids beyond the header
        assert pot.count("msgid") == 1

    def test_escapes_double_quotes_in_msgid(self):
        cat = {'She said "hi"': [(Path("x.py"), 1)]}
        pot = render_pot(cat)
        # The msgid line should escape `"` as `\"`
        assert r'msgid "She said \"hi\""' in pot


class TestReadPotMsgids:
    """Round-trip the .pot file — extract → render → re-read."""

    def test_round_trip(self, tmp_path):
        cat = {
            "Welcome": [(tmp_path / "x.py", 1)],
            "Sign in": [(tmp_path / "y.py", 1)],
            "Goodbye": [(tmp_path / "z.py", 1)],
        }
        pot_path = tmp_path / "messages.pot"
        pot_path.write_text(render_pot(cat, repo_root=tmp_path))
        msgids = _read_pot_msgids(pot_path)
        # Sorted alphabetically by render_pot
        assert sorted(msgids) == sorted(cat.keys())

    def test_skips_empty_header_msgid(self, tmp_path):
        pot_path = tmp_path / "messages.pot"
        pot_path.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
            encoding="utf-8",
        )
        msgids = _read_pot_msgids(pot_path)
        assert msgids == ["Hello"]


class TestCliIntegration:
    """Smoke-test the Typer entry points end-to-end."""

    def test_extract_writes_pot(self, project):
        from typer.testing import CliRunner

        from dazzle.cli.i18n import i18n_app

        _write(project / "templates" / "p.html", '<h1>{{ _("Welcome") }}</h1>')
        out = project / "locales" / "messages.pot"

        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            [
                "extract",
                "--project-root",
                str(project),
                "--output",
                str(out),
                "--source",
                str(project / "templates"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        text = out.read_text()
        assert 'msgid "Welcome"' in text

    def test_stats_without_pot_exits_nonzero(self, project):
        from typer.testing import CliRunner

        from dazzle.cli.i18n import i18n_app

        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            ["stats", "--pot", str(project / "missing.pot")],
        )
        assert result.exit_code == 2

    def test_stats_summarises_translation_coverage(self, project):
        from typer.testing import CliRunner

        from dazzle.cli.i18n import i18n_app
        from dazzle.i18n import get_catalogue, register_translations

        # Reset and register a partial fr translation
        get_catalogue().reset()
        register_translations("fr", {"Welcome": "Bienvenue"})

        # Build a .pot with two msgids — one translated, one not
        pot = project / "messages.pot"
        cat = {
            "Welcome": [(project / "x.py", 1)],
            "Sign in": [(project / "y.py", 1)],
        }
        pot.write_text(render_pot(cat, repo_root=project))

        runner = CliRunner()
        result = runner.invoke(i18n_app, ["stats", "--pot", str(pot)])
        assert result.exit_code == 0, result.output
        assert "Reference msgids" in result.output
        assert "fr: 1/2" in result.output  # 50% coverage

        get_catalogue().reset()
