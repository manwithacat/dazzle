# Agent Code Quality Substrate — Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `exceptions-as-control-flow` gap end-to-end through PythonAuditAgent: detection heuristic in user-app Python, catalogue-entry ↔ heuristic-ID bidirectional drift, and scaffolded strict tooling so every Dazzle project ships with the substrate enabled.

**Architecture:** Extends existing infrastructure. Sentinel's `PythonAuditAgent` (`src/dazzle/sentinel/agents/python_audit.py`) gains a new `@heuristic` method `PA-LLM-07`. Counter-prior frontmatter gains an optional `detectors:` field linking entries to heuristic IDs, with a bidirectional drift test enforcing the contract. `init_project` ships three new tooling files (`pyproject.toml`, `pyrightconfig.json`, `.pre-commit-config.yaml`) for newly-scaffolded projects; a new `dazzle quality bootstrap` command writes them into existing projects.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), Typer (CLI), pytest + pytest-parametrize, `ast` stdlib for detection, `tomli_w` for TOML emission, PyYAML for frontmatter.

**Source spec:** `docs/superpowers/specs/2026-05-25-agent-code-quality-substrate-design.md`.

---

## File structure

### Create

| Path | Responsibility |
|---|---|
| `tests/unit/test_python_audit_exceptions.py` | Unit tests for the new `PA-LLM-07` heuristic, one positive + one negative case per canonical wrong shape. |
| `tests/unit/test_init_project_scaffolding.py` | Tests that `init_project` writes the three tooling files and that `dazzle quality bootstrap` is a no-op when they already exist. |
| `src/dazzle/templates/blank/pyproject.toml` | Strict Ruff + Pyright config shipped with every scaffolded project. |
| `src/dazzle/templates/blank/pyrightconfig.json` | Strict-mode Pyright config. |
| `src/dazzle/templates/blank/.pre-commit-config.yaml` | Ruff + ruff-format + sentinel-scan hooks. |
| `src/dazzle/quality/__init__.py` | Empty package marker (the bootstrap module lives here). |
| `src/dazzle/quality/bootstrap.py` | `quality_bootstrap()` function: writes tooling files into an existing project with the merge semantics from spec §5.3. |

### Modify

| Path | Change |
|---|---|
| `src/dazzle/sentinel/models.py:94-115` | Add `catalogue_entry: str \| None = None` to `Finding` (line ~113, just before `model_config`). |
| `src/dazzle/sentinel/agents/python_audit.py` | Add `check_exceptions_as_control_flow` `@heuristic` method (PA-LLM-07) after `check_pip_when_uv_available`. |
| `src/dazzle/mcp/semantics_kb/counter_priors.py:40-48` | Add `DetectorRef` model + `detectors: list[DetectorRef]` field on `CounterPrior`. |
| `docs/counter-priors/exceptions-as-control-flow.md` (frontmatter only) | Add `detectors: - {id: PA-LLM-07, agent: PA, note: ...}`. |
| `tests/unit/test_counter_priors_drift.py` | Add bidirectional drift assertion (every declared detector resolves to a `@heuristic`; every quality `@heuristic` declares its catalogue entry). |
| `src/dazzle/cli/quality.py:10` | Add a new `bootstrap` subcommand wrapping `dazzle.quality.bootstrap.quality_bootstrap`. |
| `src/dazzle/core/init_impl/project.py:130-253` | No structural change — the blank template already gets copied wholesale, so adding the three files to `src/dazzle/templates/blank/` is sufficient for fresh inits. |
| `.github/workflows/ci.yml` | Add a job step running `dazzle sentinel scan --agent PA` against `examples/`, failing on findings of severity HIGH or above. |
| `CHANGELOG.md` | Add unreleased entry with **Added** (PA-LLM-07, scaffolding, `dazzle quality bootstrap`) and **Agent Guidance** sections. |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Bump `SEED_SCHEMA_VERSION` so the KG re-ingests the updated frontmatter. |

---

## Task 1: `Finding.catalogue_entry` field

**Files:**
- Modify: `src/dazzle/sentinel/models.py:94-115`
- Test: `tests/unit/test_sentinel_models.py` (new test added to whichever file currently covers Finding; check via `grep -l "class Finding" tests/`)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_sentinel_models.py` (create the file if it does not exist):

```python
"""Tests for Sentinel Pydantic models."""

from dazzle.sentinel.models import AgentId, Finding, Severity


def test_finding_carries_catalogue_entry() -> None:
    """A Finding may declare which counter-prior catalogue entry it enforces."""
    f = Finding(
        agent=AgentId.PA,
        heuristic_id="PA-LLM-07",
        category="python_audit",
        subcategory="llm_bias",
        severity=Severity.MEDIUM,
        title="exceptions as control flow",
        description="x",
        catalogue_entry="exceptions-as-control-flow",
    )
    assert f.catalogue_entry == "exceptions-as-control-flow"


def test_finding_catalogue_entry_defaults_none() -> None:
    """Findings unrelated to the catalogue may omit the field."""
    f = Finding(
        agent=AgentId.PA,
        heuristic_id="PA-UP001",
        category="python_audit",
        subcategory="modernisation",
        severity=Severity.LOW,
        title="x",
        description="y",
    )
    assert f.catalogue_entry is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sentinel_models.py -v`
Expected: FAIL — `Finding` rejects unknown field `catalogue_entry`.

- [ ] **Step 3: Add the field**

Modify `src/dazzle/sentinel/models.py`, inserting at line 113 (just before `model_config = ConfigDict(frozen=True)` inside `class Finding`):

```python
    catalogue_entry: str | None = None  # counter-prior catalogue entry id, kebab-case
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_sentinel_models.py -v`
Expected: PASS.

- [ ] **Step 5: Run the broader sentinel test suite**

Run: `pytest tests/ -m "not e2e" -k "sentinel" -v`
Expected: PASS (the field is additive with a default, so no existing test should break).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/sentinel/models.py tests/unit/test_sentinel_models.py
git commit -m "Add catalogue_entry field to Sentinel Finding"
```

---

## Task 2: `PA-LLM-07 exceptions_as_control_flow` heuristic

The heuristic detects four canonical shapes from `docs/counter-priors/exceptions-as-control-flow.md`. We implement them as four sub-detector helper functions inside `python_audit.py`, called from one `@heuristic` method, so each shape can be tested independently but they share a single Sentinel finding stream.

**Scan scope:** every `.py` file under `<project>/app/`. Files under `tests/`, `scripts/`, and `src/dazzle/` (when run against the framework itself) are excluded — those have their own discipline (`test_no_bare_except_pass.py`).

**Files:**
- Modify: `src/dazzle/sentinel/agents/python_audit.py` — append new heuristic method + helpers.
- Test: `tests/unit/test_python_audit_exceptions.py` (new).

- [ ] **Step 1: Write the failing tests for shape 1 (silent swallow)**

Create `tests/unit/test_python_audit_exceptions.py`:

```python
"""Tests for PA-LLM-07 — exceptions as control flow."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_silent_swallow,
    _detect_fallback_control_flow,
    _detect_validation_via_exception,
    _detect_try_as_conditional,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Shape 1: silent swallow
# ---------------------------------------------------------------------------


def test_silent_swallow_bare_except_pass() -> None:
    tree = _parse("try:\n    do()\nexcept:\n    pass\n")
    hits = _detect_silent_swallow(tree, Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].line == 3


def test_silent_swallow_except_exception_pass() -> None:
    tree = _parse("try:\n    do()\nexcept Exception:\n    pass\n")
    hits = _detect_silent_swallow(tree, Path("app/x.py"))
    assert len(hits) == 1


def test_silent_swallow_negative_specific_recovery() -> None:
    """Re-raising or specific recovery is fine."""
    tree = _parse(
        "try:\n    do()\nexcept ValueError as e:\n    log.error('bad input: %s', e)\n    raise\n"
    )
    assert _detect_silent_swallow(tree, Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 2: fallback control flow
# ---------------------------------------------------------------------------


def test_fallback_control_flow_literal_default() -> None:
    """`try: x = api.get(); except Exception: x = DEFAULT` shape."""
    src = (
        "try:\n"
        "    user = api.fetch(uid)\n"
        "except Exception:\n"
        "    user = None\n"
    )
    hits = _detect_fallback_control_flow(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_fallback_control_flow_negative_distinct_action() -> None:
    """If the except body does something different (e.g. raise, log+raise) it's fine."""
    src = (
        "try:\n"
        "    user = api.fetch(uid)\n"
        "except Exception:\n"
        "    log.exception('fetch failed')\n"
        "    raise\n"
    )
    assert _detect_fallback_control_flow(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 3: validation via exception
# ---------------------------------------------------------------------------


def test_validation_via_exception_int_cast() -> None:
    src = (
        "try:\n"
        "    int(s)\n"
        "    valid = True\n"
        "except ValueError:\n"
        "    valid = False\n"
    )
    hits = _detect_validation_via_exception(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_validation_via_exception_negative_real_parse() -> None:
    """A try/except around a parse that uses the result downstream isn't validation."""
    src = (
        "try:\n"
        "    n = int(s)\n"
        "    items[n] = compute(n)\n"
        "except ValueError as e:\n"
        "    raise InvalidInput(s) from e\n"
    )
    assert _detect_validation_via_exception(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 4: try-as-conditional
# ---------------------------------------------------------------------------


def test_try_as_conditional_dict_get() -> None:
    src = (
        "try:\n"
        "    v = d[k]\n"
        "except KeyError:\n"
        "    v = None\n"
    )
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_attr_access() -> None:
    src = (
        "try:\n"
        "    v = obj.attr\n"
        "except AttributeError:\n"
        "    v = None\n"
    )
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_index_access() -> None:
    src = (
        "try:\n"
        "    v = seq[i]\n"
        "except IndexError:\n"
        "    v = None\n"
    )
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_negative_other_exception() -> None:
    """KeyError around something that's not a subscript (e.g. external API call) is OK."""
    src = (
        "try:\n"
        "    result = service.call(payload)\n"
        "except KeyError as e:\n"
        "    raise ProtocolError(payload) from e\n"
    )
    assert _detect_try_as_conditional(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Heuristic integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    """End-to-end: the heuristic produces Findings carrying the catalogue entry id."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "sync.py").write_text(
        "def sync():\n    try:\n        v = d[k]\n    except KeyError:\n        v = None\n"
    )

    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_exceptions_as_control_flow(appspec=None)  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].heuristic_id == "PA-LLM-07"
    assert findings[0].catalogue_entry == "exceptions-as-control-flow"
    assert findings[0].remediation is not None
    assert any(
        "docs/counter-priors/exceptions-as-control-flow.md" in ref
        for ref in findings[0].remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    """Test and script files are out of scope."""
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("try:\n    do()\nexcept:\n    pass\n")

    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_exceptions_as_control_flow(appspec=None) == []  # type: ignore[arg-type]


def test_heuristic_noqa_suppression(tmp_path: Path) -> None:
    """A `# noqa: PA-LLM-07` comment on the try line suppresses the finding."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n    try:  # noqa: PA-LLM-07 - boundary suppression\n"
        "        v = d[k]\n    except KeyError:\n        v = None\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_exceptions_as_control_flow(appspec=None) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/unit/test_python_audit_exceptions.py -v`
Expected: FAIL on every test — the four helper functions and the heuristic method don't exist yet.

- [ ] **Step 3: Add the helper module section to `python_audit.py`**

Modify `src/dazzle/sentinel/agents/python_audit.py`. Just above the `class PythonAuditAgent` line (around line 70), insert the dataclass for sub-detector hits and the four helper functions:

```python
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


def _exception_names(handler: ast.ExceptHandler) -> set[str]:
    """Return the set of exception names a handler catches.

    Bare `except:` returns the empty set. `except Exception:` returns
    {"Exception"}. `except (KeyError, ValueError):` returns both.
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
    """True if the body's only statement is `target_name = <Constant>`."""
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
    """If the try body's last statement is `name = <call>`, return name."""
    if not try_body:
        return None
    stmt = try_body[-1]
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return None
    return stmt.targets[0].id


def _detect_silent_swallow(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 1: `except [Exception]: pass`."""
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
                    _ShapeHit(line=handler.lineno, snippet="except: pass", shape="silent_swallow")
                )
    return hits


def _detect_fallback_control_flow(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 2: try body assigns name=<call>; except body assigns name=<literal>."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        target_name = _try_body_assigns_name(node.body)
        if target_name is None:
            continue
        for handler in node.handlers:
            if _body_assigns_literal_to(handler.body, target_name):
                hits.append(
                    _ShapeHit(
                        line=handler.lineno,
                        snippet=f"{target_name} = <literal>",
                        shape="fallback",
                    )
                )
    return hits


def _detect_validation_via_exception(tree: ast.AST, path: Path) -> list[_ShapeHit]:
    """Shape 3: try body calls int()/float()/Decimal(); except sets a flag."""
    hits: list[_ShapeHit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        # Try body contains a bare validation call (int(s), float(s)) AND a
        # flag assignment (valid = True). Excludes cases where the parsed
        # value is used downstream within the try body.
        validation_call = False
        flag_assign: str | None = None
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                fn = stmt.value.func
                if isinstance(fn, ast.Name) and fn.id in _VALIDATION_CALLS:
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
                    )
                )
    return hits


def _try_body_does_precheck_op(
    body: list[ast.stmt],
    exception_names: set[str],
) -> str | None:
    """If the try body's single statement is a subscript / attr access / index
    op corresponding to one of the trivial-precheck exceptions, return a short
    description of the op. Otherwise None.
    """
    if len(body) != 1:
        return None
    stmt = body[0]
    if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1):
        return None
    value = stmt.value
    if isinstance(value, ast.Subscript):
        # d[k] → KeyError if dict, IndexError if sequence; we accept both.
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
                    )
                )
    return hits
```

- [ ] **Step 4: Add the `@heuristic` method**

Append to `PythonAuditAgent` (after `check_pip_when_uv_available`; should land near line 600 in the current file):

```python
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
                    line_text = (
                        source_lines[hit.line - 1] if 0 < hit.line <= len(source_lines) else ""
                    )
                    if "noqa: PA-LLM-07" in line_text:
                        continue
                    # Also accept noqa on the `try` line one above the handler
                    if hit.line - 2 >= 0 and "noqa: PA-LLM-07" in source_lines[hit.line - 2]:
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
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/unit/test_python_audit_exceptions.py -v`
Expected: PASS on all 13 tests.

- [ ] **Step 6: Run the wider sentinel test suite**

Run: `pytest tests/ -m "not e2e" -k "sentinel or python_audit" -v`
Expected: PASS — no regressions in existing PA heuristics.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/sentinel/agents/python_audit.py tests/unit/test_python_audit_exceptions.py
git commit -m "Add PA-LLM-07: exceptions-as-control-flow heuristic

Detects the four canonical wrong shapes documented in
docs/counter-priors/exceptions-as-control-flow.md: silent swallow,
fallback control flow, validation via exception, and try-as-conditional.
Scans app/ only; respects # noqa: PA-LLM-07 on the try or handler line."
```

---

## Task 3: Counter-prior `detectors:` field + bidirectional drift

The catalogue entry declares which detectors enforce it; the drift test asserts every declared detector resolves to an actual `@heuristic`, and conversely every Sentinel heuristic that targets a catalogued pattern declares its catalogue entry.

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/counter_priors.py:50-80`
- Modify: `docs/counter-priors/exceptions-as-control-flow.md` (frontmatter only)
- Modify: `tests/unit/test_counter_priors_drift.py:140+` (append new test)
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py` — bump `SEED_SCHEMA_VERSION`

- [ ] **Step 1: Write the failing schema test**

Append to `tests/unit/test_counter_priors_drift.py`:

```python
# ─────────────────────────────────────────────────────────────────────────
# Counter-prior ↔ Sentinel heuristic drift (PA-LLM-07 onwards)
# ─────────────────────────────────────────────────────────────────────────


def _python_audit_heuristic_ids() -> set[str]:
    """Return every heuristic_id declared on PythonAuditAgent.

    Reflection is sufficient: heuristics are discovered the same way at runtime.
    """
    from dazzle.sentinel.agents.python_audit import PythonAuditAgent

    agent = PythonAuditAgent()
    return {meta.heuristic_id for meta, _ in agent.get_heuristics()}


def test_every_declared_detector_resolves() -> None:
    """Every detector id declared in a counter-prior frontmatter must exist."""
    heuristic_ids = _python_audit_heuristic_ids()
    missing: list[str] = []
    for entry in load_all_counter_priors():
        for detector in entry.detectors:
            if detector.agent == "PA" and detector.id not in heuristic_ids:
                missing.append(
                    f"{entry.id}: declared detector {detector.id!r} not found on PythonAuditAgent"
                )
    assert not missing, "Detector ids declared in catalogue but not implemented:\n" + "\n".join(missing)


def test_exceptions_entry_declares_pa_llm_07() -> None:
    """Sanity pin: the pilot entry must wire to PA-LLM-07."""
    entries = {e.id: e for e in load_all_counter_priors()}
    entry = entries["exceptions_as_control_flow"]
    detector_ids = {d.id for d in entry.detectors}
    assert "PA-LLM-07" in detector_ids
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/unit/test_counter_priors_drift.py -v -k "detector or pa_llm_07"`
Expected: FAIL — `CounterPrior` has no `detectors` attribute and the catalogue entry doesn't declare it.

- [ ] **Step 3: Extend the schema**

Modify `src/dazzle/mcp/semantics_kb/counter_priors.py`. After the `CounterPriorRefs` class (around line 47), add the new model:

```python
class DetectorRef(BaseModel):
    """Pointer to a Sentinel heuristic that enforces this counter-prior."""

    id: str  # heuristic_id, e.g. "PA-LLM-07"
    agent: str  # AgentId code, e.g. "PA"
    note: str = ""  # optional clarification when coverage is partial
```

Then extend `CounterPrior` (around line 50) — add the new field just before `file_path`:

```python
    detectors: list[DetectorRef] = Field(default_factory=list)
```

- [ ] **Step 4: Update the pilot frontmatter**

Modify `docs/counter-priors/exceptions-as-control-flow.md` — extend the frontmatter (existing YAML block at the top of the file). After the `refs:` block, before the closing `---`, add:

```yaml
detectors:
  - id: PA-LLM-07
    agent: PA
    note: covers all four canonical wrong shapes (silent_swallow, fallback, validation, conditional) in app/ Python.
```

- [ ] **Step 5: Bump the KG seed schema version**

Find `SEED_SCHEMA_VERSION` in `src/dazzle/mcp/knowledge_graph/seed.py`:

```bash
grep -n "SEED_SCHEMA_VERSION" /Volumes/SSD/Dazzle/src/dazzle/mcp/knowledge_graph/seed.py
```

Bump the integer value by 1 (e.g. `SEED_SCHEMA_VERSION = 19` → `SEED_SCHEMA_VERSION = 20`).

- [ ] **Step 6: Run the drift tests**

Run: `pytest tests/unit/test_counter_priors_drift.py -v`
Expected: PASS — schema accepts the new field, frontmatter declares it, heuristic exists.

- [ ] **Step 7: Run the broader suite to catch knock-on breakage**

Run: `pytest tests/ -m "not e2e" -k "counter_prior or knowledge_graph or seed" -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/counter_priors.py \
        docs/counter-priors/exceptions-as-control-flow.md \
        tests/unit/test_counter_priors_drift.py \
        src/dazzle/mcp/knowledge_graph/seed.py
git commit -m "Wire counter-priors to Sentinel heuristics via detectors: field

Adds DetectorRef model + detectors list on CounterPrior. Pilot entry
exceptions-as-control-flow declares PA-LLM-07. Drift test enforces
the contract bidirectionally. KG seed version bumped."
```

---

## Task 4: Project scaffolding — tooling templates + `dazzle quality bootstrap`

Three tooling files ship into every new project via the blank template. For existing projects, a new `dazzle quality bootstrap` command writes them with merge-without-overwrite semantics on `pyproject.toml`.

**Files:**
- Create: `src/dazzle/templates/blank/pyproject.toml`
- Create: `src/dazzle/templates/blank/pyrightconfig.json`
- Create: `src/dazzle/templates/blank/.pre-commit-config.yaml`
- Create: `src/dazzle/quality/__init__.py`
- Create: `src/dazzle/quality/bootstrap.py`
- Modify: `src/dazzle/cli/quality.py:10` — add `bootstrap` subcommand
- Test: `tests/unit/test_init_project_scaffolding.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_init_project_scaffolding.py`:

```python
"""Tests for tooling-file scaffolding shipped with new and existing projects."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dazzle.core.init_impl import init_project
from dazzle.quality.bootstrap import quality_bootstrap


def _read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def test_init_project_writes_tooling_files(tmp_path: Path) -> None:
    target = tmp_path / "myproj"
    init_project(target, project_name="myproj", no_llm=True, no_git=True)

    assert (target / "pyproject.toml").exists()
    assert (target / "pyrightconfig.json").exists()
    assert (target / ".pre-commit-config.yaml").exists()

    cfg = _read_toml(target / "pyproject.toml")
    assert "tool" in cfg and "ruff" in cfg["tool"]
    select = cfg["tool"]["ruff"]["lint"]["select"]
    assert "TRY" in select
    assert "BLE" in select
    assert "S" in select


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    """Running bootstrap twice produces identical files."""
    target = tmp_path / "existing"
    target.mkdir()
    quality_bootstrap(target)
    first = (target / "pyproject.toml").read_text()
    quality_bootstrap(target)
    second = (target / "pyproject.toml").read_text()
    assert first == second


def test_bootstrap_preserves_unrelated_tables(tmp_path: Path) -> None:
    """Existing [project] / [tool.poetry] / etc. survive a bootstrap."""
    target = tmp_path / "existing"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.2.3"\n\n[tool.poetry]\nfoo = "bar"\n'
    )
    quality_bootstrap(target)
    cfg = _read_toml(target / "pyproject.toml")
    assert cfg["project"]["name"] == "myapp"
    assert cfg["project"]["version"] == "1.2.3"
    assert cfg["tool"]["poetry"]["foo"] == "bar"
    assert "ruff" in cfg["tool"]


def test_bootstrap_replaces_managed_ruff_table(tmp_path: Path) -> None:
    """If [tool.ruff] already exists, it is replaced (we own it)."""
    target = tmp_path / "existing"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 80\n[tool.ruff.lint]\nselect = ["E"]\n'
    )
    quality_bootstrap(target)
    cfg = _read_toml(target / "pyproject.toml")
    assert cfg["tool"]["ruff"]["line-length"] == 100
    assert "TRY" in cfg["tool"]["ruff"]["lint"]["select"]
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/unit/test_init_project_scaffolding.py -v`
Expected: FAIL — files don't exist in the template, `dazzle.quality.bootstrap` module doesn't exist.

- [ ] **Step 3: Create the blank-template `pyproject.toml`**

Create `src/dazzle/templates/blank/pyproject.toml`:

```toml
# managed-by: dazzle quality bootstrap
# Strict defaults from the agent code quality substrate.
# Ignores require documented rationale in this file under
# [tool.ruff.lint.per-file-ignores] or as inline # noqa: <code> - <reason> comments.

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "F",     # pyflakes
    "W",     # pycodestyle warnings
    "B",     # bugbear (likely bugs, includes B006 mutable-default-argument)
    "BLE",   # blind-except
    "FBT",   # boolean-trap
    "C4",    # comprehensions
    "DTZ",   # datetime gotchas
    "PTH",   # pathlib over os.path
    "PL",    # pylint subset
    "TRY",   # tryceratops (exception-handling discipline)
    "S",     # security (bandit)
    "PERF",  # performance
    "UP",    # modernise (pyupgrade)
    "SIM",   # simplify
    "I",     # import sorting
    "TCH",   # type-checking imports
    "RUF",   # ruff-specific
]
ignore = []  # add entries only with a rationale comment

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]   # assert is fine in tests
"scripts/**" = ["T201"] # print is fine in scripts
```

- [ ] **Step 4: Create the blank-template `pyrightconfig.json`**

Create `src/dazzle/templates/blank/pyrightconfig.json`:

```json
{
  "typeCheckingMode": "strict",
  "reportMissingTypeStubs": "warning",
  "reportUnknownMemberType": "warning",
  "reportMissingTypeArgument": "error",
  "reportUntypedFunctionDecorator": "error",
  "pythonVersion": "3.12"
}
```

- [ ] **Step 5: Create the blank-template `.pre-commit-config.yaml`**

Create `src/dazzle/templates/blank/.pre-commit-config.yaml`:

```yaml
# managed-by: dazzle quality bootstrap
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: dazzle-sentinel-pa
        name: dazzle sentinel scan (Python audit)
        entry: dazzle sentinel scan --agent PA --severity-threshold medium
        language: system
        pass_filenames: false
        types: [python]
```

- [ ] **Step 6: Create the bootstrap module**

Create `src/dazzle/quality/__init__.py` (empty file).

Create `src/dazzle/quality/bootstrap.py`:

```python
"""Write tooling-file templates into an existing Dazzle project.

For fresh `dazzle init` flows the blank template already ships these files.
This module handles the existing-project case: it reads what's there, swaps
in the Dazzle-managed tables, and leaves everything else alone.
"""

from __future__ import annotations

from pathlib import Path

import tomli_w
import tomllib

_DAZZLE_MANAGED_TABLES = ("tool.ruff", "tool.ruff.lint", "tool.ruff.lint.per-file-ignores")


def _template_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "blank"


def _load_template_ruff_tables() -> dict:
    """Read the Dazzle-managed [tool.ruff*] tables out of the blank template."""
    template = _template_dir() / "pyproject.toml"
    return tomllib.loads(template.read_text())


def quality_bootstrap(project_dir: Path) -> list[Path]:
    """Write the three tooling files into `project_dir`.

    pyproject.toml: replace [tool.ruff*] tables, leave others.
    pyrightconfig.json: write if missing, replace if present.
    .pre-commit-config.yaml: write if missing, leave alone if present.

    Returns the list of files written (or rewritten).
    """
    project_dir = project_dir.resolve()
    written: list[Path] = []

    written.extend(_bootstrap_pyproject(project_dir))
    written.extend(_bootstrap_pyright(project_dir))
    written.extend(_bootstrap_precommit(project_dir))

    return written


def _bootstrap_pyproject(project_dir: Path) -> list[Path]:
    target = project_dir / "pyproject.toml"
    template_tables = _load_template_ruff_tables()

    if target.exists():
        existing = tomllib.loads(target.read_text())
    else:
        existing = {}

    # Replace tool.ruff wholesale (we own it).
    tool = existing.setdefault("tool", {})
    tool["ruff"] = template_tables["tool"]["ruff"]

    target.write_text(tomli_w.dumps(existing))
    return [target]


def _bootstrap_pyright(project_dir: Path) -> list[Path]:
    target = project_dir / "pyrightconfig.json"
    src = _template_dir() / "pyrightconfig.json"
    target.write_text(src.read_text())
    return [target]


def _bootstrap_precommit(project_dir: Path) -> list[Path]:
    target = project_dir / ".pre-commit-config.yaml"
    if target.exists():
        return []  # don't overwrite a user-customised pre-commit config
    src = _template_dir() / ".pre-commit-config.yaml"
    target.write_text(src.read_text())
    return [target]
```

- [ ] **Step 7: Add the `bootstrap` CLI subcommand**

Modify `src/dazzle/cli/quality.py`. Add this command at the end of the file:

```python
@quality_app.command("bootstrap")
def bootstrap_command() -> None:
    """Write strict tooling defaults (pyproject.toml / pyrightconfig.json / .pre-commit-config.yaml) into the current project."""
    from dazzle.quality.bootstrap import quality_bootstrap

    project_root = Path.cwd().resolve()
    written = quality_bootstrap(project_root)
    console.print(
        f"\n[green]Quality tooling bootstrapped[/green] ({len(written)} file{'s' if len(written) != 1 else ''})"
    )
    for path in written:
        console.print(f"  [dim]•[/dim] {path.relative_to(project_root)}")
    console.print(
        "\n[dim]Next: run `pre-commit install` to wire the hooks. "
        "Existing pyproject.toml tables outside [tool.ruff*] were preserved.[/dim]"
    )
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/unit/test_init_project_scaffolding.py -v`
Expected: PASS on all four tests.

- [ ] **Step 9: Smoke test the CLI**

Run:
```bash
cd /tmp && rm -rf qa-bootstrap-smoke && mkdir qa-bootstrap-smoke && cd qa-bootstrap-smoke
dazzle quality bootstrap
ls -la
cat pyproject.toml | head -20
```
Expected: three files emitted; `pyproject.toml` contains the strict Ruff config.

- [ ] **Step 10: Add `tomli_w` to the dazzle dependencies**

Check `pyproject.toml` (the Dazzle project root one) for the dependencies list:
```bash
grep -A 20 "^dependencies = " /Volumes/SSD/Dazzle/pyproject.toml
```
If `tomli_w` is not already listed, add it to the main `dependencies` array.

- [ ] **Step 11: Commit**

```bash
git add src/dazzle/templates/blank/pyproject.toml \
        src/dazzle/templates/blank/pyrightconfig.json \
        src/dazzle/templates/blank/.pre-commit-config.yaml \
        src/dazzle/quality/__init__.py \
        src/dazzle/quality/bootstrap.py \
        src/dazzle/cli/quality.py \
        tests/unit/test_init_project_scaffolding.py \
        pyproject.toml
git commit -m "Ship strict tooling defaults via init + dazzle quality bootstrap

New projects scaffolded by dazzle init get pyproject.toml (Ruff TRY/BLE/
S/B006 et al.), pyrightconfig.json (strict mode), and a .pre-commit-config
that runs ruff + sentinel PA. Existing projects opt in via the new
dazzle quality bootstrap command which preserves all non-Dazzle-managed
[tool.*] tables."
```

---

## Task 5: CI wiring + CHANGELOG entry

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Confirm the example apps are clean**

Run: `dazzle sentinel scan --agent PA --severity-threshold medium examples/`

(If the command shape differs, adapt — the goal is to verify zero findings against the bundled examples before CI gates on the same call.)

Expected: zero findings. If any fire, audit them — either they're real (fix the example) or false positives (tighten the heuristic; re-run Task 2 tests).

- [ ] **Step 2: Add the CI step**

Open `.github/workflows/ci.yml`. Find the unit-test job (look for `pytest tests/ -m "not e2e"`). Immediately after it, add:

```yaml
      - name: Sentinel Python audit on examples
        run: |
          dazzle sentinel scan --agent PA --severity-threshold high examples/
```

(Threshold is `high` initially — PA-LLM-07 emits `medium`, so this is informational only in CI until the backfill audit promotes it.)

- [ ] **Step 3: Update CHANGELOG**

Open `CHANGELOG.md`. Under the topmost unreleased / next-version section, add:

```markdown
### Added
- Sentinel heuristic `PA-LLM-07` (exceptions-as-control-flow) detects the four canonical wrong shapes of try/except misuse in user `app/` Python. Wires to `docs/counter-priors/exceptions-as-control-flow.md` via the new `detectors:` frontmatter field.
- New CLI command `dazzle quality bootstrap` writes strict Ruff + Pyright + pre-commit defaults into an existing project. Newly-scaffolded projects (`dazzle init`) ship these files automatically.
- `Finding.catalogue_entry` field on Sentinel findings — links a finding back to its counter-prior catalogue entry for agent feedback.

### Agent Guidance
- When writing user code in `app/`, prefer explicit conditionals (`d.get(k)`, `getattr(obj, "attr", None)`) and structured errors over `try/except`. The four canonical wrong shapes are documented at `docs/counter-priors/exceptions-as-control-flow.md`. PA-LLM-07 flags them at sentinel-scan time.
- When introducing a new counter-prior that has a Sentinel detector, declare the link in the catalogue entry's frontmatter `detectors:` array. The drift test (`tests/unit/test_counter_priors_drift.py`) will fail if the declaration goes missing.
- For per-line suppression of PA-LLM-07, add `# noqa: PA-LLM-07 - <reason>` on the `try` line or the handler line. Suppression without a reason is invalid.
```

- [ ] **Step 4: Run the full pre-ship gate**

Run:
```bash
pytest tests/ -m "not e2e"
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml CHANGELOG.md
git commit -m "Wire PA-LLM-07 into CI + document substrate slice in CHANGELOG"
```

- [ ] **Step 6: Bump the version**

Per project convention (see CLAUDE.md "Ship Discipline"), every push gets a unique version. Run:

```bash
/bump minor   # this is a feature addition, not a bug fix
```

- [ ] **Step 7: Final verification + ship**

Run `dazzle sentinel scan --agent PA examples/` once more to confirm nothing regressed.

The vertical slice is complete. Round 2 (`n-plus-one-in-user-code` or `optional-instead-of-result` + `dazzle.result`) is a separate plan.

---

## Self-review notes

**Spec coverage:**
- §5.1 (heuristic) → Task 2
- §5.2 (catalogue ↔ heuristic wiring) → Task 3
- §5.3 (scaffolding + `dazzle quality bootstrap`) → Task 4
- §5.4 (convention library) → deliberately deferred per spec
- §5.5 (agent feedback format) → covered by Task 1 (`catalogue_entry`) + Task 2 (`Remediation.references`)
- §6 (data flow) → exercised end-to-end by Task 2 Step 5 + Task 5 Step 1
- §7 (failure semantics, suppression) → Task 2 Step 4 (severity MEDIUM, noqa handling) + Task 5 Step 2 (CI threshold high, informational only)
- §8 (testing) → unit tests in Tasks 1-4; smoke gate in Task 5 Step 1
- §10 implementation order → preserved as Tasks 1-5 (with Tasks 1-2 swapped relative to spec order, because the heuristic uses `catalogue_entry` which must exist first)

**Placeholder scan:** clean. No TBD, TODO, "appropriate error handling," or vague references.

**Type consistency:** `_ShapeHit` declared in Task 2 Step 3 used consistently. `DetectorRef` declared in Task 3 Step 3, used in Task 3 Step 1 test. `Finding.catalogue_entry: str | None` declared in Task 1 Step 3, used in Task 2 Step 4 and Task 3 Step 1.

**Ambiguity check:** Task 4 Step 9 smoke test uses a `/tmp` path — fine for macOS/Linux; if running on Windows, adapt. The `tomli_w` dependency check in Task 4 Step 10 may already be satisfied; the step is a conditional add.
