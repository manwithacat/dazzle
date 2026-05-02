"""``dazzle i18n`` CLI commands (#955 cycle 3).

Today this ships:

  * ``dazzle i18n extract`` — walks templates + Python sources, finds
    every ``_("...")`` call, emits a ``.pot`` (Portable Object Template)
    file. Cycle 4 adds ``.po`` compilation; for now the ``.pot`` is the
    source of truth that adopters hand to translators.
  * ``dazzle i18n stats`` — read-only summary of the in-memory
    catalogue: how many msgids per locale, missing-translation count
    against a freshly extracted .pot.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import typer

i18n_app = typer.Typer(
    help="Internationalisation tools — extract, stats (#955).",
    no_args_is_help=True,
)


# Match `_(...)` calls with a string literal first arg. Handles single-
# and double-quoted strings, escaped quotes, and optional trailing
# kwargs (``_("Hello {name}", name=user.name)``). Multi-line strings
# and f-strings are out of scope — gettext rejects them anyway.
_GETTEXT_CALL_RE = re.compile(
    r"""
    \b_\s*\(\s*                # _( with optional whitespace
    (?:r|u|b)?                  # raw/unicode/bytes prefix
    (                            # group 1: the string literal
        '(?:\\.|[^'\\])*'        #   single-quoted
        |
        "(?:\\.|[^"\\])*"        #   double-quoted
    )
    """,
    re.VERBOSE,
)


# File extensions to scan for `_()` calls. Templates (.html / .jinja)
# carry ~80% of UI strings; .py picks up server-side error messages and
# email bodies registered as Python constants.
_DEFAULT_EXTENSIONS: tuple[str, ...] = (".html", ".jinja", ".jinja2", ".py")


def _iter_source_files(roots: Iterable[Path], extensions: tuple[str, ...]) -> Iterable[Path]:
    """Walk *roots* yielding every file whose suffix is in *extensions*.

    Skips dot-directories (`.git`, `.venv`, `.dazzle`, `__pycache__`)
    and `node_modules` to avoid scanning vendored code.
    """
    skip_dirs = {"__pycache__", "node_modules"}
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix in extensions:
                yield root
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in extensions:
                continue
            # Skip any path containing a hidden directory or known noise.
            if any(part.startswith(".") for part in path.parts):
                continue
            if any(part in skip_dirs for part in path.parts):
                continue
            yield path


def _extract_msgids(text: str) -> list[str]:
    """Return every ``_("...")`` msgid in *text*. Order-preserving,
    duplicates kept (caller dedupes with location tracking).
    """
    out: list[str] = []
    for match in _GETTEXT_CALL_RE.finditer(text):
        literal = match.group(1)
        # Strip surrounding quotes; unescape common backslash sequences.
        unquoted = literal[1:-1]
        unquoted = unquoted.encode("utf-8").decode("unicode_escape")
        out.append(unquoted)
    return out


def _line_of(text: str, offset: int) -> int:
    """1-based line number of *offset* in *text*."""
    return text.count("\n", 0, offset) + 1


def extract_messages(roots: list[Path]) -> dict[str, list[tuple[Path, int]]]:
    """Walk *roots*, return ``{msgid: [(path, line), ...]}``.

    Locations are 1-based ``(path, line)`` tuples — gettext .pot files
    show them as ``#: path:line`` reference comments.
    """
    catalogue: dict[str, list[tuple[Path, int]]] = {}
    for path in _iter_source_files(roots, _DEFAULT_EXTENSIONS):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Skip unreadable / binary files silently — not the
            # extractor's job to surface I/O errors.
            continue
        for match in _GETTEXT_CALL_RE.finditer(text):
            literal = match.group(1)
            unquoted = literal[1:-1]
            unquoted = unquoted.encode("utf-8").decode("unicode_escape")
            line = _line_of(text, match.start())
            catalogue.setdefault(unquoted, []).append((path, line))
    return catalogue


def render_pot(
    catalogue: dict[str, list[tuple[Path, int]]],
    *,
    project_name: str = "dazzle-project",
    project_version: str = "0.0.0",
    repo_root: Path | None = None,
) -> str:
    """Render *catalogue* as a gettext .pot file.

    Format follows the GNU gettext spec: empty msgid header carrying
    metadata, then one block per msgid with ``#:`` reference comments
    (locations) followed by ``msgid``/``msgstr`` lines.

    *repo_root* is used to make ``#:`` paths repo-relative — keeps
    diffs clean when the same project is checked out in different
    absolute paths.
    """
    lines: list[str] = []
    # Header — empty msgid is gettext's metadata convention.
    lines.append("# Translations template for the project.")
    lines.append("# Generated by `dazzle i18n extract` — DO NOT edit by hand.")
    lines.append('msgid ""')
    lines.append('msgstr ""')
    lines.append(f'"Project-Id-Version: {project_name} {project_version}\\n"')
    lines.append('"MIME-Version: 1.0\\n"')
    lines.append('"Content-Type: text/plain; charset=utf-8\\n"')
    lines.append('"Content-Transfer-Encoding: 8bit\\n"')
    lines.append("")

    for msgid in sorted(catalogue.keys()):
        for path, line in sorted(set(catalogue[msgid])):
            ref = (
                path.relative_to(repo_root)
                if repo_root and path.is_relative_to(repo_root)
                else path
            )
            lines.append(f"#: {ref}:{line}")
        # Escape backslashes + double quotes for the msgid literal.
        escaped = msgid.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'msgid "{escaped}"')
        lines.append('msgstr ""')
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


@i18n_app.command("extract")
def extract_command(
    output: Path = typer.Option(
        Path("locales/messages.pot"),
        "--output",
        "-o",
        help="Path to write the .pot file (created if missing).",
    ),
    sources: list[Path] = typer.Option(
        None,
        "--source",
        "-s",
        help="Source root(s) to scan. Defaults to the project root if invoked "
        "inside a Dazzle project.",
    ),
    project_root: Path = typer.Option(
        Path("."),
        "--project-root",
        help="Project root (used to resolve default sources + relative paths).",
    ),
) -> None:
    """Walk templates + Python sources for `_("...")` calls, emit a .pot."""
    if not sources:
        sources = []
        for default in (project_root / "src", project_root / "templates", project_root / "dsl"):
            if default.exists():
                sources.append(default)
        if not sources:
            sources = [project_root]

    catalogue = extract_messages(sources)
    pot_text = render_pot(catalogue, repo_root=project_root.resolve())

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pot_text, encoding="utf-8")
    typer.echo(
        f"Extracted {len(catalogue)} msgid(s) from {len(sources)} source root(s) -> {output}"
    )


@i18n_app.command("stats")
def stats_command(
    pot: Path = typer.Option(
        Path("locales/messages.pot"),
        "--pot",
        help="Path to the .pot file to compare against.",
    ),
) -> None:
    """Summarise the in-memory catalogue against the .pot reference.

    Cycle 3 ships read-only stats — missing translations + locale
    coverage. Cycle 4 will add a ``--check`` flag that fails CI when
    any locale is below a coverage threshold.
    """
    from dazzle.i18n import get_catalogue

    catalogue = get_catalogue()
    locales = catalogue.locales()
    if not pot.exists():
        typer.echo(f"No .pot at {pot}; run `dazzle i18n extract` first.")
        raise typer.Exit(code=2)

    pot_msgids = _read_pot_msgids(pot)
    typer.echo(f"Reference msgids in {pot}: {len(pot_msgids)}")
    typer.echo(f"Registered locales: {locales}")
    for locale in locales:
        translated = sum(1 for m in pot_msgids if catalogue.lookup(locale, m) is not None)
        pct = (translated / len(pot_msgids) * 100) if pot_msgids else 100.0
        typer.echo(f"  {locale}: {translated}/{len(pot_msgids)} ({pct:.1f}%)")


def _read_pot_msgids(pot: Path) -> list[str]:
    """Pull every non-empty ``msgid`` from a .pot file. Empty msgid
    (the header) is skipped."""
    out: list[str] = []
    text = pot.read_text(encoding="utf-8")
    for match in re.finditer(r'^msgid\s+"((?:[^"\\]|\\.)*)"', text, flags=re.MULTILINE):
        msgid = match.group(1).encode("utf-8").decode("unicode_escape")
        if msgid:
            out.append(msgid)
    return out
