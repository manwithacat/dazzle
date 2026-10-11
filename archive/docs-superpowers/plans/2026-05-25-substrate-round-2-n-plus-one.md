# Substrate Round 2: `PA-LLM-08 n_plus_one_in_user_code` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sentinel heuristic `PA-LLM-08` detecting N+1 query patterns in user `app/` Python — closing the next gap from the substrate audit at minimal cost, demonstrating the round-1 substrate is reusable.

**Architecture:** Single `@heuristic` method `check_n_plus_one_in_user_code` on `PythonAuditAgent` plus one module-level helper `_detect_n_plus_one`. Reuses all round-1 infrastructure unchanged: `Finding.catalogue_entry` model field, counter-prior `detectors:` wiring, bidirectional drift test, MCP findings integration test, CI gate.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), pytest, `ast` stdlib for detection. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-25-substrate-round-2-n-plus-one-design.md`.

**Hard scope limit:** total diff must stay under 400 LOC including tests. If a task pushes the diff over, stop and re-scope.

---

## File structure

### Create

| Path | Responsibility |
|---|---|
| `tests/unit/test_python_audit_n_plus_one.py` | Unit tests for `PA-LLM-08`. 6 positive sub-shape tests, 6 negative false-positive guards, 2 integration tests. ~150 LOC. |

### Modify

| Path | Change |
|---|---|
| `src/dazzle/sentinel/agents/python_audit.py` | Add `_QUERYSET_METHODS`, `_REPO_METHODS`, `_LEN_LIKE_BUILTINS` module constants. Add `_detect_n_plus_one(tree, path)` helper. Add `check_n_plus_one_in_user_code` `@heuristic` method on `PythonAuditAgent`. ~80 LOC. |
| `docs/counter-priors/n-plus-one-in-user-code.md` (frontmatter only) | Append `detectors:` block declaring `PA-LLM-08`. |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Bump `SEED_SCHEMA_VERSION` by 1. |
| `CHANGELOG.md` | Add `## [0.76.0] - <today>` section with Added + Agent Guidance entries. |
| Version files (5 lines via `/bump minor`) | `pyproject.toml`, `core.toml`, `CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb`. |

**No new modules. No new CLI surface. No scaffolding changes. No drift test changes — the round-1 bidirectional drift test picks up the new declaration automatically.**

---

## Task 1: `PA-LLM-08` heuristic

The single heuristic. Module-level helpers + `@heuristic` method. TDD: 14 tests first, watch them fail, implement, watch them pass.

**Files:**
- Create: `tests/unit/test_python_audit_n_plus_one.py`
- Modify: `src/dazzle/sentinel/agents/python_audit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_python_audit_n_plus_one.py`:

```python
"""Tests for PA-LLM-08 — N+1 queries in user app code."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_n_plus_one,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: queryset chain shapes
# ---------------------------------------------------------------------------


def test_queryset_chain_all() -> None:
    """`for order in orders: x = order.lines.all()` is the canonical shape."""
    src = "for order in orders:\n    x = order.lines.all()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_queryset_chain_first() -> None:
    """`.first()` after attribute chain on loop var fires."""
    src = "for order in orders:\n    x = order.payments.first()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_queryset_chain_filter_terminator() -> None:
    """Chained .filter().all() fires (terminator at end of chain)."""
    src = "for order in orders:\n    x = order.lines.filter(state='paid').all()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: repo-call shape
# ---------------------------------------------------------------------------


def test_repo_call_with_loopvar_arg() -> None:
    """`<x>_repo.fetch(<loopvar>)` fires."""
    src = "for oid in order_ids:\n    x = order_repo.fetch(oid)\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_repo_call_with_loopvar_attr_arg() -> None:
    """`<x>_repo.list(field=<loopvar>.attr)` fires."""
    src = "for order in orders:\n    x = line_repo.list(order_id=order.id)\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: len-wrapping shape
# ---------------------------------------------------------------------------


def test_len_wrapped_queryset() -> None:
    """`len(<loopvar>.attr.all())` fires through the outer len()."""
    src = "for order in orders:\n    c = len(order.lines.all())\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_negative_attribute_access_no_call() -> None:
    """Plain attribute access on loop var (no method call) doesn't fire."""
    src = "for order in orders:\n    x = order.id\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_method_outside_queryset_set() -> None:
    """`.upper()` is not a queryset terminator."""
    src = "for s in strings:\n    x = s.upper()\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_call_no_loopvar_reference() -> None:
    """Repo call inside a loop whose args don't reference the loop var doesn't fire."""
    src = "for i in range(10):\n    x = order_repo.fetch(static_id)\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_repo_call_outside_loop() -> None:
    """Repo call at module scope doesn't fire."""
    src = "result = repo.list(scope={'x': 1})\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_dict_get_not_treated_as_queryset() -> None:
    """`d.get(k)` must not fire — `get` is excluded from _QUERYSET_METHODS."""
    src = "for k in keys:\n    x = mapping.get(k)\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_for_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-08` on the `for:` line suppresses every hit in the loop body."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n"
        "    for order in orders:  # noqa: PA-LLM-08 - prefetched\n"
        "        x = order.lines.all()\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]


def test_noqa_suppression_on_call_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-08` on the offending call line suppresses just that hit."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n"
        "    for order in orders:\n"
        "        x = order.lines.all()  # noqa: PA-LLM-08\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: heuristic populates Finding correctly
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    """End-to-end: a real PA-LLM-08 finding carries catalogue_entry + URL."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "render.py").write_text(
        "def render(orders):\n"
        "    out = []\n"
        "    for order in orders:\n"
        "        out.append(order.lines.all())\n"
        "    return out\n"
    )

    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_n_plus_one_in_user_code(appspec=None)  # type: ignore[arg-type]

    assert len(findings) == 1
    f = findings[0]
    assert f.heuristic_id == "PA-LLM-08"
    assert f.catalogue_entry == "n-plus-one-in-user-code"
    assert f.remediation is not None
    assert any(
        "docs/counter-priors/n-plus-one-in-user-code.md" in ref
        for ref in f.remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    """tests/ and scripts/ files are out of scope."""
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("for x in xs:\n    y = x.lines.all()\n")

    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/unit/test_python_audit_n_plus_one.py -v`
Expected: FAIL on every test — `_detect_n_plus_one` and `check_n_plus_one_in_user_code` don't exist yet.

- [ ] **Step 3: Add module-level constants + helper**

Modify `src/dazzle/sentinel/agents/python_audit.py`. In the "PA-LLM-07 helpers" section (where `_PRECHECK_EXCEPTIONS` and `_VALIDATION_CALLS` live, around line 65-75 after round 1), add the new constants AFTER the existing ones:

```python
# ---------------------------------------------------------------------------
# PA-LLM-08 helpers — N+1 queries in user app code
# ---------------------------------------------------------------------------

_QUERYSET_METHODS = frozenset({
    "all", "list", "first", "last", "filter", "order_by", "count", "exists",
})
# `get` is deliberately excluded — it collides with dict.get(). The
# unambiguous `<x>_repo.get(...)` shape is covered by _REPO_METHODS below.

_REPO_METHODS = frozenset({
    "list", "fetch", "fetch_by_id", "get", "find",
})

_LEN_LIKE_BUILTINS = frozenset({"len"})
# Conservative start. Backfill audit (#1256) may expand to sum, sorted, etc.


def _names_in_expr(node: ast.AST) -> set[str]:
    """Return every Name id referenced anywhere inside the given expression."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _loop_targets(node: ast.For) -> set[str]:
    """Return the set of names bound by a for-loop target.

    Handles `for x in xs:` and `for x, y in items:` (tuple unpacking).
    """
    target = node.target
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Tuple):
        return {elt.id for elt in target.elts if isinstance(elt, ast.Name)}
    return set()


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
    # The receiver of the queryset method must itself be an attribute access
    # (or chain of them) eventually rooted at a Name == loop variable.
    # A bare `loopvar.all()` is also valid (single-level attribute access).
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
    # Any arg subexpression must reference a loop variable.
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


def _detect_n_plus_one(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Return _ShapeHit records for every N+1-shaped call inside a for-loop body."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        loop_targets = _loop_targets(node)
        if not loop_targets:
            continue
        for body_node in node.body:
            for call in ast.walk(body_node):
                if not isinstance(call, ast.Call):
                    continue
                if _matches_queryset_shape(call, loop_targets):
                    shape = "queryset"
                elif _matches_repo_shape(call, loop_targets):
                    shape = "repo"
                elif _matches_len_wrap_shape(call, loop_targets):
                    shape = "len_wrap"
                else:
                    continue
                hits.append(
                    _ShapeHit(
                        line=call.lineno,
                        snippet=ast.unparse(call) if hasattr(ast, "unparse") else "<call>",
                        shape=shape,
                        try_line=node.lineno,  # reuse try_line slot to carry the for-line
                    )
                )
    return hits
```

The `_ShapeHit` dataclass already exists from round 1 (PA-LLM-07). The `try_line` field is reused to carry the outer `for` statement's line number — this lets the suppression check look at the `for:` line for `# noqa: PA-LLM-08`. (The field's name is historical; a future rename to `outer_line` is fine but out of scope for this slice.)

- [ ] **Step 4: Add the `@heuristic` method**

Append to `class PythonAuditAgent` (after `check_exceptions_as_control_flow` from round 1):

```python
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
                # Suppression: noqa on the call line OR the for-statement line.
                call_line_text = (
                    source_lines[hit.line - 1]
                    if 0 < hit.line <= len(source_lines)
                    else ""
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
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/unit/test_python_audit_n_plus_one.py -v`
Expected: PASS on all 14 tests.

- [ ] **Step 6: Run the wider audit suite**

Run: `pytest tests/ -m "not e2e" -k "sentinel or python_audit"`
Expected: PASS — round 1's 430 tests still green, plus the new 14.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_n_plus_one.py
git commit -m "Add PA-LLM-08: n-plus-one-in-user-code heuristic

Detects the three canonical N+1 shapes catalogued in
docs/counter-priors/n-plus-one-in-user-code.md: queryset-method chain
on loop-variable attribute access, *_repo.<method>(...) with
loop-variable args, and len() wrapping a queryset chain. Scans app/
only; respects # noqa: PA-LLM-08 on the for or call line. Severity
MEDIUM, confidence LIKELY (pre-fetched relations look identical at
AST level)."
```

---

## Task 2: Counter-prior frontmatter wiring

Declare `PA-LLM-08` in the catalogue entry, bump KG seed version. The bidirectional drift test from round 1 (`test_every_declared_detector_resolves`) catches this — no test additions needed.

**Files:**
- Modify: `docs/counter-priors/n-plus-one-in-user-code.md` (frontmatter only)
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`

- [ ] **Step 1: Verify the drift test currently passes**

Before adding the declaration, run:

```bash
pytest tests/unit/test_counter_priors_drift.py -v -k "detector"
```

Expected: PASS — round 1's PA-LLM-07 declaration is wired correctly; PA-LLM-08 is not declared yet so there's nothing to validate.

- [ ] **Step 2: Verify the test would fail if we added an invalid declaration**

Quickly sanity check the bidirectional drift contract is alive. Add a temporary bogus detector to the frontmatter and confirm the test catches it. (Skip this step if you trust round 1's wiring — it's belt-and-braces.)

- [ ] **Step 3: Add the `detectors:` block to the frontmatter**

Modify `docs/counter-priors/n-plus-one-in-user-code.md`. The existing frontmatter ends with:

```yaml
refs:
  adrs: []
  tests: []
---
```

Insert the `detectors:` block immediately after `refs:` and before the closing `---`:

```yaml
refs:
  adrs: []
  tests: []
detectors:
  - id: PA-LLM-08
    agent: PA
    note: covers queryset chains on loop-variable attribute access, *_repo calls with loop-variable args, and len() wrapping. Does not detect prefetched-relation suppression at AST level — author adds `# noqa: PA-LLM-08 — prefetched` when the relation is materialised upstream.
---
```

- [ ] **Step 4: Bump the KG seed schema version**

Find the constant:

```bash
grep -n "SEED_SCHEMA_VERSION" /Volumes/SSD/Dazzle/src/dazzle/mcp/knowledge_graph/seed.py
```

Round 1 bumped it from 15 → 16. Bump to 17.

- [ ] **Step 5: Run the drift tests**

```bash
pytest tests/unit/test_counter_priors_drift.py -v
```

Expected: PASS. Specifically: `test_every_declared_detector_resolves` confirms PA-LLM-08 (declared in frontmatter) exists on `PythonAuditAgent` (added in Task 1).

- [ ] **Step 6: Run the wider drift + KG suite**

```bash
pytest tests/ -m "not e2e" -k "counter_prior or knowledge_graph or seed"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/counter-priors/n-plus-one-in-user-code.md \
        src/dazzle/mcp/knowledge_graph/seed.py
git commit -m "Wire n-plus-one-in-user-code counter-prior to PA-LLM-08

Declares the detector in the frontmatter; the round-1 bidirectional
drift test enforces the contract automatically. KG seed version
bumped 16 → 17."
```

---

## Task 3: Smoke-test against examples + CHANGELOG + bump

The CI gate (round 1's sentinel scan on examples) inherits PA-LLM-08 automatically. Verify locally that none of the 13 bundled example apps trigger the new heuristic before shipping.

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`, `src/dazzle/mcp/semantics_kb/core.toml`, `.claude/CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb` (via `/bump minor`)

- [ ] **Step 1: Smoke-test against every example app**

The PA sentinel scan reads from each example's `dazzle.toml`. Loop over them:

```bash
cd /Volumes/SSD/Dazzle
for dir in examples/*/; do
  if [ -f "$dir/dazzle.toml" ]; then
    echo "=== $dir ==="
    cd "$dir"
    dazzle sentinel scan --agent PA --severity medium 2>&1 | grep -E "PA-LLM-08|count|status" || echo "no PA-LLM-08 findings"
    cd /Volumes/SSD/Dazzle
  fi
done
```

Expected: zero PA-LLM-08 findings on every example. If any fire, classify:
- **Real N+1 in an example app**: STOP and report. Fix the example separately, then resume the slice.
- **False positive**: STOP and tighten the detector. Add a regression test to `tests/unit/test_python_audit_n_plus_one.py` covering the shape that fired incorrectly.

- [ ] **Step 2: Update CHANGELOG**

Open `/Volumes/SSD/Dazzle/CHANGELOG.md`. Find the `## [Unreleased]` heading. Insert a new dated heading immediately AFTER `## [Unreleased]` and BEFORE the `## [0.75.0] - 2026-05-25` heading. Today's date format YYYY-MM-DD. Add the section content:

```markdown
## [0.76.0] - <today>

### Added — agent code quality substrate round 2 (PA-LLM-08 pilot)

- **Sentinel heuristic `PA-LLM-08`** (`n_plus_one_in_user_code`) detects three canonical shapes of N+1 query patterns in user `app/` Python: queryset chains on loop-variable attribute access (`order.lines.all()` inside a for-loop), `*_repo.<method>(...)` calls with loop-variable args, and `len()` wrapping a queryset chain. Severity MEDIUM, confidence LIKELY (false-positive risk from prefetched relations and identically-named non-DB methods). Suppress via `# noqa: PA-LLM-08 — <reason>` on the `for` or call line.
- **Counter-prior `n-plus-one-in-user-code.md` frontmatter** declares `PA-LLM-08`. Round-1 bidirectional drift test (#1255) automatically enforces the contract.

### Agent Guidance

- When writing loops in `app/` that touch related rows, reach for `Repository.aggregate(group_by=..., count="...")` or batched fetch helpers. Don't enumerate. See `docs/counter-priors/n-plus-one-in-user-code.md` for the right shapes.
- Prefetched relations are legitimate: when the relation is materialised upstream of the loop, document the suppression with `# noqa: PA-LLM-08 — prefetched via <upstream-call>`.
- PA-LLM-08 doesn't detect comprehension N+1 yet (`[x.lines.all() for x in xs]`). Treat that shape with the same discipline manually until a follow-up extends the detector.
```

Replace `<today>` with the actual date (use `date +%Y-%m-%d`).

- [ ] **Step 3: Run the full pre-ship gate**

```bash
cd /Volumes/SSD/Dazzle
pytest tests/ -m "not e2e" 2>&1 | tail -5
ruff check src/ tests/ --fix 2>&1 | tail -3
ruff format src/ tests/ 2>&1 | tail -3
mypy src/dazzle 2>&1 | tail -3
```

Expected: pytest all green, ruff clean, mypy clean.

- [ ] **Step 4: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "Document PA-LLM-08 in CHANGELOG under [0.76.0]"
```

- [ ] **Step 5: Bump version**

Run `/bump minor` in the Claude session (this is a controller/skill action, not a subagent action — the executing controller invokes the bump skill).

Expected: version bumps from `0.75.0` to `0.76.0`. The skill updates `pyproject.toml`, `src/dazzle/mcp/semantics_kb/core.toml`, `.claude/CLAUDE.md`, `ROADMAP.md`, `homebrew/dazzle.rb` in one pass.

(Note: round 1 found `core.toml` and `ROADMAP.md` had drifted to 0.72.17. They should be at 0.75.0 now after round 1's catch-up; verify before bumping.)

- [ ] **Step 6: Commit version bump**

```bash
git status   # verify only version files changed
git add pyproject.toml src/dazzle/mcp/semantics_kb/core.toml \
        .claude/CLAUDE.md ROADMAP.md homebrew/dazzle.rb
git commit -m "Release v0.76.0: PA-LLM-08 (n-plus-one-in-user-code)

Round 2 of the agent code quality substrate. Validates the round-1
pipeline is reusable at low cost: one heuristic, one frontmatter
declaration, ~14 tests, no new modules. The substrate is paying its
rent — round 2 cost ~half of round 1."
```

- [ ] **Step 7: Verify diff stays under the scope ceiling**

```bash
git diff main...HEAD --stat
```

Expected: cumulative LOC across all commits on this branch is under 400. If over, the design is leaking — flag it before pushing.

---

## Self-review notes

**Spec coverage:**
- §4 detection logic (three sub-shapes) → Task 1 (heuristic + 6 positive + 5 negative + 2 integration + 1 suppression).
- §5 testing surface → Task 1 unit tests.
- §6 frontmatter wiring → Task 2.
- §7 CHANGELOG + version → Task 3.
- §8 implementation order → preserved as Tasks 1-3 (one heuristic, one wiring, one ship).
- §9 risks — false positives + repo naming + comprehension gap — addressed by:
  - Smoke-test against all 13 examples (Task 3 Step 1) catches real-world false positives before ship.
  - `_REPO_METHODS` brittleness documented in Task 2 frontmatter note.
  - Comprehension gap documented in CHANGELOG Agent Guidance.
- §10 success criteria — 400 LOC ceiling enforced in Task 3 Step 7.

**Placeholder scan:** clean. `<today>` in Task 3 Step 2 is a date placeholder with explicit replacement instruction. No TBDs, no "add validation as appropriate", no "similar to round 1" without showing the actual code.

**Type consistency:** `_ShapeHit` reused from round 1 (with the historical `try_line` field name documented as "carrying the for-line"). `_QUERYSET_METHODS` / `_REPO_METHODS` / `_LEN_LIKE_BUILTINS` declared in Task 1 Step 3, used in Task 1 Step 3's helpers. `check_n_plus_one_in_user_code` method declared in Task 1 Step 4, referenced in Task 1 Step 5 tests AND Task 1 Step 1 imports.

**Ambiguity check:**
- The `try_line` field reuse is documented inline (Task 1 Step 3) — future readers won't be confused.
- The smoke-test step (Task 3 Step 1) tells the engineer how to triage a fire (real vs FP) so they don't paper over.
- `/bump minor` (Task 3 Step 5) is explicitly flagged as a controller-skill invocation, not a subagent action — prevents the subagent from trying to run `/bump` as a shell command.
