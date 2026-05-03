"""Translation file discovery + load (#955 cycle 5).

Reads ``locale/<locale>/LC_MESSAGES/messages.po`` (or ``.mo``) files
under a project root and registers them with the global
:class:`~dazzle.i18n.MessageCatalogue` so the cycle-2 ``_()`` filter
returns translated strings instead of source text.

Layout follows the GNU gettext convention so existing translator
tooling (Poedit, Weblate, Crowdin) drops in unchanged::

    my-project/
      locale/
        fr/
          LC_MESSAGES/
            messages.po          # human-edited
            messages.mo          # compiled — optional, falls back to .po
        de/
          LC_MESSAGES/
            messages.po

Compilation (``.po`` → ``.mo``) is optional. The loader prefers
``.mo`` when present (fastest parse) but reads ``.po`` directly as
a fallback so an adopter can ship translations without running the
compile step.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dazzle.i18n import get_catalogue

logger = logging.getLogger(__name__)

LOCALE_DIR_NAME = "locale"
"""Conventional directory name. ``locales`` (plural) is also accepted as
a fallback so projects that already organise translations under that
name don't have to rename their tree."""

LOCALE_DIR_FALLBACK = "locales"

MESSAGES_BASENAME = "messages"
"""Single domain for now. Multi-domain support (one .po per feature)
is a follow-up if any project actually needs it — most Dazzle apps
fit comfortably in one catalogue."""


def find_translation_files(project_root: Path) -> dict[str, Path]:
    """Return ``{locale: path-to-best-translation-file}``.

    Scans both ``project_root/locale`` and ``project_root/locales`` so
    the framework adapts to whichever convention the project chose.
    Within each locale directory, prefers ``messages.mo`` over
    ``messages.po`` because compiled catalogues parse 10× faster on
    cold start.
    """
    out: dict[str, Path] = {}
    for dir_name in (LOCALE_DIR_NAME, LOCALE_DIR_FALLBACK):
        locale_root = project_root / dir_name
        if not locale_root.is_dir():
            continue
        for locale_dir in locale_root.iterdir():
            if not locale_dir.is_dir():
                continue
            lc_dir = locale_dir / "LC_MESSAGES"
            if not lc_dir.is_dir():
                continue
            mo_path = lc_dir / f"{MESSAGES_BASENAME}.mo"
            po_path = lc_dir / f"{MESSAGES_BASENAME}.po"
            chosen: Path | None = None
            if mo_path.is_file():
                chosen = mo_path
            elif po_path.is_file():
                chosen = po_path
            if chosen is not None:
                # Locale dir name is the locale code (e.g. "fr", "de_DE").
                out[locale_dir.name] = chosen
    return out


def parse_po_file(path: Path) -> dict[str, str]:
    """Parse a ``.po`` file into ``{msgid: msgstr}``.

    Uses Babel's parser when available (handles plurals, contexts,
    multi-line entries) and falls back to a minimal regex-based
    parser when the ``[i18n]`` extra isn't installed. The fallback
    only handles single-line msgid/msgstr pairs — adopters who need
    rich .po features should install Babel.
    """
    try:
        from babel.messages.pofile import read_po
    except ImportError:
        return _parse_po_minimal(path)

    with path.open("rb") as fp:
        catalog = read_po(fp)
    out: dict[str, str] = {}
    for message in catalog:
        msgid = message.id
        if not msgid:
            continue  # skip header (empty msgid)
        if isinstance(msgid, tuple):  # plural form — take singular
            msgid = msgid[0]
        msgstr = message.string
        if isinstance(msgstr, tuple):
            msgstr = msgstr[0] if msgstr and msgstr[0] else ""
        if msgstr:
            out[str(msgid)] = str(msgstr)
    return out


def parse_mo_file(path: Path) -> dict[str, str]:
    """Parse a compiled ``.mo`` file into ``{msgid: msgstr}``.

    Uses Babel's parser; raises if Babel is unavailable since ``.mo``
    is a binary format with no reasonable hand-rolled fallback.
    """
    try:
        from babel.messages.mofile import read_mo
    except ImportError as exc:
        raise RuntimeError(
            "Reading compiled .mo files requires babel — install with "
            "`pip install dazzle-dsl[i18n]` (or use .po files only)"
        ) from exc

    with path.open("rb") as fp:
        catalog = read_mo(fp)
    out: dict[str, str] = {}
    for message in catalog:
        msgid = message.id
        if not msgid:
            continue
        if isinstance(msgid, tuple):
            msgid = msgid[0]
        msgstr = message.string
        if isinstance(msgstr, tuple):
            msgstr = msgstr[0] if msgstr and msgstr[0] else ""
        if msgstr:
            out[str(msgid)] = str(msgstr)
    return out


def _parse_po_minimal(path: Path) -> dict[str, str]:
    """Minimal regex-based .po parser used when Babel isn't installed.

    Handles the common case: single-line ``msgid "..."`` followed by
    ``msgstr "..."``. Skips entries with empty msgstr (untranslated)
    and the header. Multi-line entries, plurals, and contexts are
    silently dropped — install Babel for full coverage.
    """
    import re

    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'^msgid\s+"((?:[^"\\]|\\.)*)"\s*\nmsgstr\s+"((?:[^"\\]|\\.)*)"',
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        msgid_raw = match.group(1)
        msgstr_raw = match.group(2)
        if not msgid_raw or not msgstr_raw:
            continue
        try:
            msgid = msgid_raw.encode("utf-8").decode("unicode_escape")
            msgstr = msgstr_raw.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            continue
        out[msgid] = msgstr
    return out


def load_translations(project_root: Path) -> dict[str, int]:
    """Discover + register every translation file under *project_root*.

    Called during server startup so the cycle-2 ``_()`` filter starts
    returning translated strings as soon as the first request arrives.
    Idempotent — calling twice merges entries without duplicating.

    Returns ``{locale: msgid_count}`` so callers can log / surface the
    coverage. Empty dict means no translations were found (typical for
    apps that haven't shipped any yet).
    """
    files = find_translation_files(project_root)
    if not files:
        return {}

    catalogue = get_catalogue()
    counts: dict[str, int] = {}
    for locale, path in files.items():
        try:
            messages = parse_mo_file(path) if path.suffix == ".mo" else parse_po_file(path)
        except Exception as exc:
            logger.warning(
                "Failed to load translations for locale %s from %s: %s",
                locale,
                path,
                exc,
            )
            continue
        if not messages:
            continue
        catalogue.register(locale, messages)
        counts[locale] = len(messages)
    if counts:
        logger.info(
            "Loaded translations for %d locale(s): %s",
            len(counts),
            ", ".join(f"{loc} ({n})" for loc, n in sorted(counts.items())),
        )
    return counts


def compile_po_to_mo(po_path: Path, mo_path: Path | None = None) -> Path:
    """Compile a ``.po`` file to a ``.mo`` binary.

    The ``.mo`` is written next to the ``.po`` (or to *mo_path* when
    given). Returns the written path so callers can log / report.
    Requires Babel — raises with a clear install hint otherwise.
    """
    try:
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po
    except ImportError as exc:
        raise RuntimeError(
            "Compiling .po → .mo requires babel — install with `pip install dazzle-dsl[i18n]`"
        ) from exc

    if mo_path is None:
        mo_path = po_path.with_suffix(".mo")
    with po_path.open("rb") as fp:
        catalog = read_po(fp)
    mo_path.parent.mkdir(parents=True, exist_ok=True)
    with mo_path.open("wb") as fp:
        write_mo(fp, catalog)
    return mo_path


__all__ = [
    "LOCALE_DIR_FALLBACK",
    "LOCALE_DIR_NAME",
    "MESSAGES_BASENAME",
    "compile_po_to_mo",
    "find_translation_files",
    "load_translations",
    "parse_mo_file",
    "parse_po_file",
]
