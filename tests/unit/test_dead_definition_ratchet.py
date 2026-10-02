"""Gate: no unreferenced module-level definition may accumulate in ``src/``.

A definition nothing calls is not a style nit — it is a claim the codebase makes
about itself that nothing has checked since it was written. Two real instances
found by this analysis on 2026-10-02, both unreferenced across all tracked files
in every language:

* ``http/runtime/auth/connection_create_form.py::leftover_group_map_stay_put`` —
  a one-line predicate left behind when its caller switched to raising
  ``CreateFormError``.
* ``dazzle_e2e/harness.py::run_testspec`` — a batch "run every flow in a
  testspec" wrapper, superseded by looping ``run_flow`` at the call sites and
  never in ``dazzle_e2e.__all__``.

First run after excluding those two: **73 orphans**, seeded into
``fixtures/dead_definitions_baseline.json`` as accepted residue.

## What counts as a reference, and why it is defined that way

The hard part is not finding definitions, it is deciding what "used" means.
Three attempts, all found the hard way by this gate failing on its own commit:

1. *AST reference walk only.* Missed everything reached by string. Dazzle
   dispatches on strings — parser keywords, MCP tool names, IR type names, dict
   keys — so those definitions are genuinely alive.
2. *Word search over every tracked file.* Resurrected orphans from prose. The
   first CHANGELOG entry that named six of the orphans ("create_kafka_bus,
   LayoutKind, OTPRecord, ...") turned them back into references and failed the
   staleness assertion. The explanatory comment added to fix that then named
   three more.
3. *This version.* A reference is **executable text only**:

   * ``.py`` files are parsed, and references are taken from the AST — ``Name``,
     ``Attribute``, ``import`` aliases, and string literals. A comment is not in
     the AST, so no comment anywhere in the repo can resurrect an orphan, and a
     dispatch string still counts. It is also cheaper: an AST parse only runs
     for files whose raw text mentions a candidate at all.
   * Other files (``.yml``, ``.toml``, ``.sh``, ``.j2``, ``.html``, ...) are read
     as text with ``#`` comments stripped, because YAML/TOML/shell config can
     legitimately name a handler in a string.
   * ``.md`` / ``.txt`` are excluded outright. Prose is not a use site, and a
     changelog has to be able to name what it found.

Scope notes:

* Module-level ``def``/``class`` only. Methods are usually called through an
  instance, which is not a name reference in any file.
* Decorated definitions are skipped. This framework registers by decorator
  (``@app.command("version")``, ``@router.get("/x")``, ``@register("tool")``),
  which binds a callable with no use site; skipping them is what keeps every CLI
  command in the repo out of the report.
* Test modules, ``node_modules/`` and build output under ``src/`` are skipped
  (anchored as ``fitness.clones._py_files`` anchors it, so a production module
  that merely contains "test" stays covered).
* Known limitation: two modules defining the same name can mask an orphan, since
  the other module's use counts. That is a false *negative* — this gate never
  blocks a legitimate change, it only occasionally misses dead code. A false
  positive would be worse than useless.

Adding a deliberate, documented keep (a dynamic entry point resolved at runtime):
add ``"relpath::name"`` to ``fixtures/dead_definitions_baseline.json``.
"""

from __future__ import annotations

import ast
import functools
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
_BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "dead_definitions_baseline.json"

#: Scanned for use sites, minus ``.json``/``.css``/``.js`` (a Python identifier
#: is not called from a lockfile or a vendored bundle, and those are most of the
#: bytes in the tree) and minus ``.md``/``.txt`` (prose — see the docstring).
_TEXT_SUFFIXES = frozenset({".cfg", ".html", ".ini", ".j2", ".py", ".sh", ".toml", ".yaml", ".yml"})

#: Formats where ``#`` starts a comment that must not count as a use site.
_HASH_COMMENT = frozenset({".cfg", ".ini", ".sh", ".toml", ".yaml", ".yml"})

_MAX_BYTES = 4_000_000
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HASH_COMMENT_LINE = re.compile(r"#.*$", re.MULTILINE)

_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "build", "dist", ".dazzle", ".venv"})


def _is_test_module(path: Path) -> bool:
    """True for pytest-collected modules — ``Test*``/``test_*`` names are entry
    points, not call sites.

    Anchored the way ``fitness.clones._py_files`` anchors it, so a production
    module whose name merely contains "test" (``testing/``, ``test_design.py``)
    stays covered.
    """
    return path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in path.parts


def _tracked_files() -> list[Path]:
    """Every tracked text file, via git, falling back to a filesystem walk."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"], cwd=_REPO, check=True, capture_output=True, text=True
        )
        rels = [r for r in proc.stdout.split("\0") if r]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return sorted(
            p
            for p in _REPO.rglob("*")
            if p.is_file()
            and ".git" not in p.parts
            and p.suffix in _TEXT_SUFFIXES
            and not _is_test_module(p)
        )
    out: list[Path] = []
    for rel in rels:
        p = _REPO / rel
        if p.suffix in _TEXT_SUFFIXES and p.is_file() and p.stat().st_size < _MAX_BYTES:
            out.append(p)
    return out


def _candidates() -> set[str]:
    """``"relpath::name"`` for every undecorated module-level def/class in src/.

    Definitions themselves are never counted as uses: a ``def helper`` statement
    produces no ``ast.Name``, so the AST reference walk cannot mistake a
    definition for a call. (The word-search version of this gate did, and
    reported a helper dead while its own call site sat ten lines above it.)
    """
    found: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts) or _is_test_module(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(_REPO)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.decorator_list or node.name.startswith("__"):
                continue
            found.add(f"{rel}::{node.name}")
    return found


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the ``Constant`` nodes that are docstrings.

    A docstring is prose that happens to be a string literal. Excluding them keeps
    "a string *value* used as data" (string dispatch, handler maps) counting as a
    reference while "a string that documents the code" does not — otherwise the
    docstring naming the very orphans this gate reports resurrects them, which is
    the third time that trap has been sprung.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return docstrings


def _py_references(text: str, wanted: set[str]) -> Counter[str]:
    """AST-derived reference counts for the wanted names in one Python file.

    Comments are structurally absent from the AST, which is the point: no comment
    in the repo can make an orphan look used. String literals are walked because
    string-keyed dispatch is how this framework wires handlers up — except
    docstrings, which are prose (see :func:`_docstring_nodes`).
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return Counter()
    docstrings = _docstring_nodes(tree)
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in wanted:
                counts[node.id] += 1
        elif isinstance(node, ast.Attribute):
            if node.attr in wanted:
                counts[node.attr] += 1
        elif isinstance(node, ast.alias):
            name = node.asname or node.name.split(".")[-1]
            if name in wanted:
                counts[name] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            for token in _TOKEN.findall(node.value):
                if token in wanted:
                    counts[token] += 1
    return counts


def _text_references(text: str, wanted: set[str], suffix: str) -> Counter[str]:
    """Reference counts from a non-Python file, comments stripped."""
    if suffix in _HASH_COMMENT:
        text = _HASH_COMMENT_LINE.sub("", text)
    return Counter(token for token in _TOKEN.findall(text) if token in wanted)


def _reference_counts(wanted: set[str]) -> Counter[str]:
    """Repo-wide use counts for the candidate names."""
    totals: Counter[str] = Counter()
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Cheap pre-filter: only pay for an AST parse when the raw text mentions
        # a candidate at all.
        if not wanted & set(_TOKEN.findall(text)):
            continue
        if path.suffix == ".py":
            counts = _py_references(text, wanted)
        else:
            counts = _text_references(text, wanted, path.suffix)
        totals.update(counts)
    return totals


@functools.lru_cache(maxsize=1)
def _current_dead() -> tuple[str, ...]:
    """Candidates whose name is never used anywhere in the repository.

    Memoised: both gate assertions ask the same question, and the answer costs
    ~5s.
    """
    candidates = _candidates()
    if not candidates:
        return ()
    # Keys are "relpath::name"; references are matched on the bare name.
    wanted = {key.split("::", 1)[1] for key in candidates}
    totals = _reference_counts(wanted)
    return tuple(sorted(key for key in candidates if not totals.get(key.split("::", 1)[1], 0)))


def test_baseline_is_a_well_formed_list() -> None:
    data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert all(isinstance(e, str) and "::" in e for e in data)


def test_no_new_unreferenced_definition_in_src() -> None:
    baseline = set(json.loads(_BASELINE_PATH.read_text(encoding="utf-8")))
    new = [key for key in _current_dead() if key not in baseline]
    assert not new, (
        "A module-level definition in src/ has no use anywhere in the repository "
        "(code and config; comments and prose do not count). Either wire it up "
        "or delete it — an unreferenced definition is a claim nothing keeps "
        "honest:\n  "
        + "\n  ".join(new)
        + "\nIf it is deliberately reached by a string resolved at runtime, add it "
        "to fixtures/dead_definitions_baseline.json."
    )


def test_baseline_has_no_stale_entries() -> None:
    """A definition that got wired up or deleted is a win — lock it in."""
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    stale = sorted(set(baseline) - set(_current_dead()))
    assert not stale, (
        "fixtures/dead_definitions_baseline.json is ahead of the tree — these "
        "entries are used again (or gone); remove them to lock in the "
        "progress:\n  " + "\n  ".join(stale)
    )


@pytest.mark.parametrize(
    ("source", "is_candidate"),
    [
        # Registered by decorator: the binding creates no use site.
        ("@app.command('version')\ndef version_command():\n    pass\n", False),
        ("def helper():\n    pass\n", True),
        ("class Widget:\n    pass\n", True),
        ("def __dunder__():\n    pass\n", False),
    ],
)
def test_candidate_extraction_skips_registration_and_dunders(
    source: str, is_candidate: bool
) -> None:
    """Every CLI command in this repo is decorated; none of them are dead code."""
    node = ast.parse(source).body[0]
    assert (not node.decorator_list and not node.name.startswith("__")) is is_candidate


def test_a_comment_mentioning_a_name_is_not_a_reference() -> None:
    """The failure mode that made this rewrite necessary.

    Naming an orphan in prose used to resurrect it — first in the CHANGELOG, then
    in the comment explaining that. A comment is not in the AST.
    """
    wanted = {"orphan_name"}
    with_comment = "def caller():\n    # TODO: call orphan_name here one day\n    return 1\n"
    without = "def caller():\n    return 1\n"
    assert not _py_references(with_comment, wanted)
    assert not _py_references(without, wanted)


def test_a_docstring_mentioning_a_name_is_not_a_reference() -> None:
    """The same trap one level deeper: a docstring is a string literal.

    This gate's own docstring names real orphans to explain what it found, and
    doing so used to make them look used again.
    """
    wanted = {"orphan_name"}
    documented = 'def caller():\n    """TODO: wire up orphan_name."""\n    return 1\n'
    assert not _py_references(documented, wanted)
    assert _py_references('X = "orphan_name"\n', wanted)["orphan_name"] == 1


def test_a_string_literal_naming_a_name_is_a_reference() -> None:
    """String dispatch is how this framework wires handlers up; it must count."""
    text = 'HANDLERS = {"index": orphan_name}\n'
    assert _py_references(text, {"orphan_name"})["orphan_name"] == 1


def test_hash_comments_in_config_are_not_references() -> None:
    assert not _text_references("# see orphan_name\n", {"orphan_name"}, ".yml")
    assert _text_references('handler: "orphan_name"\n', {"orphan_name"}, ".yml")["orphan_name"] == 1
