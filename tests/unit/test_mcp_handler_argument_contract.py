"""#1751 / #1756 — the handler↔schema contract gate.

`test_api_surface_drift.py` proves a tool's *schema* has not changed. It cannot
prove the schema and the handler agree, and when they disagree nothing says so:

* a handler reading a key the schema does not declare is unreachable by any
  caller following the published interface (#1750: `graph related` read
  `entity_id` where the schema says `name`, then got handed the whole graph);
* a schema key no handler reads is advertised, accepted, and silently ignored
  (#1753: `sentinel findings` declared `severity_threshold` and filtered by
  `severity` instead — 24 findings returned for a "high and above" filter).

Neither is visible to a human reading the schema, which is why five more pairs
survived a drift-gated surface (#1756).

The check is an AST walk — handlers are plain functions over
`arguments: dict[str, Any]`, so `arguments.get("<literal>")` is enough. No
imports, no execution, no MCP session.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from dazzle.mcp.server.handlers_consolidated import CONSOLIDATED_TOOL_HANDLERS
from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

pytestmark = pytest.mark.gate

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
CONSOLIDATED = REPO_SRC / "dazzle" / "mcp" / "server" / "handlers_consolidated.py"

# Keys the dispatcher injects itself. Deliberately not declared in the schemas —
# the MCP client never sends them.
INJECTED = {
    "_resolved_project_path",
    "_progress",
    "_tool_name",
    "project_root",
}

# Handlers read a key the schema omits on purpose. Each entry needs a reason in
# its value, or `test_allowlist_entries_are_justified` fails — the same
# escape-hatch shape as the other dedup gates. Empty by design: #1756 fixed its
# instances rather than allowlisting them.
# Read by the dispatcher, not by an op handler: `_resolve_project` picks the
# project up from `project_path` before any op runs. Declared on every
# project-scoped tool, so direction B must not report it as unread — but a tool
# whose schema omits it and whose *handler* reads it is still a dead read, so it
# is not in INJECTED.
DISPATCHER_READ = {"project_path"}

ALLOWLIST: dict[str, str] = {}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_candidates(dotted: str) -> list[Path]:
    """Files that may define `dotted`'s members.

    A reference may name a module or a package (`handlers/dsl/`), and a package
    `__init__` usually only re-exports — so the package's own modules are
    searched too. Missing this made `dsl` look like a tool whose handlers read
    nothing, which would have turned the gate into a rubber stamp.
    """
    base = REPO_SRC / dotted.replace(".", "/")
    candidates: list[Path] = []
    if base.with_suffix(".py").exists():
        candidates.append(base.with_suffix(".py"))
    if (base / "__init__.py").exists():
        candidates.append(base / "__init__.py")
        candidates.extend(sorted(p for p in base.glob("*.py") if p.name != "__init__.py"))
    return candidates


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None or not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value
    return constants


def _lazy_refs(tree: ast.Module, consts: dict[str, str]) -> dict[str, tuple[str, str]]:
    """`_x = _lazy_import(f"{_MOD}:func")` → name → (module, function).

    Several op tables reference their handler through one of these aliases
    (`_policy_inner`, `_user_profile_inner`) rather than a literal. Missing them
    makes the tool look like it reads nothing, which turns the gate into a
    rubber stamp for exactly the tools it most needs to check.
    """
    refs: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        # Both `x = _lazy_import(...)` and `x: Callable = _lazy_import(...)` —
        # this module uses the annotated form for most aliases.
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)):
            continue
        if value.func.id not in {"_lazy_import", "_lazy_import_async"} or not value.args:
            continue
        resolved = _resolve_ref(value.args[0], consts)
        if resolved:
            for target in targets:
                refs[target.id] = resolved
    return refs


def _resolve_ref(
    ref: ast.expr,
    consts: dict[str, str],
    aliases: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str] | None:
    """Resolve an op-table value to (module, function).

    Accepts `"mod:func"`, `f"{_MOD_X}:func"`, a `_lazy_import` alias name, and a
    bare name bound to a function in handlers_consolidated.py itself.
    """
    if isinstance(ref, ast.Name):
        if aliases and ref.id in aliases:
            return aliases[ref.id]
        return ("dazzle.mcp.server.handlers_consolidated", ref.id)
    if isinstance(ref, ast.Constant) and isinstance(ref.value, str):
        text: str | None = ref.value
    elif isinstance(ref, ast.JoinedStr):
        parts: list[str] = []
        for value in ref.values:
            # `f"{_MOD_X}:func"` parses the name as a FormattedValue, not a Name.
            if isinstance(value, ast.FormattedValue):
                value = value.value
            if isinstance(value, ast.Name) and value.id in consts:
                parts.append(consts[value.id])
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
        text = "".join(parts)
    else:
        return None
    if not text or ":" not in text:
        return None
    module, _, func = text.rpartition(":")
    return (module, func)


def _arg_param(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
    return next((p for p in ("arguments", "args") if p in params), None)


def _is_param_dict(node: ast.expr, param: str) -> bool:
    """Is this expression the arguments dict?

    `args.get(k)` and the defensive `(args or {}).get(k)` are both reads of the
    same dict; the second form appears in handlers that tolerate a missing
    argument, and missing it made the gate report a key nobody reads.
    """
    if isinstance(node, ast.Name):
        return node.id == param
    if isinstance(node, ast.BoolOp):
        return any(isinstance(v, ast.Name) and v.id == param for v in node.values)
    return False


def _reads(fn: ast.FunctionDef | ast.AsyncFunctionDef, param: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "setdefault", "pop"}
            and _is_param_dict(node.func.value, param)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == param
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
    return keys


def _relative_module(current: str, level: int, module: str | None) -> str:
    """Resolve `from ..pkg.mod import x` against the importing module."""
    parts = current.split(".")
    package = parts[:-1]  # `current` names a module, not a package
    for _ in range(level - 1):
        package = package[:-1]
    if module:
        package = package + module.split(".")
    return ".".join(package)


def _imported_aliases(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, current: str
) -> dict[str, tuple[str, str]]:
    """Local names bound by a function-local `from .x import f as g`.

    Several consolidated handlers are one line long — `handle_perf` imports the
    real handler inside the function and returns `_handle(arguments)`. Without
    following the import, every such tool reads nothing and the gate passes it
    vacuously, which is the failure mode a gate must not have.
    """
    aliases: dict[str, tuple[str, str]] = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = _relative_module(current, node.level, node.module)
        for alias in node.names:
            if alias.name != "*":
                aliases[alias.asname or alias.name] = (module, alias.name)
    return aliases


def _expand(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    module: str,
    cache: dict[tuple[str, str], set[str]],
) -> set[str]:
    """Keys read by `fn`, plus the same for the helpers it delegates to.

    Two delegation shapes occur in this codebase and both have to be followed:
    a handler that calls a module-level helper, and a consolidated wrapper that
    imports its real handler inside the function body
    (`handle_perf` → `.handlers.perf.handle_perf`). A gate that cannot see
    through either passes those tools vacuously.
    """
    param = _arg_param(fn)
    if param is None:
        return set()
    keys = _reads(fn, param)
    imported = _imported_aliases(fn, module)
    functions = _module_functions(module)
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        helper = functions.get(node.func.id)
        if helper is not None:
            keys |= _expand(helper, module, cache)
            continue
        target = imported.get(node.func.id)
        if target:
            keys |= _handler_reads(*target, cache)
    return keys


def _module_functions(module: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function across a module's files.

    A package re-exports in `__init__` and defines in its own modules, so a
    handler's helper (`_list_runs_async`) can live in a sibling of the file that
    wraps it. Merging the package is what lets the walk follow that hop;
    stopping at the first file that defines the entry point reported `process`
    as ignoring its own `status` filter.
    """
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in _module_candidates(module):
        functions.update(_functions(_parse(path)))
    return functions


def _handler_reads(module: str, func: str, cache: dict[tuple[str, str], set[str]]) -> set[str]:
    """Keys read by `module:func`."""
    if (module, func) in cache:
        return cache[(module, func)]
    cache[(module, func)] = set()  # cycle guard
    functions = _module_functions(module)
    fn = functions.get(func)
    if fn is None:
        return set()
    keys = _expand(fn, module, cache)
    cache[(module, func)] = keys
    return keys


# ---------------------------------------------------------------------------
# tool → handler reads
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _registry_variable(tree: ast.Module) -> dict[str, str]:
    """tool name → the module-level variable that holds its handler.

    Read from the `CONSOLIDATED_TOOL_HANDLERS = {"graph": handle_graph, …}`
    literal itself. Deriving it from the runtime objects does not work: a
    registry value is the *result* of a factory call, and an AST node's `id()`
    never equals it. Getting this wrong leaves a tool with no handler at all,
    which the gate would then pass vacuously.
    """
    variables: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "CONSOLIDATED_TOOL_HANDLERS" not in targets:
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=False):
            if isinstance(key, ast.Constant) and isinstance(value, ast.Name):
                variables[key.value] = value.id
    return variables


def _tool_reads() -> dict[str, set[str]]:
    """{tool: keys read by its handlers} — union over every op plus the wrapper.

    Built from the registry's own `CONSOLIDATED_TOOL_HANDLERS` map and the op
    tables in handlers_consolidated.py, so a new tool is covered the moment it
    is registered rather than when someone remembers the gate.
    """
    tree = _parse(CONSOLIDATED)
    consts = _module_constants(tree)
    aliases = _lazy_refs(tree, consts)
    variables = _registry_variable(tree)
    cache: dict[tuple[str, str], set[str]] = {}
    reads: dict[str, set[str]] = {tool: set() for tool in CONSOLIDATED_TOOL_HANDLERS}
    this_module = "dazzle.mcp.server.handlers_consolidated"

    # `_make_project_handler("tool", {"op": "mod:func"})` tables.
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in {
            "_make_project_handler",
            "_make_project_handler_async",
            "_make_standalone_handler",
        }:
            continue
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Dict):
            continue
        tool = _norm(node.args[0].value)
        for value in node.args[1].values:
            resolved = _resolve_ref(value, consts, aliases)
            if resolved:
                reads.setdefault(tool, set()).update(_handler_reads(*resolved, cache))

    # Inline `ops = {"op": lambda args: _handle_x(args)}` tables, attributed to
    # whichever handler function owns them (the graph tool).
    tool_of_function = {name: tool for tool, name in variables.items()}
    functions = _functions(tree)
    for name, fn in functions.items():
        for node in ast.walk(fn):
            if not isinstance(node, ast.Dict):
                continue
            imported = _imported_aliases(fn, this_module)
            for value in node.values:
                if isinstance(value, ast.Name) and value.id in imported:
                    # `standalone_ops = {"search": search_api_packs_handler, …}`
                    # built from function-local imports (`handle_api_pack`).
                    reads.setdefault(tool_of_function.get(name, name), set()).update(
                        _handler_reads(*imported[value.id], cache)
                    )
                elif isinstance(value, ast.Lambda):
                    # A lambda body reads arguments too — `populate` filters on
                    # `args.get("root_path")` inside one — so expand the lambda
                    # rather than only chasing the function it calls.
                    reads.setdefault(tool_of_function.get(name, name), set()).update(
                        _expand(value, this_module, cache)
                    )

    # Wrappers: a tool whose handler inspects arguments itself before dispatching
    # (`handle_story` special-cases `view=wall`), or whose handler is a
    # lazy-import alias and so owns no op table.
    for tool in reads:
        variable = variables.get(tool)
        if variable is None:
            continue
        if variable in functions:
            reads[tool] |= _expand(functions[variable], this_module, cache)
        elif variable in aliases:
            reads[tool] |= _handler_reads(*aliases[variable], cache)

    return reads


def _declared() -> dict[str, dict[str, Any]]:
    return {t.name: t.input_schema.get("properties", {}) for t in get_consolidated_tools()}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_no_handler_reads_an_undeclared_key() -> None:
    """Direction A — the capability works, but no caller following the published
    interface can reach it (#1750, #1756)."""
    declared = _declared()
    problems: list[str] = []
    for tool, keys in _tool_reads().items():
        props = declared.get(tool)
        if props is None:
            problems.append(f"{tool}: has a consolidated handler but no tool in the registry")
            continue
        allowed = set(props) | INJECTED | {"operation"}
        for key in sorted(keys - allowed):
            if f"{tool}:{key}" in ALLOWLIST:
                continue
            problems.append(f"{tool}: reads {key!r}, which the schema does not declare")
    assert not problems, "\n".join(problems)


def test_no_declared_key_is_ignored_by_every_handler() -> None:
    """Direction B — the schema advertises a filter that does nothing (#1753)."""
    declared = _declared()
    reads = _tool_reads()
    problems: list[str] = []
    for tool, props in declared.items():
        read = reads.get(tool)
        if read is None:
            continue  # not walked — `test_gate_walks_every_consolidated_tool` reports that
        for key in sorted(set(props) - read - INJECTED - DISPATCHER_READ - {"operation"}):
            if f"{tool}:{key}" in ALLOWLIST:
                continue
            problems.append(f"{tool}: declares {key!r} and no handler reads it")
    assert not problems, "\n".join(problems)


def test_gate_walks_every_consolidated_tool() -> None:
    """Coverage, stated rather than implied. A tool the walk cannot reach is a
    hole in the gate, not a pass — #1751 asked for this to be visible."""
    declared = _declared()
    unwalked = sorted(set(declared) - set(_tool_reads()))
    assert not unwalked, (
        f"gate does not walk: {unwalked}. Either the tool has no consolidated "
        "handler or the walk missed it — silence here is a blind spot."
    )


def test_every_allowlist_entry_is_justified() -> None:
    """A gate that can be silenced silently is not a gate.

    Each allowance must name the tool it applies to, a key that tool's schema
    really declares, and a reason — added in the same commit as the drift it
    excuses, so the next reader can judge it.
    """
    declared = _declared()
    reads = _tool_reads()
    problems: list[str] = []
    for entry, reason in ALLOWLIST.items():
        tool, _, key = entry.partition(":")
        if not reason.strip():
            problems.append(f"{entry}: allowed without a reason")
        if tool not in declared:
            problems.append(f"{entry}: no such tool")
            continue
        if key and key not in declared[tool]:
            problems.append(f"{entry}: the schema does not declare {key!r}")
        if key and key not in reads.get(tool, set()):
            problems.append(f"{entry}: nothing reads {key!r}, so nothing needs allowing")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# The gate's own tests — a detector nobody has falsified is a guess
# ---------------------------------------------------------------------------


def _reads_in(source: str, func: str = "handler") -> set[str]:
    """Keys `_reads` extracts from a synthetic handler."""
    fn = _functions(ast.parse(source))[func]
    param = _arg_param(fn)
    assert param is not None
    return _reads(fn, param)


def test_reads_finds_literal_argument_reads() -> None:
    keys = _reads_in(
        "def handler(arguments):\n"
        "    a = arguments.get('limit')\n"
        "    b = arguments['status']\n"
        "    c = arguments.pop('cursor', None)\n"
        "    return a, b, c\n"
    )
    assert keys == {"limit", "status", "cursor"}


def test_reads_finds_the_defensive_arguments_or_empty_form() -> None:
    """`(args or {}).get(k)` is the same read; missing it reported keys as
    unread for handlers that tolerate a missing argument."""
    assert _reads_in("def handler(args):\n    return (args or {}).get('name')\n") == {"name"}


def test_reads_ignores_other_dicts() -> None:
    """Only the arguments dict counts — otherwise every `.get("id")` in a
    handler would look like an interface key."""
    assert _reads_in("def handler(args):\n    return payload.get('id'), other['k']\n") == set()


def test_walk_sees_through_a_one_line_delegating_wrapper() -> None:
    """`handle_perf` imports its real handler inside the function body. A walk
    that cannot follow that hop would report the tool as reading nothing, and
    the gate would pass it vacuously."""
    from dazzle.mcp.server.handlers_consolidated import handle_perf  # noqa: F401

    reads = _tool_reads()
    assert "run" in reads["perf"], "perf's wrapper delegates to .handlers.perf.handle_perf"


# Tools whose operations genuinely take no arguments beyond `operation`, so an
# empty read set is the truth and not a walk failure. Named rather than
# tolerated silently — #1751 asked for coverage to be reported, not implied.
ARGUMENT_LESS_TOOLS = {"db", "demo_data", "pitch", "semantics"}


def test_walk_finds_a_handler_for_every_registered_tool() -> None:
    """Every tool either reads arguments or is one of the four that take none.

    A tool that reads nothing *and* is not argument-less is a walk failure —
    the state a rubber-stamp gate is in, where the tool passes because nothing
    was inspected.
    """
    reads = _tool_reads()
    unexplained = sorted(
        tool for tool, keys in reads.items() if not keys and tool not in ARGUMENT_LESS_TOOLS
    )
    assert not unexplained, (
        f"walk found no handler for: {unexplained}. Either the tool's handler moved "
        "or the walk lost it — silence here is a blind spot, not a pass."
    )


def test_argument_less_tools_are_still_registered() -> None:
    """If one of these gains an argument, the entry has to be re-examined."""
    assert ARGUMENT_LESS_TOOLS <= set(CONSOLIDATED_TOOL_HANDLERS)
