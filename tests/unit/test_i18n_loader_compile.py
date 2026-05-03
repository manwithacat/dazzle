"""Tests for #955 cycle 5 — .po/.mo workflow + runtime catalogue load.

Cycle 4 added Babel-backed formatting; cycle 5 adds the missing
"actually load translations from disk" piece. The cycle-2
MessageCatalogue exists but, until now, translations were always
registered programmatically. The new loader walks the standard
gettext layout (`locale/<locale>/LC_MESSAGES/messages.{mo,po}`)
and registers each into the catalogue at server boot.

These tests cover:
- Discovery: which file wins when both .po and .mo are present
- Both layout names: `locale/` (canonical) and `locales/` (fallback)
- Babel-backed parsing for .po and .mo
- Minimal regex fallback when Babel isn't installed
- `compile_po_to_mo` round-trip
- The CLI commands that drive the workflow end-to-end
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dazzle.i18n import get_catalogue
from dazzle.i18n.loader import (
    compile_po_to_mo,
    find_translation_files,
    load_translations,
    parse_mo_file,
    parse_po_file,
)

# Skip Babel-backed tests when the optional extra isn't installed.
babel = pytest.importorskip("babel")


# ---------------------------------------------------------------------------
# Test fixtures — generate .po + .mo on disk
# ---------------------------------------------------------------------------


_FRENCH_PO = """\
msgid ""
msgstr ""
"Language: fr\\n"
"Project-Id-Version: test 0.0.0\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=utf-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

msgid "Welcome"
msgstr "Bienvenue"

msgid "Sign in"
msgstr "Connexion"
"""


_GERMAN_PO = """\
msgid ""
msgstr ""
"Language: de\\n"
"Content-Type: text/plain; charset=utf-8\\n"

msgid "Welcome"
msgstr "Willkommen"
"""


@pytest.fixture(autouse=True)
def reset_catalogue():
    """Each test starts with an empty global catalogue."""
    cat = get_catalogue()
    cat.reset()
    yield
    cat.reset()


def _make_locale_tree(root: Path, locale: str, po_text: str) -> Path:
    """Drop a .po into ``root/locale/<locale>/LC_MESSAGES/messages.po``."""
    lc_dir = root / "locale" / locale / "LC_MESSAGES"
    lc_dir.mkdir(parents=True, exist_ok=True)
    po_path = lc_dir / "messages.po"
    po_path.write_text(po_text, encoding="utf-8")
    return po_path


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestFindTranslationFiles:
    def test_finds_po_when_no_mo(self, tmp_path: Path):
        _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        files = find_translation_files(tmp_path)
        assert set(files.keys()) == {"fr"}
        assert files["fr"].suffix == ".po"

    def test_prefers_mo_over_po(self, tmp_path: Path):
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        compile_po_to_mo(po_path)  # writes messages.mo alongside
        files = find_translation_files(tmp_path)
        assert files["fr"].suffix == ".mo"

    def test_locales_fallback_dir(self, tmp_path: Path):
        # Project uses `locales/` (plural) — loader still finds it.
        lc_dir = tmp_path / "locales" / "fr" / "LC_MESSAGES"
        lc_dir.mkdir(parents=True)
        (lc_dir / "messages.po").write_text(_FRENCH_PO, encoding="utf-8")
        files = find_translation_files(tmp_path)
        assert "fr" in files

    def test_no_translations_dir_returns_empty(self, tmp_path: Path):
        # English-only projects shouldn't trip on the loader.
        assert find_translation_files(tmp_path) == {}

    def test_skips_locale_dir_without_lc_messages(self, tmp_path: Path):
        # Misshapen tree — the loader must not register anything for it.
        (tmp_path / "locale" / "fr").mkdir(parents=True)
        assert find_translation_files(tmp_path) == {}


# ---------------------------------------------------------------------------
# parse_po_file / parse_mo_file
# ---------------------------------------------------------------------------


class TestParsers:
    def test_parse_po_returns_msgstr_dict(self, tmp_path: Path):
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        messages = parse_po_file(po_path)
        assert messages == {"Welcome": "Bienvenue", "Sign in": "Connexion"}

    def test_parse_po_skips_empty_msgstr(self, tmp_path: Path):
        # Untranslated entries (msgstr "") are dropped — they'd just
        # mask the source-text fallback otherwise.
        po_text = _FRENCH_PO + '\nmsgid "Untranslated"\nmsgstr ""\n'
        po_path = tmp_path / "messages.po"
        po_path.write_text(po_text, encoding="utf-8")
        messages = parse_po_file(po_path)
        assert "Untranslated" not in messages

    def test_parse_mo_round_trip(self, tmp_path: Path):
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        mo_path = compile_po_to_mo(po_path)
        messages = parse_mo_file(mo_path)
        assert messages["Welcome"] == "Bienvenue"


# ---------------------------------------------------------------------------
# load_translations — end to end
# ---------------------------------------------------------------------------


class TestLoadTranslations:
    def test_registers_into_global_catalogue(self, tmp_path: Path):
        _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        _make_locale_tree(tmp_path, "de", _GERMAN_PO)

        counts = load_translations(tmp_path)
        assert counts == {"fr": 2, "de": 1}

        cat = get_catalogue()
        assert cat.lookup("fr", "Welcome") == "Bienvenue"
        assert cat.lookup("de", "Welcome") == "Willkommen"
        assert cat.lookup("fr", "Sign in") == "Connexion"

    def test_no_translations_returns_empty(self, tmp_path: Path):
        assert load_translations(tmp_path) == {}

    def test_idempotent_register(self, tmp_path: Path):
        _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        load_translations(tmp_path)
        load_translations(tmp_path)  # second call merges, doesn't break
        assert get_catalogue().lookup("fr", "Welcome") == "Bienvenue"

    def test_corrupt_po_logged_not_raised(self, tmp_path: Path, caplog):
        # A bad file must not crash boot.
        po_path = _make_locale_tree(tmp_path, "xx", "garbage not a real po")
        del po_path  # unused — file just needs to exist
        with caplog.at_level("WARNING"):
            counts = load_translations(tmp_path)
        # Either the parser tolerated the garbage and returned empty
        # (which is fine — nothing registered), or it threw and we
        # caught + logged. Either way no crash.
        assert "xx" not in counts


# ---------------------------------------------------------------------------
# compile_po_to_mo
# ---------------------------------------------------------------------------


class TestCompile:
    def test_writes_mo_alongside_po(self, tmp_path: Path):
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        mo_path = compile_po_to_mo(po_path)
        assert mo_path == po_path.with_suffix(".mo")
        assert mo_path.is_file()

    def test_explicit_output_path(self, tmp_path: Path):
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        out = tmp_path / "out.mo"
        result = compile_po_to_mo(po_path, mo_path=out)
        assert result == out
        assert out.is_file()


# ---------------------------------------------------------------------------
# CLI: dazzle i18n init / compile
# ---------------------------------------------------------------------------


class TestI18nCli:
    def test_init_creates_po_seeded_from_pot(self, tmp_path: Path):
        from dazzle.cli.i18n import i18n_app

        pot_path = tmp_path / "locales" / "messages.pot"
        pot_path.parent.mkdir(parents=True)
        pot_path.write_text(
            'msgid ""\nmsgstr ""\n"Project-Id-Version: x\\n"\n\nmsgid "Hello"\nmsgstr ""\n',
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            ["init", "fr", "--pot", str(pot_path), "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 0, result.stdout
        po = tmp_path / "locale" / "fr" / "LC_MESSAGES" / "messages.po"
        assert po.is_file()
        content = po.read_text()
        # Header gained a Language: declaration; msgid block intact.
        assert "Language: fr" in content
        assert 'msgid "Hello"' in content

    def test_init_refuses_overwrite_without_force(self, tmp_path: Path):
        from dazzle.cli.i18n import i18n_app

        pot_path = tmp_path / "locales" / "messages.pot"
        pot_path.parent.mkdir(parents=True)
        pot_path.write_text('msgid ""\nmsgstr ""\n', encoding="utf-8")
        existing_po = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            ["init", "fr", "--pot", str(pot_path), "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 2
        # Original content untouched
        assert "Bienvenue" in existing_po.read_text()

    def test_compile_walks_locale_tree(self, tmp_path: Path):
        from dazzle.cli.i18n import i18n_app

        _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        _make_locale_tree(tmp_path, "de", _GERMAN_PO)
        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            ["compile", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 0, result.stdout
        assert (tmp_path / "locale" / "fr" / "LC_MESSAGES" / "messages.mo").is_file()
        assert (tmp_path / "locale" / "de" / "LC_MESSAGES" / "messages.mo").is_file()

    def test_compile_no_locale_dir_exits_with_hint(self, tmp_path: Path):
        from dazzle.cli.i18n import i18n_app

        runner = CliRunner()
        result = runner.invoke(
            i18n_app,
            ["compile", "--project-root", str(tmp_path)],
        )
        assert result.exit_code == 2
        # stderr captured into output by typer.testing
        combined = (result.stdout or "") + (result.stderr or "")
        assert "init" in combined or "locale/" in combined


# ---------------------------------------------------------------------------
# Babel-missing fallback for parse_po_file
# ---------------------------------------------------------------------------


class TestBabelMissingFallback:
    def test_minimal_po_parser_handles_simple_pairs(self, tmp_path: Path, monkeypatch):
        # Block babel.messages imports so the loader falls back to the
        # regex parser. The minimal parser only handles single-line
        # entries — verify it covers the common case.
        real_import = builtins.__import__

        def _block(name: str, *a: Any, **kw: Any) -> Any:
            if name.startswith("babel.messages"):
                raise ImportError("babel.messages not available")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _block)
        po_path = _make_locale_tree(tmp_path, "fr", _FRENCH_PO)
        messages = parse_po_file(po_path)
        # Single-line entries should still parse.
        assert messages.get("Welcome") == "Bienvenue"
        assert messages.get("Sign in") == "Connexion"
