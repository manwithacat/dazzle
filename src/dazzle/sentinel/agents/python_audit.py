"""Python Audit detection agent (PA) — detects obsolete Python patterns.

Three detection layers:
1. Ruff profile scan (UP, PTH, ASYNC, C4, SIM rules)
2. Semgrep ruleset (deprecated stdlib, patterns ruff misses)
3. @heuristic methods (LLM training-bias patterns)
"""

from __future__ import annotations

import ast
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.sentinel.agents.base import DetectionAgent, heuristic
from dazzle.sentinel.models import AgentId, Severity

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.sentinel.models import AgentResult, Finding


# ---------------------------------------------------------------------------
# PA-LLM-07 helpers — exceptions as control flow
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc

_PRECHECK_EXCEPTIONS = {"KeyError", "ValueError", "AttributeError", "IndexError"}
_VALIDATION_CALLS = {"int", "float", "Decimal", "bool"}


@_dc(frozen=True)
class _ShapeHit:
    line: int
    snippet: str
    shape: str  # silent_swallow | fallback | validation | conditional
    try_line: int = 0  # lineno of the enclosing try: statement (for noqa lookup)


def _exception_names(handler: ast.ExceptHandler) -> set[str]:
    """Return the set of exception names a handler catches.

    Bare ``except:`` returns the empty set. ``except Exception:`` returns
    {"Exception"}. ``except (KeyError, ValueError):`` returns both.
    """
    if handler.type is None:
        return set()
    if isinstance(handler.type, ast.Name):
        return {handler.type.id}
    if isinstance(handler.type, ast.Tuple):
        return {n.id for n in handler.type.elts if isinstance(n, ast.Name)}
    return set()


def _body_is_pass(body: list[ast.stmt]) -> bool:
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _body_assigns_literal_to(body: list[ast.stmt], target_name: str) -> bool:
    """True if the body's only statement is ``target_name = <Constant>``."""
    if len(body) != 1:
        return False
    stmt = body[0]
    if not isinstance(stmt, ast.Assign):
        return False
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return False
    if stmt.targets[0].id != target_name:
        return False
    return isinstance(stmt.value, ast.Constant)


def _try_body_assigns_name(try_body: list[ast.stmt]) -> str | None:
    """If the try body's last statement is ``name = <expr>``, return name.

    Callers refine on the RHS shape they need.
    """
    if not try_body:
        return None
    stmt = try_body[-1]
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    return stmt.targets[0].id


def _detect_silent_swallow(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 1: ``except [Exception]: pass``."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            names = _exception_names(handler)
            if names and names != {"Exception"}:
                continue  # specific recovery
            if _body_is_pass(handler.body):
                hits.append(
                    _ShapeHit(
                        line=handler.lineno,
                        snippet="except: pass",
                        shape="silent_swallow",
                        try_line=node.lineno,
                    )
                )
    return hits


def _detect_fallback_control_flow(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 2: try body assigns name=<call>; except body assigns name=<literal>.

    Requires the try body's last stmt RHS to be a ``Call`` node — subscript
    and attribute access are handled by _detect_try_as_conditional instead.
    """
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        target_name = _try_body_assigns_name(node.body)
        if target_name is None:
            continue
        # Only match when the try-body RHS is a function/method call
        last_stmt = node.body[-1]
        if not (isinstance(last_stmt, ast.Assign) and isinstance(last_stmt.value, ast.Call)):
            continue
        for handler in node.handlers:
            if _body_assigns_literal_to(handler.body, target_name):
                hits.append(
                    _ShapeHit(
                        line=handler.lineno,
                        snippet=f"{target_name} = <literal>",
                        shape="fallback",
                        try_line=node.lineno,
                    )
                )
    return hits


def _detect_validation_via_exception(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 3: try body calls int()/float()/Decimal(); except sets a flag."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        validation_call = False
        flag_assign: str | None = None
        for stmt in node.body:
            # Discarded validation call: `int(s)` as a bare expression
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                fn = stmt.value.func
                if isinstance(fn, ast.Name) and fn.id in _VALIDATION_CALLS:
                    validation_call = True
            # Assigned validation call: `n = int(s)`
            if (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id in _VALIDATION_CALLS
            ):
                validation_call = True
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is True
            ):
                flag_assign = stmt.targets[0].id
        if not (validation_call and flag_assign):
            continue
        for handler in node.handlers:
            if "ValueError" not in _exception_names(handler):
                continue
            if _body_assigns_literal_to(handler.body, flag_assign):
                hits.append(
                    _ShapeHit(
                        line=handler.lineno,
                        snippet=f"{flag_assign} = False",
                        shape="validation",
                        try_line=node.lineno,
                    )
                )
    return hits


def _try_body_does_precheck_op(
    body: list[ast.stmt],
    exception_names: set[str],
) -> str | None:
    """Return a short description if the try body's single statement is a
    subscript / attr access corresponding to one of the trivial-precheck
    exceptions. Otherwise None.
    """
    if len(body) != 1:
        return None
    stmt = body[0]
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
        return None
    value = stmt.value
    if isinstance(value, ast.Subscript):
        if exception_names & {"KeyError", "IndexError"}:
            return "subscript"
    if isinstance(value, ast.Attribute):
        if "AttributeError" in exception_names:
            return "attribute"
    return None


def _detect_try_as_conditional(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 4: try body is a single subscript/attr access; except assigns literal."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        target_name = _try_body_assigns_name(node.body)
        if target_name is None:
            continue
        for handler in node.handlers:
            names = _exception_names(handler)
            if not (names & _PRECHECK_EXCEPTIONS):
                continue
            op = _try_body_does_precheck_op(node.body, names)
            if op is None:
                continue
            if _body_assigns_literal_to(handler.body, target_name):
                hits.append(
                    _ShapeHit(
                        line=handler.lineno,
                        snippet=f"{target_name} = <{op}>",
                        shape="conditional",
                        try_line=node.lineno,
                    )
                )
    return hits


# ---------------------------------------------------------------------------
# PA-LLM-08 helpers — N+1 queries in user app code
# ---------------------------------------------------------------------------

_QUERYSET_METHODS = frozenset(
    {
        "all",
        "list",
        "first",
        "last",
        "filter",
        "order_by",
        "count",
        "exists",
    }
)
# `get` is deliberately excluded — it collides with dict.get(). The
# unambiguous `<x>_repo.get(...)` shape is covered by _REPO_METHODS below.

_REPO_METHODS = frozenset(
    {
        "list",
        "fetch",
        "fetch_by_id",
        "get",
        "find",
    }
)

_LEN_LIKE_BUILTINS = frozenset({"len"})
# Conservative start. Backfill audit (#1256) may expand to sum, sorted, etc.


def _names_in_expr(node: ast.AST) -> set[str]:
    """Return every Name id referenced anywhere inside the given expression."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _target_names(target: ast.AST) -> set[str]:
    """Return the names bound by an iteration target.

    Shared between `ast.For.target` and `ast.comprehension.target` — both
    have the same shape (a Name or a Tuple of Names).
    """
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Tuple):
        return {elt.id for elt in target.elts if isinstance(elt, ast.Name)}
    return set()


def _loop_targets(node: ast.For) -> set[str]:
    """Return the set of names bound by a for-loop target.

    Handles `for x in xs:` and `for x, y in items:` (tuple unpacking).
    """
    return _target_names(node.target)


def _comprehension_targets(generators: list[ast.comprehension]) -> set[str]:
    """Accumulate every loop-target name across a comprehension's generators.

    For nested comprehensions like `[expr for a in xs for b in a.items]`,
    later generators can reference earlier targets, so we union all of them.
    """
    accumulated: set[str] = set()
    for gen in generators:
        accumulated |= _target_names(gen.target)
    return accumulated


def _comprehension_body_exprs(node: ast.AST) -> list[ast.expr]:
    """Return the per-iteration expressions of a comprehension node.

    Each value here is evaluated once per iteration — so any N+1-shaped call
    inside is an N+1 finding. The `.ifs` predicates inside each generator
    are also per-iteration; included so a queryset terminator in an `if`
    filter doesn't get a free pass.
    """
    bodies: list[ast.expr] = []
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        bodies.append(node.elt)
    elif isinstance(node, ast.DictComp):
        bodies.append(node.key)
        bodies.append(node.value)
    else:
        return []
    for gen in node.generators:
        bodies.extend(gen.ifs)
    return bodies


def _root_of_attribute_chain(node: ast.AST) -> ast.Name | None:
    """Walk an Attribute chain to its root Name. Returns None if not a Name."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node if isinstance(node, ast.Name) else None


def _matches_queryset_shape(call: ast.Call, loop_targets: set[str]) -> bool:
    """Shape 1: <loopvar>.<attr>...<attr>.<queryset_method>(...)."""
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr not in _QUERYSET_METHODS:
        return False
    root = _root_of_attribute_chain(call.func.value)
    return root is not None and root.id in loop_targets


def _matches_repo_shape(call: ast.Call, loop_targets: set[str]) -> bool:
    """Shape 2: <x>_repo.<repo_method>(...) where any arg references a loop var."""
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr not in _REPO_METHODS:
        return False
    if not isinstance(call.func.value, ast.Name):
        return False
    if not call.func.value.id.endswith("_repo"):
        return False
    referenced: set[str] = set()
    for arg in call.args:
        referenced |= _names_in_expr(arg)
    for kw in call.keywords:
        if kw.value is not None:
            referenced |= _names_in_expr(kw.value)
    return bool(referenced & loop_targets)


def _matches_len_wrap_shape(call: ast.Call, loop_targets: set[str]) -> bool:
    """Shape 3: len(<loopvar>.attr.all()) (or another _LEN_LIKE_BUILTINS wrapper)."""
    if not (isinstance(call.func, ast.Name) and call.func.id in _LEN_LIKE_BUILTINS):
        return False
    if not call.args:
        return False
    inner = call.args[0]
    return isinstance(inner, ast.Call) and _matches_queryset_shape(inner, loop_targets)


def _shape_hits_in_body(
    body_nodes: list[ast.AST] | list[ast.stmt] | list[ast.expr],
    targets: set[str],
    outer_lineno: int,
) -> list[_ShapeHit]:
    """Find every N+1-shaped call inside the given body nodes, attributed to outer_lineno.

    When a len-wrap shape is detected, the inner queryset call is *not* reported
    separately — the outer len() node is the canonical hit (identity-tracked
    via id()).
    """
    hits: list[_ShapeHit] = []
    all_calls: list[ast.Call] = []
    for body_node in body_nodes:
        all_calls.extend(c for c in ast.walk(body_node) if isinstance(c, ast.Call))

    len_wrap_inner: set[int] = set()
    for call in all_calls:
        if _matches_len_wrap_shape(call, targets) and call.args:
            len_wrap_inner.add(id(call.args[0]))

    for call in all_calls:
        if _matches_len_wrap_shape(call, targets):
            shape = "len_wrap"
        elif id(call) in len_wrap_inner:
            continue
        elif _matches_queryset_shape(call, targets):
            shape = "queryset"
        elif _matches_repo_shape(call, targets):
            shape = "repo"
        else:
            continue
        snippet = ast.unparse(call) if hasattr(ast, "unparse") else "<call>"
        hits.append(
            _ShapeHit(
                line=call.lineno,
                snippet=snippet,
                shape=shape,
                try_line=outer_lineno,
            )
        )
    return hits


def _detect_n_plus_one(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Return _ShapeHit records for every N+1-shaped call inside a for-loop OR comprehension body.

    Walks both `ast.For` statements and the four comprehension types
    (`ast.ListComp`, `ast.SetComp`, `ast.GeneratorExp`, `ast.DictComp`).
    Nested comprehensions accumulate loop targets across their generators —
    `[expr for a in xs for b in a.items]` has both `a` and `b` in scope for
    `expr`, so a wrong-shape call against either fires.

    Uses the existing _ShapeHit dataclass from round 1 (PA-LLM-07). The
    `try_line` field carries the outer statement's line number so the
    suppression check can match a `# noqa: PA-LLM-08` comment on the for-line
    or the comprehension's opening bracket line. The field name is historical;
    semantically it's now "outer-statement line".
    """
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            targets = _loop_targets(node)
            if not targets:
                continue
            hits.extend(_shape_hits_in_body(list(node.body), targets, node.lineno))
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            targets = _comprehension_targets(node.generators)
            if not targets:
                continue
            body_exprs = _comprehension_body_exprs(node)
            hits.extend(_shape_hits_in_body(list(body_exprs), targets, node.lineno))
    return hits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUFF_SEVERITY: dict[str, Severity] = {
    "UP": Severity.LOW,
    "PTH": Severity.INFO,
    "ASYNC": Severity.MEDIUM,
    "C": Severity.INFO,
    "SIM": Severity.INFO,
}


def _ruff_severity(code: str) -> Severity:
    """Map ruff rule code prefix to sentinel severity."""
    prefix = code.rstrip("0123456789")
    return _RUFF_SEVERITY.get(prefix, Severity.INFO)


def _should_include(min_version_str: str, target: tuple[int, int]) -> bool:
    """Return True if the finding's min Python version <= the project's target."""
    try:
        parts = min_version_str.split(".")
        min_ver = (int(parts[0]), int(parts[1]))
        return min_ver <= target
    except (IndexError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PythonAuditAgent(DetectionAgent):
    """Detects obsolete Python patterns in user project code."""

    def __init__(self, project_path: Path | None = None) -> None:
        self._project_path = project_path or Path.cwd()

    @property
    def agent_id(self) -> AgentId:
        return AgentId.PA

    # ------------------------------------------------------------------
    # Orchestrator entry point
    # ------------------------------------------------------------------

    def run(self, appspec: AppSpec) -> AgentResult:
        """Run all detection layers against user project code."""
        import time

        from dazzle.sentinel.models import AgentResult as AR

        t0 = time.monotonic()
        all_findings: list[Finding] = []
        errors: list[str] = []

        # Layer 1: Ruff
        try:
            all_findings.extend(self._run_ruff())
        except Exception as exc:
            errors.append(f"ruff: {exc}")

        # Layer 2: Semgrep
        try:
            all_findings.extend(self._run_semgrep())
        except Exception as exc:
            errors.append(f"semgrep: {exc}")

        # Layer 3: @heuristic methods
        heuristics = self.get_heuristics()
        for meta, method in heuristics:
            try:
                findings = method(appspec)
                all_findings.extend(findings)
            except Exception as exc:
                errors.append(f"{meta.heuristic_id}: {exc}")

        elapsed = (time.monotonic() - t0) * 1000
        return AR(
            agent=self.agent_id,
            findings=all_findings,
            heuristics_run=len(heuristics) + 2,  # +2 for ruff and semgrep layers
            duration_ms=round(elapsed, 2),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Layer 1: Ruff
    # ------------------------------------------------------------------

    def _run_ruff(self) -> list[Finding]:
        """Run ruff with curated rules and parse JSON output."""
        import subprocess

        scan_paths = [str(d) for d in self._get_scan_dirs() if d.exists()]
        if not scan_paths:
            return []

        major, minor = self._get_target_python_version()
        target = f"py{major}{minor}"

        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--select",
                    "UP,PTH,ASYNC,C4,SIM",
                    "--output-format",
                    "json",
                    "--target-version",
                    target,
                    *scan_paths,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if not result.stdout.strip():
            return []

        try:
            import json

            items = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_ruff_findings(items)

    def _parse_ruff_findings(self, items: list[dict[str, Any]]) -> list[Finding]:
        """Convert ruff JSON items to Finding objects."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
        )

        findings = []
        for item in items:
            code = item.get("code", "")
            message = item.get("message", "")
            filename = item.get("filename", "")
            row = item.get("location", {}).get("row", 0)
            fix_msg = (item.get("fix") or {}).get("message", "")

            findings.append(
                Finding(
                    agent=AgentId.PA,
                    heuristic_id=f"PA-{code}",
                    category="python_audit",
                    subcategory="modernisation",
                    severity=_ruff_severity(code),
                    confidence=Confidence.CONFIRMED,
                    title=f"{code}: {message}",
                    description=message,
                    evidence=[
                        Evidence(
                            evidence_type="source_pattern",
                            location=f"{filename}:{row}",
                        )
                    ],
                    remediation=Remediation(
                        summary=fix_msg or message,
                        effort=RemediationEffort.TRIVIAL,
                    )
                    if fix_msg
                    else None,
                )
            )
        return findings

    # ------------------------------------------------------------------
    # Layer 2: Semgrep
    # ------------------------------------------------------------------

    def _run_semgrep(self) -> list[Finding]:
        """Run semgrep with shipped ruleset and parse JSON output."""
        import subprocess

        ruleset = Path(__file__).parent.parent / "rules" / "python_audit.yml"
        if not ruleset.exists():
            return []

        scan_paths = [str(d) for d in self._get_scan_dirs() if d.exists()]
        if not scan_paths:
            return []

        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "--config",
                    str(ruleset),
                    "--json",
                    "--quiet",
                    *scan_paths,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if not result.stdout.strip():
            return []

        try:
            import json

            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        return self._parse_semgrep_findings(data)

    def _parse_semgrep_findings(self, data: dict[str, Any]) -> list[Finding]:
        """Convert semgrep JSON output to Finding objects."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        findings = []
        for item in data.get("results", []):
            check_id = item.get("check_id", "")
            path = item.get("path", "")
            line = item.get("start", {}).get("line", 0)
            extra = item.get("extra", {})
            message = extra.get("message", "")
            metadata = extra.get("metadata", {})
            snippet = extra.get("lines", "")
            severity_str = metadata.get("sentinel_severity", "MEDIUM").upper()
            severity = getattr(Severity, severity_str, Severity.MEDIUM)

            findings.append(
                Finding(
                    agent=AgentId.PA,
                    heuristic_id=check_id,
                    category="python_audit",
                    subcategory="deprecated_stdlib",
                    severity=severity,
                    confidence=Confidence.CONFIRMED,
                    title=f"{check_id}: {message}",
                    description=message,
                    evidence=[
                        Evidence(
                            evidence_type="source_pattern",
                            location=f"{path}:{line}",
                            snippet=snippet.strip() if snippet else None,
                        )
                    ],
                    remediation=Remediation(
                        summary=message,
                        effort=RemediationEffort.SMALL,
                    ),
                )
            )
        return findings

    # ------------------------------------------------------------------
    # Layer 3: @heuristic methods
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="PA-LLM-01",
        category="python_audit",
        subcategory="llm_bias",
        title="requests library in async codebase — prefer httpx",
    )
    def check_requests_in_async_codebase(self, appspec: AppSpec) -> list[Finding]:
        """Flag `import requests` when project has async code."""
        import ast

        from dazzle.sentinel.models import Confidence, Evidence, Finding, Severity

        files = self._get_python_files()
        has_async = False
        requests_files: list[tuple[Path, int]] = []

        for f in files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    has_async = True
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "requests":
                            requests_files.append((f, node.lineno))
                if isinstance(node, ast.ImportFrom) and node.module == "requests":
                    requests_files.append((f, node.lineno))

        if not has_async:
            return []

        return [
            Finding(
                agent=AgentId.PA,
                heuristic_id="PA-LLM-01",
                category="python_audit",
                subcategory="llm_bias",
                severity=Severity.LOW,
                confidence=Confidence.LIKELY,
                title="requests library used in async codebase",
                description="Project has async code but uses requests (sync-only). httpx provides the same API with native async support.",
                evidence=[
                    Evidence(
                        evidence_type="source_pattern",
                        location=f"{path}:{line}",
                    )
                ],
            )
            for path, line in requests_files
        ]

    @heuristic(
        heuristic_id="PA-LLM-03",
        category="python_audit",
        subcategory="llm_bias",
        title="Manual dunder methods — consider @dataclass",
    )
    def check_manual_dunders(self, appspec: AppSpec) -> list[Finding]:
        """Flag classes with manual __init__ + __repr__/__eq__ but no @dataclass."""
        import ast

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        findings: list[Finding] = []
        dunder_set = {"__init__", "__repr__", "__eq__"}

        for f in self._get_python_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                has_dataclass = any(
                    (isinstance(d, ast.Name) and d.id == "dataclass")
                    or (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)
                        and d.func.id == "dataclass"
                    )
                    or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                    for d in node.decorator_list
                )
                if has_dataclass:
                    continue
                methods = {
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                has_init = "__init__" in methods
                has_other = bool(methods & (dunder_set - {"__init__"}))
                if has_init and has_other:
                    findings.append(
                        Finding(
                            agent=AgentId.PA,
                            heuristic_id="PA-LLM-03",
                            category="python_audit",
                            subcategory="llm_bias",
                            severity=Severity.LOW,
                            confidence=Confidence.POSSIBLE,
                            title=f"Class '{node.name}' has manual dunders — consider @dataclass",
                            description=f"Class '{node.name}' defines __init__ plus __repr__/__eq__ manually. @dataclass generates these automatically.",
                            evidence=[
                                Evidence(
                                    evidence_type="source_pattern",
                                    location=f"{f}:{node.lineno}",
                                )
                            ],
                            remediation=Remediation(
                                summary="Replace with @dataclass and type-annotated fields",
                                effort=RemediationEffort.SMALL,
                            ),
                        )
                    )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-04",
        category="python_audit",
        subcategory="llm_bias",
        title="unittest.TestCase in a pytest project",
    )
    def check_unittest_in_pytest_project(self, appspec: AppSpec) -> list[Finding]:
        """Flag unittest usage when conftest.py exists (indicating pytest)."""
        import ast

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        if not (self._project_path / "conftest.py").exists():
            return []

        findings: list[Finding] = []
        for f in self._get_python_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "unittest":
                            findings.append(
                                Finding(
                                    agent=AgentId.PA,
                                    heuristic_id="PA-LLM-04",
                                    category="python_audit",
                                    subcategory="llm_bias",
                                    severity=Severity.INFO,
                                    confidence=Confidence.LIKELY,
                                    title="unittest used in pytest project",
                                    description="This project uses pytest (conftest.py present) but this file imports unittest. Use pytest functions + fixtures instead.",
                                    evidence=[
                                        Evidence(
                                            evidence_type="source_pattern",
                                            location=f"{f}:{node.lineno}",
                                        )
                                    ],
                                    remediation=Remediation(
                                        summary="Rewrite as pytest functions with assert statements",
                                        effort=RemediationEffort.MEDIUM,
                                    ),
                                )
                            )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-05",
        category="python_audit",
        subcategory="llm_bias",
        title="setup.py alongside pyproject.toml",
    )
    def check_setup_py_with_pyproject(self, appspec: AppSpec) -> list[Finding]:
        """Flag setup.py/setup.cfg when pyproject.toml exists."""
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        root = self._project_path
        if not (root / "pyproject.toml").exists():
            return []

        findings: list[Finding] = []
        for name in ["setup.py", "setup.cfg"]:
            path = root / name
            if path.exists():
                findings.append(
                    Finding(
                        agent=AgentId.PA,
                        heuristic_id="PA-LLM-05",
                        category="python_audit",
                        subcategory="llm_bias",
                        severity=Severity.LOW,
                        confidence=Confidence.LIKELY,
                        title=f"{name} exists alongside pyproject.toml",
                        description=f"Project has pyproject.toml (PEP 621) but also {name}. Consolidate into pyproject.toml.",
                        evidence=[
                            Evidence(
                                evidence_type="source_pattern",
                                location=str(path),
                            )
                        ],
                        remediation=Remediation(
                            summary=f"Migrate {name} contents into pyproject.toml and delete {name}",
                            effort=RemediationEffort.MEDIUM,
                        ),
                    )
                )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-06",
        category="python_audit",
        subcategory="llm_bias",
        title="pip/virtualenv references when uv is available",
    )
    def check_pip_when_uv_available(self, appspec: AppSpec) -> list[Finding]:
        """Flag pip install / virtualenv references when uv.lock exists."""
        import re

        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        root = self._project_path
        if not (root / "uv.lock").exists():
            return []

        pip_pattern = re.compile(r"pip install|virtualenv|python -m venv")
        findings: list[Finding] = []

        for name in ["README.md", "CONTRIBUTING.md", "Makefile", "justfile"]:
            path = root / name
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pip_pattern.search(line):
                    findings.append(
                        Finding(
                            agent=AgentId.PA,
                            heuristic_id="PA-LLM-06",
                            category="python_audit",
                            subcategory="llm_bias",
                            severity=Severity.INFO,
                            confidence=Confidence.POSSIBLE,
                            title="pip/virtualenv reference in uv project",
                            description=f"Project uses uv (uv.lock present) but {name} references pip/virtualenv. Update docs to use uv commands.",
                            evidence=[
                                Evidence(
                                    evidence_type="source_pattern",
                                    location=f"{path}:{i}",
                                    snippet=line.strip(),
                                )
                            ],
                            remediation=Remediation(
                                summary="Replace pip install with uv pip install, virtualenv with uv venv",
                                effort=RemediationEffort.TRIVIAL,
                            ),
                        )
                    )
                    break  # One finding per file is enough
        return findings

    @heuristic(
        heuristic_id="PA-LLM-07",
        category="python_audit",
        subcategory="llm_bias",
        title="exceptions used as control flow",
    )
    def check_exceptions_as_control_flow(self, appspec: AppSpec) -> list[Finding]:
        """Flag the four canonical wrong shapes of try/except misuse.

        See docs/counter-priors/exceptions-as-control-flow.md for the
        full taxonomy and why these patterns are corrosive.
        """
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        app_dir = self._project_path / "app"
        if not app_dir.exists():
            return []

        detectors = (
            ("silent_swallow", _detect_silent_swallow, Confidence.CONFIRMED),
            ("fallback", _detect_fallback_control_flow, Confidence.LIKELY),
            ("validation", _detect_validation_via_exception, Confidence.LIKELY),
            ("conditional", _detect_try_as_conditional, Confidence.CONFIRMED),
        )

        catalogue_url = (
            "https://github.com/cyfutureuk/dazzle/blob/main/"
            "docs/counter-priors/exceptions-as-control-flow.md"
        )

        findings: list[Finding] = []
        for py_file in sorted(app_dir.rglob("*.py")):
            try:
                source_text = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source_text, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue
            source_lines = source_text.splitlines()

            for shape_name, detector, confidence in detectors:
                for hit in detector(tree, py_file):
                    # Check for noqa suppression on: handler line, line above handler,
                    # or the try: line itself (hit.try_line).
                    handler_text = (
                        source_lines[hit.line - 1] if 0 < hit.line <= len(source_lines) else ""
                    )
                    if "noqa: PA-LLM-07" in handler_text:
                        continue
                    above_handler = (
                        source_lines[hit.line - 2]
                        if hit.line >= 2 and hit.line - 2 < len(source_lines)
                        else ""
                    )
                    if "noqa: PA-LLM-07" in above_handler:
                        continue
                    try_line_text = (
                        source_lines[hit.try_line - 1]
                        if hit.try_line and 0 < hit.try_line <= len(source_lines)
                        else ""
                    )
                    if "noqa: PA-LLM-07" in try_line_text:
                        continue
                    findings.append(
                        Finding(
                            agent=AgentId.PA,
                            heuristic_id="PA-LLM-07",
                            category="python_audit",
                            subcategory="llm_bias",
                            severity=Severity.MEDIUM,
                            confidence=confidence,
                            title=f"Exceptions as control flow ({shape_name})",
                            description=(
                                f"This try/except matches the {shape_name!r} antipattern from "
                                "the counter-prior catalogue. See linked entry for the right shape."
                            ),
                            evidence=[
                                Evidence(
                                    evidence_type="source_pattern",
                                    location=f"{py_file}:{hit.line}",
                                    snippet=hit.snippet,
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    "Replace with explicit conditional / structured error / "
                                    "specific exception + recovery."
                                ),
                                effort=RemediationEffort.SMALL,
                                guidance=(
                                    "See docs/counter-priors/exceptions-as-control-flow.md "
                                    "for the four canonical wrong shapes and the right shapes."
                                ),
                                references=[catalogue_url],
                            ),
                            catalogue_entry="exceptions-as-control-flow",
                        )
                    )
        return findings

    @heuristic(
        heuristic_id="PA-LLM-08",
        category="python_audit",
        subcategory="llm_bias",
        title="N+1 queries in user app code",
    )
    def check_n_plus_one_in_user_code(self, appspec: AppSpec) -> list[Finding]:
        """Flag the three canonical shapes of N+1 in user app/ Python.

        See docs/counter-priors/n-plus-one-in-user-code.md for the
        full taxonomy and the right shapes (Repository.aggregate, batched
        fetch, latest_per_group).
        """
        from dazzle.sentinel.models import (
            Confidence,
            Evidence,
            Finding,
            Remediation,
            RemediationEffort,
            Severity,
        )

        app_dir = self._project_path / "app"
        if not app_dir.exists():
            return []

        catalogue_url = (
            "https://github.com/cyfutureuk/dazzle/blob/main/"
            "docs/counter-priors/n-plus-one-in-user-code.md"
        )

        findings: list[Finding] = []
        for py_file in sorted(app_dir.rglob("*.py")):
            try:
                source_text = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source_text, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue
            source_lines = source_text.splitlines()

            for hit in _detect_n_plus_one(tree, py_file):
                call_line_text = (
                    source_lines[hit.line - 1] if 0 < hit.line <= len(source_lines) else ""
                )
                for_line_text = (
                    source_lines[hit.try_line - 1]
                    if hit.try_line and 0 < hit.try_line <= len(source_lines)
                    else ""
                )
                if "noqa: PA-LLM-08" in call_line_text:
                    continue
                if "noqa: PA-LLM-08" in for_line_text:
                    continue

                findings.append(
                    Finding(
                        agent=AgentId.PA,
                        heuristic_id="PA-LLM-08",
                        category="python_audit",
                        subcategory="llm_bias",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=f"N+1 query in loop ({hit.shape})",
                        description=(
                            f"This for-loop body matches the {hit.shape!r} N+1 shape. "
                            "Pull the inner call up to a batched aggregate / fetch "
                            "before the loop. See linked catalogue entry."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="source_pattern",
                                location=f"{py_file}:{hit.line}",
                                snippet=hit.snippet,
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Replace with Repository.aggregate or batched fetch outside the loop."
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "See docs/counter-priors/n-plus-one-in-user-code.md "
                                "for the right shapes (aggregate / latest_per_group / prefetch)."
                            ),
                            references=[catalogue_url],
                        ),
                        catalogue_entry="n-plus-one-in-user-code",
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # Scanning helpers
    # ------------------------------------------------------------------

    def _get_scan_dirs(self) -> list[Path]:
        """Return directories to scan."""
        root = self._project_path
        dirs = []
        for name in ["app", "scripts"]:
            candidate = root / name
            if candidate.is_dir():
                dirs.append(candidate)
        if not dirs:
            dirs.append(root)
        return dirs

    def _get_python_files(self) -> list[Path]:
        """Collect .py files in the user's project (not framework code)."""
        root = self._project_path
        scan_dirs = []
        for d in ["app", "scripts"]:
            candidate = root / d
            if candidate.is_dir():
                scan_dirs.append(candidate)
        # Also include root-level .py files
        scan_dirs.append(root)

        files: list[Path] = []
        skip_dirs = {"__pycache__", ".venv", "node_modules", ".dazzle", ".git"}
        for scan_dir in scan_dirs:
            if scan_dir == root:
                # Only root-level .py files, not recursive
                files.extend(f for f in scan_dir.glob("*.py") if f.is_file())
            else:
                for f in scan_dir.rglob("*.py"):
                    if any(part in skip_dirs for part in f.parts):
                        continue
                    if f.is_file():
                        files.append(f)
        return files

    def _get_target_python_version(self) -> tuple[int, int]:
        """Read requires-python from pyproject.toml, return (major, minor)."""
        pyproject = self._project_path / "pyproject.toml"
        if not pyproject.exists():
            return (3, 10)  # conservative default
        # Malformed pyproject / missing tomllib falls back to the conservative default (#smells-1.1).
        with suppress(Exception):
            import re
            import tomllib

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            requires = data.get("project", {}).get("requires-python", "")
            match = re.search(r"(\d+)\.(\d+)", requires)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        return (3, 10)
