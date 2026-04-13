# Agent-Led Fitness Methodology v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v1 skeleton of the Agent-Led Fitness Methodology — a continuous V&V loop that triangulates `spec.md`, DSL stories, and the running app, emits structured findings, and produces autonomous (hard) or human-gated (soft) corrections. This plan delivers every component listed in §14 "v1 — Ship the skeleton" of the design spec.

**Architecture:** New subsystem at `src/dazzle/fitness/` with three passes — deterministic story walker (Pass 1), agentic spec cross-check (Pass 2a), agentic behavioural proxy with hard interlock (Pass 2b). All runs record into a per-run `FitnessLedger` (v1 snapshot-based). A regression comparator runs every cycle. Findings are self-contained (evidence-embedded) and routed through a two-gate corrector (maturity + mechanical disambiguation).

**Tech Stack:** Python 3.12+, Pydantic, existing `DazzleAgent` framework (`src/dazzle/agent/`), PostgreSQL snapshot comparison via asyncpg, Playwright for Pass 1/2b execution, LLM calls via existing `dazzle.llm` facade.

**Prerequisite:** ADR-0020 "Lifecycle Evidence Predicates" — see `docs/superpowers/plans/2026-04-13-lifecycle-evidence-predicates-plan.md`. That plan must ship and merge FIRST — Pass 1 walker and `progress_evaluator.py` depend on the new `lifecycle:` DSL block. This plan assumes `LifecycleSpec`, `LifecycleStateSpec`, `LifecycleTransitionSpec` are available in `src/dazzle/core/ir/lifecycle.py`.

**Source spec:** `docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md` (v2, approved 2026-04-13).

---

## File Structure

The fitness subsystem is a new tree under `src/dazzle/fitness/`. Each module is small and focused (single responsibility) to match the design principle: files that change together live together, but split by responsibility.

```
src/dazzle/fitness/
├── __init__.py              # Public API re-exports
├── config.py                # [dazzle.fitness] TOML reader
├── maturity.py              # [dazzle.maturity].level reader
├── models.py                # Shared dataclasses: Finding, FitnessDiff, LedgerStep, RowChange
├── ledger.py                # FitnessLedger abstract interface
├── ledger_snapshot.py       # v1 snapshot impl (ships now)
├── interlock.py             # EXPECT-before-ACTION enforcement
├── budget.py                # Token budget + degradation ladder
├── progress_evaluator.py    # Lifecycle motion-vs-work detection (needs ADR-0020)
├── spec_extractor.py        # Pass 2a-A: reads spec.md only
├── adversary.py             # Pass 2a-C: reads DSL stories only (structural independence)
├── independence.py          # Pass 2a-D: Jaccard between sensors
├── cross_check.py           # Pass 2a-B: coverage / over-impl findings
├── walker.py                # Pass 1: deterministic story walker
├── proxy.py                 # Pass 2b: agentic behavioural proxy
├── extractor.py             # Transcripts → Findings with evidence_embedded
├── backlog.py               # fitness-backlog.md reader/writer
├── comparator.py            # Regression detection across cycles
├── corrector.py             # Two-gate routing + alternative-generation
├── paraphrase.py            # v1 skeleton (UX wiring is v1.1)
├── engine.py                # Orchestrator
└── missions/
    ├── __init__.py
    ├── story_walk.py        # Mission for Pass 1
    └── free_roam.py         # Mission for Pass 2b

src/dazzle/cli/runtime_impl/ux_cycle_impl/
└── fitness_strategy.py      # Strategy.FITNESS wiring

tests/unit/fitness/
├── __init__.py
├── test_config.py
├── test_maturity.py
├── test_models.py
├── test_ledger_snapshot.py
├── test_interlock.py
├── test_budget.py
├── test_progress_evaluator.py
├── test_spec_extractor.py
├── test_adversary.py
├── test_independence.py
├── test_cross_check.py
├── test_walker.py
├── test_proxy.py
├── test_extractor.py
├── test_backlog.py
├── test_comparator.py
├── test_corrector.py
├── test_paraphrase.py
└── test_engine.py

tests/e2e/fitness/
└── test_support_tickets_fitness.py

docs/reference/fitness-methodology.md   # User-facing reference
```

**Why this decomposition:**

- Each file < 250 LOC target. The engine orchestrator is the only module touching every other module.
- `models.py` owns shared dataclasses so circular-import hazards are avoided.
- `ledger.py` defines the abstract interface; implementations live in sibling files (`ledger_snapshot.py`, later `ledger_savepoint.py`, `ledger_wal.py`). v1 ships only the snapshot implementation but the interface is stable.
- Passes are separated from their shared infrastructure (`interlock.py`, `budget.py`, `independence.py`) — each pass can be tested in isolation.
- `missions/` sub-tree mirrors the existing `src/dazzle/agent/missions/` convention and uses the `_shared.py` helpers already present there.

---

## Task 0: Discovery

Before writing code, the implementing agent MUST verify assumptions about the surrounding codebase. The fitness engine depends on several existing subsystems; if any has diverged from what this plan assumes, the implementer should pause and flag it.

**Files:**
- Read: `src/dazzle/agent/core.py` (DazzleAgent class, Mission interface)
- Read: `src/dazzle/agent/observer.py` (PlaywrightObserver, HttpObserver)
- Read: `src/dazzle/agent/executor.py` (PlaywrightExecutor, HttpExecutor)
- Read: `src/dazzle/agent/missions/_shared.py` (shared helpers)
- Read: `src/dazzle/core/ir/lifecycle.py` (LifecycleSpec from ADR-0020)
- Read: `src/dazzle/core/ir/entity.py` (EntitySpec — verify `fitness` attribute location)
- Read: `src/dazzle/core/ir/story.py` (StorySpec — verify field names)
- Read: `src/dazzle/core/ir/persona.py` (PersonaSpec — verify `.id`/`.name` attr)
- Read: `src/dazzle/core/ir/process.py` (ProcessSpec — confirm it's workflow-not-lifecycle)
- Read: `src/dazzle/core/runtime_services.py` (RuntimeServices — for DB pool access)
- Read: `src/dazzle/llm/__init__.py` (confirm LLM facade signature)
- Read: `examples/support_tickets/spec.md` (target app for E2E test)
- Read: `examples/support_tickets/*.dsl` (confirm stories + personas exist)

- [ ] **Step 1: Verify DazzleAgent Mission protocol**

Run: `grep -n "class Mission" src/dazzle/agent/core.py`
Expected: finds a `Mission` dataclass or protocol with fields like `name`, `tools`, `system_prompt`, `observation_fn`, `completion_fn`.

Record: actual field names, the observer/executor attachment mechanism, and how missions produce AgentTranscripts.

- [ ] **Step 2: Verify DB pool access path**

Run: `grep -rn "asyncpg.create_pool\|Pool" src/dazzle/core/runtime_services.py src/dazzle_back/ | head -30`
Expected: finds the canonical place to get an asyncpg pool for a running example app.

Record: is the pool accessible via `RuntimeServices.db_pool()` or another path? Is there a read-only pool for snapshot work?

- [ ] **Step 3: Verify LLM facade signature**

Run: `grep -n "def ask\|async def ask\|class Llm" src/dazzle/llm/__init__.py src/dazzle/llm/*.py 2>/dev/null | head -20`
Expected: finds a canonical `ask(prompt, model=..., system=...)` or similar.

Record: exact signature, whether it supports model family selection, whether it returns plain text or structured output.

- [ ] **Step 4: Verify existing fitness-like patterns**

Run: `grep -rn "fitness" src/dazzle/ docs/adr/ --include="*.py" --include="*.md" | head -30`
Expected: no collisions. The word "fitness" should not appear in existing code paths.

If it does: NOTE the collision. The fitness subsystem may need a different import path or name prefix.

- [ ] **Step 5: Confirm lifecycle ADR has landed**

Run: `ls src/dazzle/core/ir/lifecycle.py && grep -n "class LifecycleSpec" src/dazzle/core/ir/lifecycle.py`
Expected: file exists, `LifecycleSpec` class defined.

If NOT: this plan is blocked. Stop and ship the lifecycle ADR plan first.

- [ ] **Step 6: Confirm support_tickets example has a lifecycle declaration**

Run: `grep -rn "lifecycle:" examples/support_tickets/`
Expected: at least one `lifecycle:` block on a Ticket entity (shipped as part of the lifecycle ADR plan).

If NOT: the ADR plan's Task 5 (example adoption) has not been executed. The fitness E2E test will fail until it is.

- [ ] **Step 7: Write a discovery findings note**

Create: `dev_docs/fitness-discovery-findings.md`
Content: a bullet list of every assumption validated or invalidated in steps 1-6, plus any surprise. This file is scratch and is NOT committed — it exists for the implementer's own reference across subagent handoffs.

After this step, proceed to Task 1.

---

## Task 1: Configuration and maturity reader

The fitness engine reads two config sections from `pyproject.toml`: `[dazzle.fitness]` (budgets, thresholds, TTLs) and `[dazzle.maturity]` (mvp/beta/stable gate). These are simple dataclasses loaded via `tomllib`.

**Files:**
- Create: `src/dazzle/fitness/__init__.py`
- Create: `src/dazzle/fitness/config.py`
- Create: `src/dazzle/fitness/maturity.py`
- Create: `tests/unit/fitness/__init__.py`
- Create: `tests/unit/fitness/test_config.py`
- Create: `tests/unit/fitness/test_maturity.py`

- [ ] **Step 1: Write failing test for FitnessConfig**

```python
# tests/unit/fitness/test_config.py
from pathlib import Path

import pytest

from dazzle.fitness.config import FitnessConfig, load_fitness_config


def test_load_config_defaults_when_section_absent(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\n')

    cfg = load_fitness_config(tmp_path)

    assert cfg.max_tokens_per_cycle == 100_000
    assert cfg.max_wall_time_minutes == 10
    assert cfg.independence_threshold_jaccard == 0.85
    assert cfg.ledger_ttl_days == 30
    assert cfg.transcript_ttl_days == 30
    assert cfg.paraphrase_graduation_rounds == 3
    assert cfg.independence_mechanism == "prompt_plus_model_family"


def test_load_config_honours_overrides(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\n\n'
        "[dazzle.fitness]\n"
        "max_tokens_per_cycle = 50000\n"
        "independence_threshold_jaccard = 0.75\n"
        '\n[dazzle.fitness.independence_mechanism]\nprimary = "prompt_only"\n'
    )

    cfg = load_fitness_config(tmp_path)

    assert cfg.max_tokens_per_cycle == 50_000
    assert cfg.independence_threshold_jaccard == 0.75
    assert cfg.independence_mechanism == "prompt_only"


def test_load_config_rejects_invalid_threshold(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[dazzle.fitness]\nindependence_threshold_jaccard = 1.5\n"
    )

    with pytest.raises(ValueError, match="threshold"):
        load_fitness_config(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.fitness'`.

- [ ] **Step 3: Implement FitnessConfig**

```python
# src/dazzle/fitness/__init__.py
"""Agent-Led Fitness Methodology — subsystem root.

See docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md
"""
```

```python
# src/dazzle/fitness/config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import tomllib


IndependenceMechanism = Literal[
    "prompt_only", "prompt_plus_model_family", "prompt_plus_model_and_seed"
]


@dataclass(frozen=True)
class FitnessConfig:
    max_tokens_per_cycle: int = 100_000
    max_wall_time_minutes: int = 10
    independence_threshold_jaccard: float = 0.85
    ledger_ttl_days: int = 30
    transcript_ttl_days: int = 30
    paraphrase_graduation_rounds: int = 3
    independence_mechanism: IndependenceMechanism = "prompt_plus_model_family"


def load_fitness_config(project_root: Path) -> FitnessConfig:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return FitnessConfig()

    data = tomllib.loads(pyproject.read_text())
    section = data.get("dazzle", {}).get("fitness", {})
    mech = section.get("independence_mechanism", {})
    mechanism = mech.get("primary", "prompt_plus_model_family")

    threshold = float(section.get("independence_threshold_jaccard", 0.85))
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"[dazzle.fitness].independence_threshold_jaccard must be in "
            f"[0.0, 1.0], got {threshold}"
        )

    return FitnessConfig(
        max_tokens_per_cycle=int(section.get("max_tokens_per_cycle", 100_000)),
        max_wall_time_minutes=int(section.get("max_wall_time_minutes", 10)),
        independence_threshold_jaccard=threshold,
        ledger_ttl_days=int(section.get("ledger_ttl_days", 30)),
        transcript_ttl_days=int(section.get("transcript_ttl_days", 30)),
        paraphrase_graduation_rounds=int(
            section.get("paraphrase_graduation_rounds", 3)
        ),
        independence_mechanism=mechanism,  # type: ignore[arg-type]
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_config.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Write failing test for maturity reader**

```python
# tests/unit/fitness/test_maturity.py
from pathlib import Path

import pytest

from dazzle.fitness.maturity import MaturityLevel, read_maturity


def test_maturity_defaults_to_mvp(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert read_maturity(tmp_path) == "mvp"


def test_maturity_reads_beta(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[dazzle.maturity]\nlevel = 'beta'\n"
    )
    assert read_maturity(tmp_path) == "beta"


def test_maturity_reads_stable(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[dazzle.maturity]\nlevel = 'stable'\n"
    )
    assert read_maturity(tmp_path) == "stable"


def test_maturity_rejects_unknown_level(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[dazzle.maturity]\nlevel = 'production'\n"
    )
    with pytest.raises(ValueError, match="maturity level"):
        read_maturity(tmp_path)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_maturity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.fitness.maturity'`.

- [ ] **Step 7: Implement maturity reader**

```python
# src/dazzle/fitness/maturity.py
from pathlib import Path
from typing import Literal
import tomllib


MaturityLevel = Literal["mvp", "beta", "stable"]
_VALID: set[str] = {"mvp", "beta", "stable"}


def read_maturity(project_root: Path) -> MaturityLevel:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return "mvp"

    data = tomllib.loads(pyproject.read_text())
    level = data.get("dazzle", {}).get("maturity", {}).get("level", "mvp")

    if level not in _VALID:
        raise ValueError(
            f"Invalid maturity level {level!r}; expected one of {_VALID}"
        )
    return level  # type: ignore[return-value]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_maturity.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/fitness/__init__.py src/dazzle/fitness/config.py src/dazzle/fitness/maturity.py tests/unit/fitness/__init__.py tests/unit/fitness/test_config.py tests/unit/fitness/test_maturity.py
git commit -m "feat(fitness): config + maturity reader (v1 task 1)"
```

---

## Task 2: `fitness.repr_fields` DSL field + lint warning

Every entity participating in fitness evaluation MUST declare `fitness.repr_fields`. v1 ships this as a non-fatal lint warning (v1.1 makes it fatal).

**Files:**
- Modify: `src/dazzle/core/ir/entity.py` — add optional `fitness: FitnessSpec | None` field
- Create: `src/dazzle/core/ir/fitness_repr.py` — `FitnessSpec` dataclass
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py` — parse `fitness:` block
- Modify: `src/dazzle/core/validation/rules.py` — add `repr_fields_missing` lint rule
- Test: `tests/unit/test_fitness_repr_parser.py`
- Test: `tests/unit/test_fitness_repr_lint.py`

- [ ] **Step 1: Write failing test for FitnessSpec IR parsing**

```python
# tests/unit/test_fitness_repr_parser.py
from dazzle.core.dsl_parser import parse_dsl


def test_entity_with_fitness_repr_fields_parses() -> None:
    source = '''
module demo

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[new, closed] required
  assignee_id: ref User

  fitness:
    repr_fields: [title, status, assignee_id]

entity User "User":
  id: uuid pk
  email: str(200) required
'''
    app = parse_dsl(source)
    ticket = next(e for e in app.entities if e.name == "Ticket")
    assert ticket.fitness is not None
    assert ticket.fitness.repr_fields == ["title", "status", "assignee_id"]


def test_entity_without_fitness_block_parses() -> None:
    source = '''
module demo

entity Note "Note":
  id: uuid pk
  body: text
'''
    app = parse_dsl(source)
    note = next(e for e in app.entities if e.name == "Note")
    assert note.fitness is None


def test_fitness_repr_fields_must_reference_declared_fields() -> None:
    import pytest
    source = '''
module demo

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required

  fitness:
    repr_fields: [title, nonexistent]
'''
    with pytest.raises(Exception, match="nonexistent"):
        parse_dsl(source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fitness_repr_parser.py -v`
Expected: FAIL — `fitness:` block is not yet understood by the parser.

- [ ] **Step 3: Implement FitnessSpec IR**

```python
# src/dazzle/core/ir/fitness_repr.py
from pydantic import BaseModel, Field


class FitnessSpec(BaseModel):
    """Per-entity fitness configuration.

    Controls how this entity is represented in fitness evaluation. The
    `repr_fields` list is the compact projection used by `FitnessDiff.RowChange`
    when recording row changes — it should capture domain-essential fields
    (status, FK links, lifecycle timestamps), not UI-optimised columns.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    repr_fields: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Wire FitnessSpec into EntitySpec**

Modify `src/dazzle/core/ir/entity.py`: add optional field.

```python
# inside class EntitySpec(BaseModel):
from dazzle.core.ir.fitness_repr import FitnessSpec  # noqa: E402

    fitness: FitnessSpec | None = None
```

- [ ] **Step 5: Parse the `fitness:` block**

Modify `src/dazzle/core/dsl_parser_impl/entity.py` — in whichever function iterates entity sub-blocks, add a branch for `fitness:`. Look at how the `fields:` or existing sub-blocks are parsed for the pattern. Add a helper `parse_fitness_block(lines, declared_field_names) -> FitnessSpec` that reads `repr_fields: [...]` and validates every name is in `declared_field_names`.

```python
# Inside the entity sub-block dispatcher
elif stripped.startswith("fitness:"):
    sub_lines, next_idx = collect_indented_block(lines, idx + 1, base_indent + 2)
    fitness_spec = _parse_fitness_block(sub_lines, declared_field_names)
    entity_kwargs["fitness"] = fitness_spec
    idx = next_idx
    continue
```

```python
def _parse_fitness_block(
    lines: list[str], declared_field_names: set[str]
) -> FitnessSpec:
    repr_fields: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("repr_fields:"):
            # "repr_fields: [a, b, c]"
            bracket = stripped.split(":", 1)[1].strip()
            if not (bracket.startswith("[") and bracket.endswith("]")):
                raise DslParseError(
                    f"fitness.repr_fields must be a bracketed list, got {bracket!r}"
                )
            inner = bracket[1:-1]
            repr_fields = [f.strip() for f in inner.split(",") if f.strip()]
            for f in repr_fields:
                if f not in declared_field_names:
                    raise DslParseError(
                        f"fitness.repr_fields references undeclared field {f!r}"
                    )
    return FitnessSpec(repr_fields=repr_fields)
```

- [ ] **Step 6: Run parser test to verify it passes**

Run: `pytest tests/unit/test_fitness_repr_parser.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 7: Write failing test for lint warning**

```python
# tests/unit/test_fitness_repr_lint.py
from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.validation import run_all_checks


def test_entity_without_repr_fields_emits_lint_warning() -> None:
    source = '''
module demo

entity Note "Note":
  id: uuid pk
  body: text
'''
    app = parse_dsl(source)
    findings = run_all_checks(app)
    repr_warnings = [
        f for f in findings
        if f.rule == "fitness.repr_fields_missing" and f.severity == "warning"
    ]
    assert len(repr_warnings) == 1
    assert "Note" in repr_warnings[0].message


def test_entity_with_repr_fields_does_not_emit_warning() -> None:
    source = '''
module demo

entity Note "Note":
  id: uuid pk
  body: text

  fitness:
    repr_fields: [body]
'''
    app = parse_dsl(source)
    findings = run_all_checks(app)
    repr_warnings = [
        f for f in findings if f.rule == "fitness.repr_fields_missing"
    ]
    assert repr_warnings == []
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/unit/test_fitness_repr_lint.py -v`
Expected: FAIL — rule does not exist yet.

- [ ] **Step 9: Implement the lint rule**

Locate the validation rules module (likely `src/dazzle/core/validation/rules.py` or similar from Task 0 discovery). Add a new rule function:

```python
def check_fitness_repr_fields_declared(app: AppSpec) -> list[Finding]:
    findings: list[Finding] = []
    for entity in app.entities:
        if entity.fitness is None or not entity.fitness.repr_fields:
            findings.append(
                Finding(
                    rule="fitness.repr_fields_missing",
                    severity="warning",  # v1 — non-fatal
                    message=(
                        f"Entity {entity.name!r} has no fitness.repr_fields. "
                        f"Fitness evaluation will skip this entity. Add a "
                        f"`fitness:\\n  repr_fields: [...]` block with "
                        f"domain-essential fields."
                    ),
                    location=entity.source_location,
                )
            )
    return findings
```

Register the function in whatever registry the validation module uses.

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/unit/test_fitness_repr_lint.py -v`
Expected: both tests PASS.

- [ ] **Step 11: Commit**

```bash
git add src/dazzle/core/ir/fitness_repr.py src/dazzle/core/ir/entity.py src/dazzle/core/dsl_parser_impl/entity.py src/dazzle/core/validation/rules.py tests/unit/test_fitness_repr_parser.py tests/unit/test_fitness_repr_lint.py
git commit -m "feat(dsl): fitness.repr_fields block + lint warning (v1 task 2)"
```

---

## Task 3: Shared models — Finding, LedgerStep, FitnessDiff, RowChange

All downstream modules depend on these shared dataclasses. Defining them up front avoids circular imports.

**Files:**
- Create: `src/dazzle/fitness/models.py`
- Test: `tests/unit/fitness/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_models.py
from datetime import datetime, timezone

import pytest

from dazzle.fitness.models import (
    EvidenceEmbedded,
    Finding,
    FitnessDiff,
    LedgerStep,
    ProgressRecord,
    RowChange,
)


def test_ledger_step_requires_expect() -> None:
    with pytest.raises(ValueError, match="expect"):
        LedgerStep(
            step_no=1,
            txn_id=None,
            expected="",  # empty string
            action_summary="click button",
            observed_ui="ok",
            observed_changes=[],
            delta={},
        )


def test_ledger_step_happy_path() -> None:
    step = LedgerStep(
        step_no=1,
        txn_id=None,
        expected="a new ticket exists",
        action_summary="click create",
        observed_ui="Ticket saved",
        observed_changes=[],
        delta={},
    )
    assert step.step_no == 1
    assert step.expected == "a new ticket exists"


def test_row_change_with_semantic_repr() -> None:
    rc = RowChange(
        table="ticket",
        row_id="ab12",
        kind="insert",
        semantic_repr="Ticket(title=Bug, status=new, assignee=alice)",
        field_deltas={"status": (None, "new")},
    )
    assert rc.kind == "insert"


def test_finding_serialisation_roundtrip() -> None:
    f = Finding(
        id="FIND-001",
        created=datetime(2026, 4, 13, tzinfo=timezone.utc),
        run_id="run-abc",
        cycle=None,
        axis="conformance",
        locus="implementation",
        severity="high",
        persona="support_agent",
        capability_ref="story:resolve_ticket",
        expected="ticket.status becomes resolved",
        observed="ticket.status unchanged",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"expect": "x", "action": "y", "observed": "z"},
            diff_summary=[],
            transcript_excerpt=[],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )
    assert f.axis == "conformance"
    assert f.evidence_embedded.expected_ledger_step["expect"] == "x"


def test_fitness_diff_aggregates() -> None:
    diff = FitnessDiff(
        run_id="r1",
        steps=[],
        created=[],
        updated=[],
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    assert diff.run_id == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.fitness.models'`.

- [ ] **Step 3: Implement models**

```python
# src/dazzle/fitness/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


Axis = Literal["coverage", "conformance"]
Locus = Literal["implementation", "story_drift", "spec_stale", "lifecycle"]
Severity = Literal["critical", "high", "medium", "low"]
Route = Literal["hard", "soft"]
FindingStatus = Literal[
    "PROPOSED", "ACCEPTED", "IN_PROGRESS", "FIXED", "VERIFIED", "REJECTED"
]
ChangeKind = Literal["insert", "update", "delete"]


@dataclass(frozen=True)
class RowChange:
    table: str
    row_id: str
    kind: ChangeKind
    semantic_repr: str
    field_deltas: dict[str, tuple[Any, Any]]


@dataclass(frozen=True)
class ProgressRecord:
    """A single lifecycle-progress observation.

    Produced by `progress_evaluator.py` from lifecycle-declared entities
    touched during the run.
    """

    entity: str
    row_id: str
    transitions_observed: list[tuple[str, str]]  # (from_state, to_state)
    evidence_satisfied: list[bool]  # parallel to transitions_observed
    ended_at_state: str
    was_progress: bool


@dataclass(frozen=True)
class LedgerStep:
    step_no: int
    txn_id: str | None
    expected: str
    action_summary: str
    observed_ui: str
    observed_changes: list[RowChange]
    delta: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.expected or not self.expected.strip():
            raise ValueError(
                "LedgerStep.expected must be non-empty "
                "(interlock enforces EXPECT before ACTION)"
            )


@dataclass(frozen=True)
class FitnessDiff:
    run_id: str
    steps: list[LedgerStep]
    created: list[RowChange]
    updated: list[RowChange]
    deleted: list[RowChange]
    progress: list[ProgressRecord]
    semantic_repr_config: dict[str, list[str]]


@dataclass(frozen=True)
class EvidenceEmbedded:
    expected_ledger_step: dict[str, Any]
    diff_summary: list[RowChange]
    transcript_excerpt: list[dict[str, Any]]  # Raw step dicts ±3 around finding


@dataclass(frozen=True)
class Finding:
    id: str
    created: datetime
    run_id: str
    cycle: str | None
    axis: Axis
    locus: Locus
    severity: Severity
    persona: str
    capability_ref: str
    expected: str
    observed: str
    evidence_embedded: EvidenceEmbedded
    disambiguation: bool
    low_confidence: bool
    status: FindingStatus
    route: Route
    fix_commit: str | None
    alternative_fix: str | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_models.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/models.py tests/unit/fitness/test_models.py
git commit -m "feat(fitness): shared models — Finding, LedgerStep, FitnessDiff (v1 task 3)"
```

---

## Task 4: FitnessLedger abstract interface + snapshot implementation

The ledger records every step of a fitness run. v1 uses a snapshot-diff strategy: take a snapshot of relevant tables before each step, run the action, take a second snapshot, compute the row-level diff. Not transactionally isolated, but fits behind the same abstract interface as later WAL/SAVEPOINT variants.

**Files:**
- Create: `src/dazzle/fitness/ledger.py`
- Create: `src/dazzle/fitness/ledger_snapshot.py`
- Test: `tests/unit/fitness/test_ledger_snapshot.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_ledger_snapshot.py
import pytest

from dazzle.fitness.ledger import FitnessLedger
from dazzle.fitness.ledger_snapshot import SnapshotLedger
from dazzle.fitness.models import FitnessDiff


class FakePool:
    """Minimal asyncpg-pool-shaped stub for unit tests."""

    def __init__(self) -> None:
        # table_name -> list of row dicts
        self._tables: dict[str, list[dict]] = {
            "ticket": [
                {"id": "t1", "title": "Broken login", "status": "new"},
            ]
        }

    async def fetch(self, query: str):  # noqa: ANN202
        # Tests will monkey-patch snapshot() directly; fetch is unused.
        raise NotImplementedError


@pytest.fixture
def repr_map() -> dict[str, list[str]]:
    return {"ticket": ["title", "status"]}


@pytest.mark.asyncio
async def test_snapshot_ledger_records_single_step(
    monkeypatch, repr_map: dict[str, list[str]]
) -> None:
    ledger = SnapshotLedger(pool=FakePool(), repr_fields=repr_map)
    ledger.open("run-1")

    async def fake_snapshot(tables):
        return {
            "ticket": [
                {"id": "t1", "title": "Broken login", "status": "new"},
            ]
        }

    async def fake_snapshot_after(tables):
        return {
            "ticket": [
                {"id": "t1", "title": "Broken login", "status": "in_progress"},
            ]
        }

    snapshots = iter([fake_snapshot, fake_snapshot_after])
    monkeypatch.setattr(
        ledger, "_snapshot", lambda tables: next(snapshots)(tables)
    )

    ledger.record_intent(step=1, expect="status advances", action_desc="click")
    await ledger.observe_step(step=1, observed_ui="ok")
    ledger.close()

    diff: FitnessDiff = ledger.summarize()
    assert diff.run_id == "run-1"
    assert len(diff.steps) == 1
    assert diff.steps[0].expected == "status advances"
    assert len(diff.updated) == 1
    assert diff.updated[0].table == "ticket"
    assert diff.updated[0].field_deltas["status"] == ("new", "in_progress")


@pytest.mark.asyncio
async def test_snapshot_ledger_rejects_step_without_intent(repr_map) -> None:
    ledger = SnapshotLedger(pool=FakePool(), repr_fields=repr_map)
    ledger.open("run-2")

    with pytest.raises(ValueError, match="intent"):
        await ledger.observe_step(step=1, observed_ui="ok")


def test_snapshot_ledger_is_a_fitness_ledger(repr_map) -> None:
    ledger = SnapshotLedger(pool=FakePool(), repr_fields=repr_map)
    assert isinstance(ledger, FitnessLedger)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_ledger_snapshot.py -v`
Expected: FAIL — modules don't exist.

- [ ] **Step 3: Implement abstract ledger**

```python
# src/dazzle/fitness/ledger.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from dazzle.fitness.models import FitnessDiff, LedgerStep


class FitnessLedger(ABC):
    """Abstract interface for per-run fitness observation storage.

    Three implementations planned:

    - `SnapshotLedger` (v1) — polls DB tables before/after each step
    - `SavepointLedger` (v1.1) — wraps each step in a SAVEPOINT
    - `WalLedger` (v1.2) — subscribes to a logical replication slot

    All three produce the same `FitnessDiff` shape.
    """

    @abstractmethod
    def open(self, run_id: str) -> None: ...

    @abstractmethod
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...

    @abstractmethod
    async def observe_step(self, step: int, observed_ui: str) -> None: ...

    @abstractmethod
    def current_step(self) -> LedgerStep | None: ...

    @abstractmethod
    def summarize(self) -> FitnessDiff: ...

    @abstractmethod
    def close(self, rollback: bool = False) -> None: ...
```

- [ ] **Step 4: Implement snapshot ledger**

```python
# src/dazzle/fitness/ledger_snapshot.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.fitness.ledger import FitnessLedger
from dazzle.fitness.models import (
    FitnessDiff,
    LedgerStep,
    RowChange,
)


@dataclass
class _PendingIntent:
    step_no: int
    expect: str
    action_desc: str
    before_snapshot: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class SnapshotLedger(FitnessLedger):
    """v1 snapshot-diff ledger.

    Before every step the ledger polls SELECT * FROM each repr-declared table;
    after the step it polls again and diffs the row sets. Not isolated (shared
    pool), ordering is by dense step_no counter.
    """

    def __init__(
        self, pool: Any, repr_fields: dict[str, list[str]]
    ) -> None:
        self._pool = pool
        self._repr_fields = repr_fields
        self._run_id: str | None = None
        self._steps: list[LedgerStep] = []
        self._created: list[RowChange] = []
        self._updated: list[RowChange] = []
        self._deleted: list[RowChange] = []
        self._pending: _PendingIntent | None = None

    def open(self, run_id: str) -> None:
        self._run_id = run_id
        self._steps = []
        self._created = []
        self._updated = []
        self._deleted = []
        self._pending = None

    def record_intent(
        self, step: int, expect: str, action_desc: str
    ) -> None:
        if not expect or not expect.strip():
            raise ValueError(
                "record_intent: expect must be non-empty "
                "(interlock enforces EXPECT before ACTION)"
            )
        self._pending = _PendingIntent(
            step_no=step, expect=expect, action_desc=action_desc
        )

    async def observe_step(self, step: int, observed_ui: str) -> None:
        if self._pending is None or self._pending.step_no != step:
            raise ValueError(
                f"observe_step({step}): no prior record_intent for this step"
            )
        before = await self._snapshot(list(self._repr_fields.keys()))
        after = await self._snapshot(list(self._repr_fields.keys()))
        row_changes = self._diff(before, after)
        for rc in row_changes:
            if rc.kind == "insert":
                self._created.append(rc)
            elif rc.kind == "update":
                self._updated.append(rc)
            elif rc.kind == "delete":
                self._deleted.append(rc)

        ledger_step = LedgerStep(
            step_no=step,
            txn_id=None,  # v1.1+
            expected=self._pending.expect,
            action_summary=self._pending.action_desc,
            observed_ui=observed_ui,
            observed_changes=row_changes,
            delta={"row_change_count": len(row_changes)},
        )
        self._steps.append(ledger_step)
        self._pending = None

    def current_step(self) -> LedgerStep | None:
        return self._steps[-1] if self._steps else None

    def summarize(self) -> FitnessDiff:
        if self._run_id is None:
            raise RuntimeError("summarize(): ledger is not open")
        return FitnessDiff(
            run_id=self._run_id,
            steps=list(self._steps),
            created=list(self._created),
            updated=list(self._updated),
            deleted=list(self._deleted),
            progress=[],  # populated by progress_evaluator
            semantic_repr_config=dict(self._repr_fields),
        )

    def close(self, rollback: bool = False) -> None:
        # v1 snapshot ledger has no transactional state to roll back.
        self._run_id = None
        self._pending = None

    async def _snapshot(
        self, tables: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Read row dicts for each table, limited to repr_fields + id."""
        out: dict[str, list[dict[str, Any]]] = {}
        for t in tables:
            cols = ["id", *self._repr_fields[t]]
            col_list = ", ".join(cols)
            query = f"SELECT {col_list} FROM {t}"  # noqa: S608
            rows = await self._pool.fetch(query)
            out[t] = [dict(r) for r in rows]
        return out

    def _diff(
        self,
        before: dict[str, list[dict[str, Any]]],
        after: dict[str, list[dict[str, Any]]],
    ) -> list[RowChange]:
        changes: list[RowChange] = []
        for table in self._repr_fields:
            before_rows = {r["id"]: r for r in before.get(table, [])}
            after_rows = {r["id"]: r for r in after.get(table, [])}
            # Inserts
            for rid, row in after_rows.items():
                if rid not in before_rows:
                    changes.append(
                        RowChange(
                            table=table,
                            row_id=str(rid),
                            kind="insert",
                            semantic_repr=self._repr(table, row),
                            field_deltas={
                                k: (None, row.get(k))
                                for k in self._repr_fields[table]
                            },
                        )
                    )
            # Updates
            for rid, b in before_rows.items():
                if rid in after_rows:
                    a = after_rows[rid]
                    deltas = {
                        k: (b.get(k), a.get(k))
                        for k in self._repr_fields[table]
                        if b.get(k) != a.get(k)
                    }
                    if deltas:
                        changes.append(
                            RowChange(
                                table=table,
                                row_id=str(rid),
                                kind="update",
                                semantic_repr=self._repr(table, a),
                                field_deltas=deltas,
                            )
                        )
            # Deletes
            for rid, row in before_rows.items():
                if rid not in after_rows:
                    changes.append(
                        RowChange(
                            table=table,
                            row_id=str(rid),
                            kind="delete",
                            semantic_repr=self._repr(table, row),
                            field_deltas={
                                k: (row.get(k), None)
                                for k in self._repr_fields[table]
                            },
                        )
                    )
        return changes

    def _repr(self, table: str, row: dict[str, Any]) -> str:
        parts = [f"{k}={row.get(k)!r}" for k in self._repr_fields[table]]
        return f"{table}({', '.join(parts)})"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_ledger_snapshot.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/fitness/ledger.py src/dazzle/fitness/ledger_snapshot.py tests/unit/fitness/test_ledger_snapshot.py
git commit -m "feat(fitness): FitnessLedger interface + snapshot impl (v1 task 4)"
```

---

## Task 5: Interlock — EXPECT-before-ACTION enforcement

The interlock is ~30 lines and eliminates the "agent drifted off protocol" failure class.

**Files:**
- Create: `src/dazzle/fitness/interlock.py`
- Test: `tests/unit/fitness/test_interlock.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_interlock.py
import pytest

from dazzle.fitness.interlock import InterlockError, interlocked_tool_call
from dazzle.fitness.ledger_snapshot import SnapshotLedger


class _NoExpect:
    """Stub ledger with no intent recorded."""

    def current_step(self):
        return None


class _WithExpect:
    """Stub ledger with intent recorded."""

    def __init__(self):
        self.observed = None

    def current_step(self):
        # Return an object that behaves like LedgerStep for the interlock.
        class _S:
            expected = "the button is clicked"

        return _S()

    def record_observation(self, step, observed):
        self.observed = observed


def test_interlock_rejects_when_no_expect() -> None:
    def tool(x: int) -> int:
        return x + 1

    with pytest.raises(InterlockError, match="no EXPECT"):
        interlocked_tool_call(_NoExpect(), tool, {"x": 1})


def test_interlock_passes_through_when_expect_present() -> None:
    ledger = _WithExpect()

    def tool(x: int) -> int:
        return x + 1

    result = interlocked_tool_call(ledger, tool, {"x": 1})
    assert result == 2
    # The interlock does NOT call record_observation — that's the ledger's
    # observe_step's job. It only guards the pre-condition.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_interlock.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement interlock**

```python
# src/dazzle/fitness/interlock.py
from __future__ import annotations

from typing import Any, Callable, Protocol


class InterlockError(RuntimeError):
    """Raised when an action is attempted without a recorded EXPECT."""


class _LedgerLike(Protocol):
    def current_step(self) -> Any: ...


def interlocked_tool_call(
    ledger: _LedgerLike,
    tool: Callable[..., Any],
    args: dict[str, Any],
) -> Any:
    """Gate a tool call on EXPECT-having-been-recorded.

    This is the v1 "reject on missing intent" variant. v2 will replace rejection
    with "synthesize EXPECT via a second LLM call, then execute", which never
    blocks progress but costs more tokens.
    """
    last_step = ledger.current_step()
    expected = getattr(last_step, "expected", None) if last_step is not None else None
    if not expected or not str(expected).strip():
        raise InterlockError(
            "Tool call rejected: no EXPECT recorded for this step. "
            "Emit `expect: <what you think will happen>` before calling tools."
        )
    return tool(**args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_interlock.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/interlock.py tests/unit/fitness/test_interlock.py
git commit -m "feat(fitness): EXPECT-before-ACTION interlock (v1 task 5)"
```

---

## Task 6: Budget + degradation ladder

Per-cycle budget with a degradation ladder: shed free-roam steps first, then adversary, then Pass 2b entirely. Pass 1 is never degraded.

**Files:**
- Create: `src/dazzle/fitness/budget.py`
- Test: `tests/unit/fitness/test_budget.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_budget.py
from dazzle.fitness.budget import BudgetController, CycleProfile
from dazzle.fitness.config import FitnessConfig


def test_full_budget_runs_all_passes() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile: CycleProfile = bc.plan(available_tokens=100_000)
    assert profile.run_pass1 is True
    assert profile.run_pass2a is True
    assert profile.run_pass2b is True
    assert profile.pass2b_step_budget == 50
    assert profile.adversary_enabled is True
    assert profile.degraded is False


def test_moderate_pressure_shortens_pass2b() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=60_000)
    assert profile.run_pass2b is True
    assert profile.pass2b_step_budget == 20
    assert profile.adversary_enabled is True
    assert profile.degraded is True


def test_heavy_pressure_drops_adversary() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=25_000)
    assert profile.run_pass2b is True
    assert profile.adversary_enabled is False
    assert profile.degraded is True


def test_severe_pressure_drops_pass2b() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=10_000)
    assert profile.run_pass2b is False
    assert profile.run_pass1 is True
    assert profile.degraded is True


def test_pass1_is_never_dropped() -> None:
    cfg = FitnessConfig(max_tokens_per_cycle=100_000)
    bc = BudgetController(cfg)
    profile = bc.plan(available_tokens=0)
    assert profile.run_pass1 is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_budget.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement budget controller**

```python
# src/dazzle/fitness/budget.py
from __future__ import annotations

from dataclasses import dataclass

from dazzle.fitness.config import FitnessConfig


@dataclass(frozen=True)
class CycleProfile:
    run_pass1: bool
    run_pass2a: bool
    run_pass2b: bool
    pass2b_step_budget: int
    adversary_enabled: bool
    degraded: bool
    reason: str


# Approximate token costs per phase, used for planning only.
_TOKENS_PER_PASS2B_STEP = 1500  # ~1.5k per EXPECT/ACTION/OBSERVE cycle
_TOKENS_PASS2A_CORE = 8_000     # spec_extractor + cross_check
_TOKENS_PASS2A_ADVERSARY = 4_000
_PASS2B_FULL_STEPS = 50
_PASS2B_SHORT_STEPS = 20


class BudgetController:
    def __init__(self, config: FitnessConfig) -> None:
        self._config = config

    def plan(self, available_tokens: int) -> CycleProfile:
        full_cost = (
            _TOKENS_PASS2A_CORE
            + _TOKENS_PASS2A_ADVERSARY
            + _PASS2B_FULL_STEPS * _TOKENS_PER_PASS2B_STEP
        )
        short_cost = (
            _TOKENS_PASS2A_CORE
            + _TOKENS_PASS2A_ADVERSARY
            + _PASS2B_SHORT_STEPS * _TOKENS_PER_PASS2B_STEP
        )
        core_only_cost = _TOKENS_PASS2A_CORE + _PASS2B_SHORT_STEPS * _TOKENS_PER_PASS2B_STEP
        minimum_cost = _TOKENS_PASS2A_CORE  # Pass 1 is free

        if available_tokens >= full_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_FULL_STEPS,
                adversary_enabled=True,
                degraded=False,
                reason="full budget",
            )
        if available_tokens >= short_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_SHORT_STEPS,
                adversary_enabled=True,
                degraded=True,
                reason="pass2b shortened",
            )
        if available_tokens >= core_only_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=True,
                pass2b_step_budget=_PASS2B_SHORT_STEPS,
                adversary_enabled=False,
                degraded=True,
                reason="adversary dropped",
            )
        if available_tokens >= minimum_cost:
            return CycleProfile(
                run_pass1=True,
                run_pass2a=True,
                run_pass2b=False,
                pass2b_step_budget=0,
                adversary_enabled=False,
                degraded=True,
                reason="pass2b dropped",
            )
        return CycleProfile(
            run_pass1=True,
            run_pass2a=False,
            run_pass2b=False,
            pass2b_step_budget=0,
            adversary_enabled=False,
            degraded=True,
            reason="pass1 only",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_budget.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/budget.py tests/unit/fitness/test_budget.py
git commit -m "feat(fitness): budget controller + degradation ladder (v1 task 6)"
```

---

## Task 7: Progress evaluator (depends on ADR-0020)

Consumes lifecycle declarations + ledger RowChanges and emits ProgressRecords. A transition is "progress" iff it advances `order` AND the evidence predicate holds.

**Files:**
- Create: `src/dazzle/fitness/progress_evaluator.py`
- Test: `tests/unit/fitness/test_progress_evaluator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_progress_evaluator.py
from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)
from dazzle.fitness.models import FitnessDiff, LedgerStep, RowChange
from dazzle.fitness.progress_evaluator import evaluate_progress


def _lifecycle() -> LifecycleSpec:
    return LifecycleSpec(
        entity="Ticket",
        status_field="status",
        states=[
            LifecycleStateSpec(name="new", order=0),
            LifecycleStateSpec(name="in_progress", order=1),
            LifecycleStateSpec(name="resolved", order=2),
        ],
        transitions=[
            LifecycleTransitionSpec(
                from_state="new", to_state="in_progress", evidence="true"
            ),
            LifecycleTransitionSpec(
                from_state="in_progress",
                to_state="resolved",
                evidence="resolution_notes != null",
            ),
        ],
    )


def test_valid_transition_counts_as_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t1",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("new", "in_progress")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    # entity field state is the updated row
    entity_state = {"t1": {"status": "in_progress", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state)
    assert len(records) == 1
    assert records[0].was_progress is True


def test_unsatisfied_evidence_is_not_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t2",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("in_progress", "resolved")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    # Agent clicked "resolve" without filling resolution_notes.
    entity_state = {"t2": {"status": "resolved", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state)
    assert records[0].was_progress is False


def test_backward_transition_is_not_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t3",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("in_progress", "new")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    entity_state = {"t3": {"status": "new", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state)
    assert records[0].was_progress is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_progress_evaluator.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement progress evaluator**

```python
# src/dazzle/fitness/progress_evaluator.py
from __future__ import annotations

from typing import Any

from dazzle.core.ir.lifecycle import LifecycleSpec
from dazzle.fitness.models import (
    FitnessDiff,
    ProgressRecord,
    RowChange,
)


def evaluate_progress(
    lifecycle: LifecycleSpec,
    diff: FitnessDiff,
    entity_state: dict[str, dict[str, Any]],
) -> list[ProgressRecord]:
    """Classify each status change in `diff` as progress or motion.

    Args:
        lifecycle: The lifecycle declaration for this entity type.
        diff: The ledger diff for the run.
        entity_state: Map of row_id → current row dict (post-run state).
            Used to evaluate evidence predicates.

    Returns:
        One ProgressRecord per row that had a status change.
    """
    order_map = {s.name: s.order for s in lifecycle.states}
    transition_map = {
        (t.from_state, t.to_state): t for t in lifecycle.transitions
    }
    status_col = lifecycle.status_field

    # Group row changes by row_id
    by_row: dict[str, list[RowChange]] = {}
    for rc in diff.updated:
        if rc.table.lower() != lifecycle.entity.lower():
            continue
        if status_col not in rc.field_deltas:
            continue
        by_row.setdefault(rc.row_id, []).append(rc)

    records: list[ProgressRecord] = []
    for row_id, changes in by_row.items():
        transitions_observed: list[tuple[str, str]] = []
        evidence_satisfied: list[bool] = []
        current_row = entity_state.get(row_id, {})

        for rc in changes:
            before, after = rc.field_deltas[status_col]
            transitions_observed.append((str(before), str(after)))

            transition = transition_map.get((str(before), str(after)))
            if transition is None:
                evidence_satisfied.append(False)
                continue

            evidence_holds = _evaluate_evidence(
                transition.evidence, current_row
            )
            is_forward = (
                order_map.get(str(after), -1) > order_map.get(str(before), -1)
            )
            evidence_satisfied.append(evidence_holds and is_forward)

        was_progress = any(evidence_satisfied)
        ended_at = (
            transitions_observed[-1][1] if transitions_observed else "unknown"
        )

        records.append(
            ProgressRecord(
                entity=lifecycle.entity,
                row_id=row_id,
                transitions_observed=transitions_observed,
                evidence_satisfied=evidence_satisfied,
                ended_at_state=ended_at,
                was_progress=was_progress,
            )
        )
    return records


def _evaluate_evidence(expression: str, row: dict[str, Any]) -> bool:
    """Tiny evaluator for v1 evidence predicates.

    Supported forms (matches the ADR-0020 grammar):
      - `true`
      - `false`
      - `<field> != null`
      - `<field> = null`
      - `<field> != ""`
      - `<field> = ""`
      - `<expr> AND <expr>`
      - `<expr> OR <expr>`

    Richer predicate support is deferred to v1.1 when the core predicate
    algebra is linked in directly.
    """
    expr = expression.strip()
    if expr == "true":
        return True
    if expr == "false":
        return False

    if " AND " in expr:
        parts = [p.strip() for p in expr.split(" AND ")]
        return all(_evaluate_evidence(p, row) for p in parts)
    if " OR " in expr:
        parts = [p.strip() for p in expr.split(" OR ")]
        return any(_evaluate_evidence(p, row) for p in parts)

    # <field> <op> <literal>
    for op, fn in (
        ("!= null", lambda v: v is not None),
        ("= null", lambda v: v is None),
        ('!= ""', lambda v: v is not None and v != ""),
        ('= ""', lambda v: v == ""),
    ):
        if op in expr:
            field = expr.split(op)[0].strip()
            return fn(row.get(field))

    # Unknown form — treat as unsatisfied; v1.1 will fail-loud here.
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_progress_evaluator.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/progress_evaluator.py tests/unit/fitness/test_progress_evaluator.py
git commit -m "feat(fitness): progress evaluator (motion vs work) (v1 task 7)"
```

---

## Task 8: spec_extractor — reads spec.md only

Pass 2a-A: extracts jobs-to-be-done from `spec.md`. No DSL access.

**Files:**
- Create: `src/dazzle/fitness/spec_extractor.py`
- Test: `tests/unit/fitness/test_spec_extractor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_spec_extractor.py
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dazzle.fitness.spec_extractor import Capability, extract_spec_capabilities


@pytest.mark.asyncio
async def test_extract_returns_capability_list(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Support System\n\n"
        "My team needs to triage tickets quickly.\n"
        "When a customer emails support, the ticket goes to whoever's on rotation.\n"
        "Once resolved, the assignee writes a resolution note.\n"
    )

    fake_llm = AsyncMock()
    fake_llm.ask.return_value = (
        '[{"capability": "triage incoming ticket", "persona": "support_agent"},'
        ' {"capability": "resolve ticket with notes", "persona": "support_agent"}]'
    )

    caps = await extract_spec_capabilities(spec, llm=fake_llm)
    assert len(caps) == 2
    assert caps[0].capability == "triage incoming ticket"
    assert caps[0].persona == "support_agent"


@pytest.mark.asyncio
async def test_extract_returns_empty_list_on_malformed_json(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("irrelevant")

    fake_llm = AsyncMock()
    fake_llm.ask.return_value = "this is not json"

    caps = await extract_spec_capabilities(spec, llm=fake_llm)
    assert caps == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_spec_extractor.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement extractor**

```python
# src/dazzle/fitness/spec_extractor.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Capability:
    capability: str
    persona: str


class _LlmLike(Protocol):
    async def ask(self, prompt: str, **kwargs: Any) -> str: ...


_PROMPT_TEMPLATE = """You are an analyst reading a product spec. Extract the \
discrete jobs-to-be-done (capabilities) this spec describes, and the persona \
who performs each.

Return ONLY a JSON array. Each element must be:
  {{"capability": "<short verb phrase>", "persona": "<role name>"}}

DO NOT include any other commentary.

Spec:
---
{spec_text}
---
"""


async def extract_spec_capabilities(
    spec_path: Path, llm: _LlmLike
) -> list[Capability]:
    text = spec_path.read_text()
    prompt = _PROMPT_TEMPLATE.format(spec_text=text)
    response = await llm.ask(prompt)
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[Capability] = []
    for item in parsed:
        if (
            isinstance(item, dict)
            and isinstance(item.get("capability"), str)
            and isinstance(item.get("persona"), str)
        ):
            out.append(
                Capability(
                    capability=item["capability"], persona=item["persona"]
                )
            )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_spec_extractor.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/spec_extractor.py tests/unit/fitness/test_spec_extractor.py
git commit -m "feat(fitness): spec_extractor reads spec.md only (v1 task 8)"
```

---

## Task 9: adversary — reads stories only

Structural independence: the adversary NEVER sees `spec.md`. Its input is the DSL story list.

**Files:**
- Create: `src/dazzle/fitness/adversary.py`
- Test: `tests/unit/fitness/test_adversary.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_adversary.py
import json
from unittest.mock import AsyncMock

import pytest

from dazzle.fitness.adversary import synthesize_from_stories
from dazzle.fitness.spec_extractor import Capability


class _StoryStub:
    def __init__(self, id: str, title: str, persona: str, steps: list[str]):
        self.id = id
        self.title = title
        self.persona = persona
        self.steps = steps


@pytest.mark.asyncio
async def test_adversary_receives_only_stories() -> None:
    stories = [
        _StoryStub("s1", "Triage new ticket", "support_agent", ["open queue"]),
        _StoryStub("s2", "Resolve with notes", "support_agent", ["click resolve"]),
    ]
    fake_llm = AsyncMock()
    fake_llm.ask.return_value = json.dumps(
        [
            {"capability": "triage", "persona": "support_agent"},
            {"capability": "resolve", "persona": "support_agent"},
        ]
    )

    caps = await synthesize_from_stories(stories, llm=fake_llm)

    assert len(caps) == 2
    assert isinstance(caps[0], Capability)
    # Verify the prompt did NOT contain spec-file references
    call_args = fake_llm.ask.call_args
    prompt = call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
    assert "spec.md" not in prompt
    assert "Triage new ticket" in prompt


@pytest.mark.asyncio
async def test_adversary_handles_empty_story_list() -> None:
    fake_llm = AsyncMock()
    caps = await synthesize_from_stories([], llm=fake_llm)
    assert caps == []
    fake_llm.ask.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_adversary.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement adversary**

```python
# src/dazzle/fitness/adversary.py
from __future__ import annotations

import json
from typing import Any, Protocol, Sequence

from dazzle.fitness.spec_extractor import Capability


class _LlmLike(Protocol):
    async def ask(self, prompt: str, **kwargs: Any) -> str: ...


_PROMPT_TEMPLATE = """You are an adversarial re-reader. You have access to ONLY \
this list of user stories — no spec, no founder intent, nothing else.

Infer what this application is trying to do. What discrete jobs-to-be-done \
(capabilities) do these stories collectively imply? Assume nothing you cannot \
derive from the stories themselves.

Return ONLY a JSON array:
  [{{"capability": "<phrase>", "persona": "<role>"}}]

Stories:
---
{story_dump}
---
"""


async def synthesize_from_stories(
    stories: Sequence[Any], llm: _LlmLike
) -> list[Capability]:
    if not stories:
        return []

    lines: list[str] = []
    for s in stories:
        sid = getattr(s, "id", "?")
        title = getattr(s, "title", "(untitled)")
        persona = getattr(s, "persona", "?")
        steps = getattr(s, "steps", [])
        lines.append(f"- [{sid}] {title} (persona={persona})")
        for step in steps:
            lines.append(f"    · {step}")
    story_dump = "\n".join(lines)

    prompt = _PROMPT_TEMPLATE.format(story_dump=story_dump)
    response = await llm.ask(prompt)
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    out: list[Capability] = []
    for item in parsed:
        if (
            isinstance(item, dict)
            and isinstance(item.get("capability"), str)
            and isinstance(item.get("persona"), str)
        ):
            out.append(
                Capability(
                    capability=item["capability"], persona=item["persona"]
                )
            )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_adversary.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/adversary.py tests/unit/fitness/test_adversary.py
git commit -m "feat(fitness): adversary (structural independence, stories only) (v1 task 9)"
```

---

## Task 10: independence — Jaccard similarity guardrail

Measures correlation between sensors. When Jaccard > threshold, emit `INDEPENDENCE_DEGRADED` signal.

**Files:**
- Create: `src/dazzle/fitness/independence.py`
- Test: `tests/unit/fitness/test_independence.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_independence.py
from dazzle.fitness.independence import (
    IndependenceReport,
    measure_independence,
)
from dazzle.fitness.spec_extractor import Capability


def _caps(*pairs: tuple[str, str]) -> list[Capability]:
    return [Capability(capability=c, persona=p) for c, p in pairs]


def test_perfect_overlap_flags_degraded() -> None:
    a = _caps(("triage", "agent"), ("resolve", "agent"))
    b = _caps(("triage", "agent"), ("resolve", "agent"))
    report = measure_independence(a, b, threshold=0.85)
    assert report.jaccard == 1.0
    assert report.degraded is True


def test_zero_overlap_is_maximally_independent() -> None:
    a = _caps(("triage", "agent"))
    b = _caps(("checkout", "customer"))
    report = measure_independence(a, b, threshold=0.85)
    assert report.jaccard == 0.0
    assert report.degraded is False


def test_partial_overlap_below_threshold() -> None:
    a = _caps(("triage", "agent"), ("resolve", "agent"), ("escalate", "agent"))
    b = _caps(("triage", "agent"), ("reject", "agent"), ("reopen", "agent"))
    report = measure_independence(a, b, threshold=0.85)
    assert 0.0 < report.jaccard < 0.85
    assert report.degraded is False
    assert report.shared == [("triage", "agent")]


def test_empty_inputs_are_insufficient_data() -> None:
    report = measure_independence([], [], threshold=0.85)
    assert report.jaccard == 0.0
    assert report.insufficient_data is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_independence.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement independence**

```python
# src/dazzle/fitness/independence.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from dazzle.fitness.spec_extractor import Capability


@dataclass(frozen=True)
class IndependenceReport:
    jaccard: float
    shared: list[tuple[str, str]]
    only_a: list[tuple[str, str]]
    only_b: list[tuple[str, str]]
    threshold: float
    degraded: bool
    insufficient_data: bool


def _as_set(caps: Iterable[Capability]) -> set[tuple[str, str]]:
    return {(c.capability.strip().lower(), c.persona.strip().lower()) for c in caps}


def measure_independence(
    sensor_a: list[Capability],
    sensor_b: list[Capability],
    threshold: float,
) -> IndependenceReport:
    set_a = _as_set(sensor_a)
    set_b = _as_set(sensor_b)

    if not set_a and not set_b:
        return IndependenceReport(
            jaccard=0.0,
            shared=[],
            only_a=[],
            only_b=[],
            threshold=threshold,
            degraded=False,
            insufficient_data=True,
        )

    intersection = set_a & set_b
    union = set_a | set_b
    jaccard = len(intersection) / len(union) if union else 0.0

    return IndependenceReport(
        jaccard=jaccard,
        shared=sorted(intersection),
        only_a=sorted(set_a - set_b),
        only_b=sorted(set_b - set_a),
        threshold=threshold,
        degraded=jaccard > threshold,
        insufficient_data=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_independence.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/independence.py tests/unit/fitness/test_independence.py
git commit -m "feat(fitness): independence guardrail (Jaccard) (v1 task 10)"
```

---

## Task 11: cross_check — coverage and over-implementation findings

Takes capabilities (from spec_extractor) and stories (from DSL) and emits coverage/over-impl findings.

**Files:**
- Create: `src/dazzle/fitness/cross_check.py`
- Test: `tests/unit/fitness/test_cross_check.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_cross_check.py
from datetime import datetime, timezone

from dazzle.fitness.cross_check import cross_check_capabilities
from dazzle.fitness.spec_extractor import Capability


class _Story:
    def __init__(self, id: str, title: str, persona: str) -> None:
        self.id = id
        self.title = title
        self.persona = persona


def test_spec_capability_with_no_matching_story_yields_coverage_finding() -> None:
    caps = [Capability(capability="triage incoming ticket", persona="support_agent")]
    stories = [_Story("s1", "close ticket", "support_agent")]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    coverage = [f for f in findings if f.axis == "coverage"]
    assert len(coverage) == 1
    assert coverage[0].locus == "story_drift"
    assert "triage" in coverage[0].capability_ref


def test_story_with_no_matching_capability_yields_over_impl_finding() -> None:
    caps = [Capability(capability="triage", persona="support_agent")]
    stories = [
        _Story("s1", "triage new ticket", "support_agent"),
        _Story("s2", "export CSV report", "support_agent"),
    ]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    over = [f for f in findings if f.locus == "spec_stale"]
    assert len(over) == 1
    assert "export" in over[0].capability_ref


def test_perfect_match_yields_no_findings() -> None:
    caps = [Capability(capability="triage", persona="agent")]
    stories = [_Story("s1", "triage ticket", "agent")]

    findings = cross_check_capabilities(
        spec_capabilities=caps,
        stories=stories,
        run_id="r1",
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_cross_check.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement cross_check**

```python
# src/dazzle/fitness/cross_check.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.spec_extractor import Capability


def _tokens(text: str) -> set[str]:
    return {t.lower().strip() for t in text.replace("-", " ").split() if t.strip()}


def _similar(a: str, b: str) -> bool:
    """Shallow lexical match — v1.1 may upgrade to embedding similarity."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = ta & tb
    return len(overlap) / min(len(ta), len(tb)) >= 0.4


def cross_check_capabilities(
    spec_capabilities: Sequence[Capability],
    stories: Sequence[Any],
    run_id: str,
    now: datetime,
) -> list[Finding]:
    findings: list[Finding] = []

    # Coverage: spec capability → no matching story
    for cap in spec_capabilities:
        matched = any(
            _similar(cap.capability, getattr(s, "title", ""))
            for s in stories
        )
        if not matched:
            findings.append(
                Finding(
                    id=f"FIND-{uuid4().hex[:8]}",
                    created=now,
                    run_id=run_id,
                    cycle=None,
                    axis="coverage",
                    locus="story_drift",
                    severity="medium",
                    persona=cap.persona,
                    capability_ref=f"spec:{cap.capability}",
                    expected=(
                        f"A DSL story implementing '{cap.capability}' for "
                        f"persona '{cap.persona}'"
                    ),
                    observed="No matching story found",
                    evidence_embedded=EvidenceEmbedded(
                        expected_ledger_step={},
                        diff_summary=[],
                        transcript_excerpt=[],
                    ),
                    disambiguation=False,
                    low_confidence=False,
                    status="PROPOSED",
                    route="soft",  # coverage findings default soft
                    fix_commit=None,
                    alternative_fix=None,
                )
            )

    # Over-impl: story → no matching spec capability
    for s in stories:
        title = getattr(s, "title", "")
        persona = getattr(s, "persona", "?")
        matched = any(
            _similar(title, cap.capability) for cap in spec_capabilities
        )
        if not matched:
            findings.append(
                Finding(
                    id=f"FIND-{uuid4().hex[:8]}",
                    created=now,
                    run_id=run_id,
                    cycle=None,
                    axis="coverage",
                    locus="spec_stale",
                    severity="low",
                    persona=persona,
                    capability_ref=f"story:{title}",
                    expected=(
                        f"Spec clause implying '{title}' for persona "
                        f"'{persona}'"
                    ),
                    observed="No matching spec clause found",
                    evidence_embedded=EvidenceEmbedded(
                        expected_ledger_step={},
                        diff_summary=[],
                        transcript_excerpt=[],
                    ),
                    disambiguation=False,
                    low_confidence=False,
                    status="PROPOSED",
                    route="soft",
                    fix_commit=None,
                    alternative_fix=None,
                )
            )

    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_cross_check.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/cross_check.py tests/unit/fitness/test_cross_check.py
git commit -m "feat(fitness): cross_check (coverage + over-impl findings) (v1 task 11)"
```

---

## Task 12: walker — Pass 1 deterministic story walker

The walker drives Playwright through each story's action steps scripted from the DSL. No LLM calls.

**Files:**
- Create: `src/dazzle/fitness/missions/__init__.py`
- Create: `src/dazzle/fitness/missions/story_walk.py`
- Create: `src/dazzle/fitness/walker.py`
- Test: `tests/unit/fitness/test_walker.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_walker.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.ledger_snapshot import SnapshotLedger
from dazzle.fitness.walker import WalkResult, walk_story


class _Story:
    def __init__(self, id: str, persona: str, steps: list[dict]) -> None:
        self.id = id
        self.persona = persona
        self.steps = steps


@pytest.mark.asyncio
async def test_walker_runs_all_steps_and_records_intents() -> None:
    # Executor stub
    executor = MagicMock()
    executor.goto = AsyncMock()
    executor.click = AsyncMock()
    executor.fill = AsyncMock()

    # Ledger stub
    ledger = MagicMock()
    ledger.observe_step = AsyncMock()
    ledger.record_intent = MagicMock()

    story = _Story(
        id="s1",
        persona="support_agent",
        steps=[
            {"action": "goto", "url": "/tickets", "expect": "queue page"},
            {"action": "click", "selector": "#new", "expect": "form opens"},
        ],
    )

    result: WalkResult = await walk_story(
        story=story, executor=executor, ledger=ledger
    )

    assert result.steps_executed == 2
    assert result.errors == []
    assert ledger.record_intent.call_count == 2
    assert ledger.observe_step.await_count == 2
    executor.goto.assert_awaited_once_with("/tickets")
    executor.click.assert_awaited_once_with("#new")


@pytest.mark.asyncio
async def test_walker_records_error_on_executor_failure() -> None:
    executor = MagicMock()
    executor.goto = AsyncMock(side_effect=RuntimeError("navigation failed"))

    ledger = MagicMock()
    ledger.observe_step = AsyncMock()
    ledger.record_intent = MagicMock()

    story = _Story(
        id="s1",
        persona="agent",
        steps=[{"action": "goto", "url": "/x", "expect": "page loads"}],
    )

    result = await walk_story(story=story, executor=executor, ledger=ledger)
    assert result.steps_executed == 1
    assert len(result.errors) == 1
    assert "navigation failed" in result.errors[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_walker.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement walker**

```python
# src/dazzle/fitness/walker.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class WalkResult:
    story_id: str
    persona: str
    steps_executed: int
    errors: list[str] = field(default_factory=list)


class _ExecutorLike(Protocol):
    async def goto(self, url: str) -> None: ...
    async def click(self, selector: str) -> None: ...
    async def fill(self, selector: str, value: str) -> None: ...


class _LedgerLike(Protocol):
    def record_intent(self, step: int, expect: str, action_desc: str) -> None: ...
    async def observe_step(self, step: int, observed_ui: str) -> None: ...


async def walk_story(
    story: Any, executor: _ExecutorLike, ledger: _LedgerLike
) -> WalkResult:
    """Drive the executor through a story's declared action steps.

    Each step has the shape:
        {"action": "goto|click|fill", "url|selector": ..., "expect": "...",
         "value": <only for fill>}

    The walker is deterministic — no LLM calls. It records intent (EXPECT +
    action description) against the ledger, runs the action, then records
    observation.
    """
    result = WalkResult(
        story_id=getattr(story, "id", "?"),
        persona=getattr(story, "persona", "?"),
        steps_executed=0,
    )

    for idx, step_def in enumerate(getattr(story, "steps", []), start=1):
        action = step_def.get("action", "").lower()
        expect = step_def.get("expect", f"step {idx} runs")
        action_desc = f"{action} {step_def}"

        ledger.record_intent(step=idx, expect=expect, action_desc=action_desc)
        result.steps_executed += 1

        try:
            if action == "goto":
                await executor.goto(step_def["url"])
            elif action == "click":
                await executor.click(step_def["selector"])
            elif action == "fill":
                await executor.fill(step_def["selector"], step_def["value"])
            else:
                raise ValueError(f"unknown action {action!r}")
            observed = f"{action} ok"
        except Exception as e:  # noqa: BLE001 — we want the error in the ledger
            observed = f"error: {e}"
            result.errors.append(f"step {idx}: {e}")

        await ledger.observe_step(step=idx, observed_ui=observed)

    return result
```

```python
# src/dazzle/fitness/missions/__init__.py
"""Mission builders for fitness passes."""
```

```python
# src/dazzle/fitness/missions/story_walk.py
"""Pass 1 mission builder — deterministic story walker.

Wraps `walker.walk_story` in a shape compatible with the existing
`DazzleAgent.Mission` protocol. Pass 1 is deterministic so the "agent" here
is a thin loop, not a reasoning model.
"""
from __future__ import annotations

from typing import Any

from dazzle.fitness.walker import walk_story, WalkResult


async def run_pass1_for_stories(
    stories: list[Any], executor: Any, ledger: Any
) -> list[WalkResult]:
    results: list[WalkResult] = []
    for s in stories:
        results.append(await walk_story(story=s, executor=executor, ledger=ledger))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_walker.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/walker.py src/dazzle/fitness/missions/__init__.py src/dazzle/fitness/missions/story_walk.py tests/unit/fitness/test_walker.py
git commit -m "feat(fitness): Pass 1 story walker (deterministic) (v1 task 12)"
```

---

## Task 13: proxy — Pass 2b agentic behavioural proxy

The proxy dispatches a `DazzleAgent` mission with EXPECT/ACTION/OBSERVE protocol. Every tool call goes through `interlocked_tool_call`. Uses the free-roam mission builder.

**Files:**
- Create: `src/dazzle/fitness/missions/free_roam.py`
- Create: `src/dazzle/fitness/proxy.py`
- Test: `tests/unit/fitness/test_proxy.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_proxy.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.proxy import run_proxy_mission


@pytest.mark.asyncio
async def test_proxy_builds_free_roam_mission_and_runs_agent() -> None:
    agent = MagicMock()
    agent.run = AsyncMock(return_value="transcript")

    ledger = MagicMock()
    ledger.current_step.return_value = None
    ledger.record_intent = MagicMock()

    persona = MagicMock(id="support_agent", name="support_agent")

    result = await run_proxy_mission(
        agent=agent,
        persona=persona,
        intent="triage the oldest open ticket",
        step_budget=20,
        ledger=ledger,
    )

    assert agent.run.await_count == 1
    mission_arg = agent.run.await_args.args[0]
    # Mission carries the intent, persona, step budget
    assert mission_arg.name.startswith("fitness.free_roam")
    assert hasattr(mission_arg, "system_prompt")
    assert "triage the oldest open ticket" in mission_arg.system_prompt
    assert result == "transcript"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_proxy.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement free_roam mission**

```python
# src/dazzle/fitness/missions/free_roam.py
"""Pass 2b mission builder — free-roam behavioural proxy.

Constructs a `Mission` object for the existing DazzleAgent framework that:

  1. Sets persona context on the system prompt
  2. Declares the intent as a high-level goal
  3. Embeds EXPECT/ACTION/OBSERVE protocol instructions
  4. Bounds the run via `step_budget`

Tool wiring lives in `proxy.py` because the interlock needs a reference to the
live ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Shaped to match DazzleAgent.Mission conventions. Task 0 discovery will have
# confirmed the exact field list; adjust here before merge if it diverges.
@dataclass
class FreeRoamMission:
    name: str
    system_prompt: str
    step_budget: int
    persona_id: str


_SYSTEM_PROMPT_TEMPLATE = """You are acting as a human proxy for the following \
persona: {persona_id}.

Your goal: {intent}

You must follow the EXPECT/ACTION/OBSERVE protocol strictly:

  1. Before EVERY tool call, state what you expect to happen in natural
     language. Keep it to one sentence. This is the `expect` field.
  2. Then call the tool.
  3. After the call, observe what actually happened. Compare to your
     expectation. If they differ, that is a signal worth recording.

The system will REJECT tool calls that are not preceded by an `expect`
statement. Do not try to work around this — emit the expectation first.

Step budget: {step_budget}. Use it efficiently.
"""


def build_free_roam_mission(
    persona: Any, intent: str, step_budget: int
) -> FreeRoamMission:
    persona_id = getattr(persona, "id", None) or getattr(persona, "name", "unknown")
    return FreeRoamMission(
        name=f"fitness.free_roam.{persona_id}",
        system_prompt=_SYSTEM_PROMPT_TEMPLATE.format(
            persona_id=persona_id, intent=intent, step_budget=step_budget
        ),
        step_budget=step_budget,
        persona_id=persona_id,
    )
```

- [ ] **Step 4: Implement proxy dispatcher**

```python
# src/dazzle/fitness/proxy.py
from __future__ import annotations

from typing import Any

from dazzle.fitness.missions.free_roam import build_free_roam_mission


async def run_proxy_mission(
    agent: Any,
    persona: Any,
    intent: str,
    step_budget: int,
    ledger: Any,
) -> Any:
    """Dispatch a Pass 2b behavioural proxy mission via DazzleAgent.

    The agent's existing tool layer must be wrapped in `interlocked_tool_call`
    at registration time (the engine wires this up when constructing the agent
    — see `engine.py`). This function only builds the mission and runs it.
    """
    mission = build_free_roam_mission(
        persona=persona, intent=intent, step_budget=step_budget
    )
    return await agent.run(mission)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_proxy.py -v`
Expected: test PASSES.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/fitness/proxy.py src/dazzle/fitness/missions/free_roam.py tests/unit/fitness/test_proxy.py
git commit -m "feat(fitness): Pass 2b proxy dispatcher (v1 task 13)"
```

---

## Task 14: extractor — transcripts → Findings with evidence_embedded

The extractor turns Pass 1/2b outputs into structured `Finding` records and embeds the ±3 transcript context into each.

**Files:**
- Create: `src/dazzle/fitness/extractor.py`
- Test: `tests/unit/fitness/test_extractor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_extractor.py
from datetime import datetime, timezone

from dazzle.fitness.extractor import extract_findings_from_diff
from dazzle.fitness.models import (
    FitnessDiff,
    LedgerStep,
    ProgressRecord,
    RowChange,
)


def _step(n: int, expect: str) -> LedgerStep:
    return LedgerStep(
        step_no=n,
        txn_id=None,
        expected=expect,
        action_summary=f"action {n}",
        observed_ui=f"ui {n}",
        observed_changes=[],
        delta={},
    )


def test_motion_without_progress_emits_lifecycle_finding() -> None:
    diff = FitnessDiff(
        run_id="r1",
        steps=[_step(1, "status advances")],
        created=[],
        updated=[
            RowChange(
                table="ticket",
                row_id="t1",
                kind="update",
                semantic_repr="Ticket(status=resolved)",
                field_deltas={"status": ("in_progress", "resolved")},
            )
        ],
        deleted=[],
        progress=[
            ProgressRecord(
                entity="Ticket",
                row_id="t1",
                transitions_observed=[("in_progress", "resolved")],
                evidence_satisfied=[False],
                ended_at_state="resolved",
                was_progress=False,
            )
        ],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r1",
        persona="support_agent",
        low_confidence=False,
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    lifecycle = [f for f in findings if f.locus == "lifecycle"]
    assert len(lifecycle) == 1
    assert lifecycle[0].axis == "conformance"
    assert lifecycle[0].severity == "high"
    assert "t1" in lifecycle[0].observed
    # Evidence is embedded for durability after ledger TTL
    assert lifecycle[0].evidence_embedded.diff_summary


def test_clean_run_emits_no_findings() -> None:
    diff = FitnessDiff(
        run_id="r",
        steps=[_step(1, "ok")],
        created=[],
        updated=[],
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r",
        persona="agent",
        low_confidence=False,
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert findings == []


def test_low_confidence_flag_propagates() -> None:
    diff = FitnessDiff(
        run_id="r",
        steps=[_step(1, "status advances")],
        created=[],
        updated=[
            RowChange(
                table="ticket",
                row_id="t1",
                kind="update",
                semantic_repr="",
                field_deltas={"status": ("in_progress", "resolved")},
            )
        ],
        deleted=[],
        progress=[
            ProgressRecord(
                entity="Ticket",
                row_id="t1",
                transitions_observed=[("in_progress", "resolved")],
                evidence_satisfied=[False],
                ended_at_state="resolved",
                was_progress=False,
            )
        ],
        semantic_repr_config={},
    )
    findings = extract_findings_from_diff(
        diff,
        run_id="r",
        persona="agent",
        low_confidence=True,
        now=datetime(2026, 4, 13, tzinfo=timezone.utc),
    )
    assert all(f.low_confidence for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_extractor.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement extractor**

```python
# src/dazzle/fitness/extractor.py
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from dazzle.fitness.models import (
    EvidenceEmbedded,
    Finding,
    FitnessDiff,
    LedgerStep,
    ProgressRecord,
)


def _context_window(
    steps: list[LedgerStep], center_step: int, radius: int = 3
) -> list[dict]:
    lo = max(0, center_step - radius - 1)
    hi = min(len(steps), center_step + radius)
    return [
        {
            "step_no": s.step_no,
            "expected": s.expected,
            "action": s.action_summary,
            "observed": s.observed_ui,
        }
        for s in steps[lo:hi]
    ]


def extract_findings_from_diff(
    diff: FitnessDiff,
    run_id: str,
    persona: str,
    low_confidence: bool,
    now: datetime,
) -> list[Finding]:
    findings: list[Finding] = []

    for progress in diff.progress:
        if progress.was_progress:
            continue

        evidence = EvidenceEmbedded(
            expected_ledger_step={
                "expect": diff.steps[-1].expected if diff.steps else "",
                "action": diff.steps[-1].action_summary if diff.steps else "",
                "observed": diff.steps[-1].observed_ui if diff.steps else "",
            },
            diff_summary=[
                rc for rc in diff.updated if rc.row_id == progress.row_id
            ][:3],
            transcript_excerpt=_context_window(
                diff.steps, len(diff.steps), radius=3
            ),
        )

        findings.append(
            Finding(
                id=f"FIND-{uuid4().hex[:8]}",
                created=now,
                run_id=run_id,
                cycle=None,
                axis="conformance",
                locus="lifecycle",
                severity="high",
                persona=persona,
                capability_ref=f"entity:{progress.entity}/{progress.row_id}",
                expected=(
                    f"{progress.entity} {progress.row_id} advances through "
                    f"its lifecycle with valid evidence"
                ),
                observed=(
                    f"{progress.entity} {progress.row_id} transitioned "
                    f"{progress.transitions_observed} but none satisfied the "
                    f"declared evidence predicate (motion without work)"
                ),
                evidence_embedded=evidence,
                disambiguation=False,
                low_confidence=low_confidence,
                status="PROPOSED",
                route="hard",
                fix_commit=None,
                alternative_fix=None,
            )
        )

    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_extractor.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/extractor.py tests/unit/fitness/test_extractor.py
git commit -m "feat(fitness): extractor — diffs to self-contained Findings (v1 task 14)"
```

---

## Task 15: backlog — fitness-backlog.md reader/writer

Durable findings. Markdown table format for git diff-friendliness; JSON blob per finding for the evidence envelope.

**Files:**
- Create: `src/dazzle/fitness/backlog.py`
- Test: `tests/unit/fitness/test_backlog.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_backlog.py
from datetime import datetime, timezone
from pathlib import Path

from dazzle.fitness.backlog import (
    read_backlog,
    upsert_findings,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _finding(id_: str, locus: str = "lifecycle") -> Finding:
    return Finding(
        id=id_,
        created=datetime(2026, 4, 13, tzinfo=timezone.utc),
        run_id="r1",
        cycle=None,
        axis="conformance",
        locus=locus,  # type: ignore[arg-type]
        severity="high",
        persona="support_agent",
        capability_ref="entity:Ticket/t1",
        expected="x",
        observed="y",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={},
            diff_summary=[],
            transcript_excerpt=[],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )


def test_upsert_creates_backlog_file(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(path, [_finding("FIND-001")])

    assert path.exists()
    text = path.read_text()
    assert "FIND-001" in text
    assert "lifecycle" in text


def test_upsert_is_idempotent_on_same_id(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(path, [_finding("FIND-002")])
    upsert_findings(path, [_finding("FIND-002")])

    rows = read_backlog(path)
    matching = [r for r in rows if r["id"] == "FIND-002"]
    assert len(matching) == 1


def test_read_backlog_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "fitness-backlog.md"
    upsert_findings(
        path, [_finding("FIND-003"), _finding("FIND-004", locus="spec_stale")]
    )
    rows = read_backlog(path)
    ids = {r["id"] for r in rows}
    assert ids == {"FIND-003", "FIND-004"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_backlog.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement backlog**

```python
# src/dazzle/fitness/backlog.py
from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from dazzle.fitness.models import Finding


_HEADER = """# Fitness Backlog

Structured findings from the Agent-Led Fitness Methodology. Each row is
self-contained via `evidence_embedded` — durable after the underlying ledger
has expired.

| id | created | locus | axis | severity | persona | status | route | summary |
|----|---------|-------|------|----------|---------|--------|-------|---------|
"""

_EVIDENCE_HEADER = "\n## Evidence envelopes\n\n"


_ROW_RE = re.compile(
    r"^\| (?P<id>FIND-\w+) \| (?P<created>[^|]+) \| (?P<locus>[^|]+) \|"
    r" (?P<axis>[^|]+) \| (?P<severity>[^|]+) \| (?P<persona>[^|]+) \|"
    r" (?P<status>[^|]+) \| (?P<route>[^|]+) \| (?P<summary>[^|]*) \|$"
)


def _finding_to_row(f: Finding) -> str:
    summary = f.observed.replace("\n", " ").replace("|", "/")[:120]
    return (
        f"| {f.id} | {f.created.isoformat()} | {f.locus} | {f.axis} |"
        f" {f.severity} | {f.persona} | {f.status} | {f.route} | {summary} |"
    )


def _finding_envelope(f: Finding) -> str:
    def _default(obj: object) -> object:
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"cannot serialise {type(obj)!r}")

    payload = json.dumps(asdict(f), default=_default, indent=2)
    return f"### {f.id}\n\n```json\n{payload}\n```\n"


def read_backlog(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text().splitlines():
        m = _ROW_RE.match(line.strip())
        if m:
            rows.append({k: v.strip() for k, v in m.groupdict().items()})
    return rows


def upsert_findings(path: Path, findings: list[Finding]) -> None:
    existing = read_backlog(path)
    existing_ids = {r["id"] for r in existing}

    to_add = [f for f in findings if f.id not in existing_ids]
    if not to_add and path.exists():
        return

    if not path.exists():
        path.write_text(_HEADER)

    text = path.read_text()
    # Split into table + envelope sections
    if _EVIDENCE_HEADER.strip() in text:
        table_part, envelope_part = text.split(_EVIDENCE_HEADER, 1)
        envelope_part = _EVIDENCE_HEADER + envelope_part
    else:
        table_part = text
        envelope_part = _EVIDENCE_HEADER

    for f in to_add:
        table_part = table_part.rstrip("\n") + "\n" + _finding_to_row(f) + "\n"
        envelope_part = envelope_part.rstrip("\n") + "\n\n" + _finding_envelope(f)

    path.write_text(table_part + "\n" + envelope_part.lstrip("\n"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_backlog.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/backlog.py tests/unit/fitness/test_backlog.py
git commit -m "feat(fitness): backlog reader/writer (v1 task 15)"
```

---

## Task 16: comparator — regression detection

Compares `FitnessDiff_n` against `FitnessDiff_{n-1}` and emits a regression report.

**Files:**
- Create: `src/dazzle/fitness/comparator.py`
- Test: `tests/unit/fitness/test_comparator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_comparator.py
from datetime import datetime, timezone

from dazzle.fitness.comparator import RegressionReport, compare_cycles
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _finding(id_: str) -> Finding:
    return Finding(
        id=id_,
        created=datetime(2026, 4, 13, tzinfo=timezone.utc),
        run_id="r",
        cycle=None,
        axis="conformance",
        locus="lifecycle",
        severity="high",
        persona="agent",
        capability_ref=f"cap:{id_}",
        expected="x",
        observed="y",
        evidence_embedded=EvidenceEmbedded({}, [], []),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="hard",
        fix_commit=None,
        alternative_fix=None,
    )


def test_new_findings_after_hard_correction_is_regression() -> None:
    previous = [_finding("FIND-001")]
    current = [_finding("FIND-002")]  # different finding appeared
    report: RegressionReport = compare_cycles(
        previous=previous,
        current=current,
        previous_had_hard_correction=True,
    )
    assert report.regression_detected is True
    assert len(report.new_findings) == 1
    assert len(report.fixed_findings) == 1


def test_same_findings_no_regression() -> None:
    f = [_finding("FIND-001")]
    report = compare_cycles(
        previous=f, current=f, previous_had_hard_correction=True
    )
    assert report.regression_detected is False
    assert len(report.persistent_findings) == 1


def test_finding_cleared_with_no_new_findings() -> None:
    previous = [_finding("FIND-001")]
    current: list[Finding] = []
    report = compare_cycles(
        previous=previous, current=current, previous_had_hard_correction=True
    )
    assert report.regression_detected is False
    assert len(report.fixed_findings) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_comparator.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement comparator**

```python
# src/dazzle/fitness/comparator.py
from __future__ import annotations

from dataclasses import dataclass

from dazzle.fitness.models import Finding


@dataclass(frozen=True)
class RegressionReport:
    new_findings: list[Finding]
    fixed_findings: list[Finding]
    persistent_findings: list[Finding]
    regression_detected: bool


def _key(f: Finding) -> tuple:
    # Content-identity: capability_ref + expected + persona uniquely names
    # a finding even across run_ids.
    return (f.capability_ref, f.expected, f.persona, f.locus)


def compare_cycles(
    previous: list[Finding],
    current: list[Finding],
    previous_had_hard_correction: bool,
) -> RegressionReport:
    prev_map = {_key(f): f for f in previous}
    curr_map = {_key(f): f for f in current}

    new_keys = set(curr_map) - set(prev_map)
    fixed_keys = set(prev_map) - set(curr_map)
    persistent_keys = set(prev_map) & set(curr_map)

    new_findings = [curr_map[k] for k in new_keys]
    fixed_findings = [prev_map[k] for k in fixed_keys]
    persistent_findings = [curr_map[k] for k in persistent_keys]

    regression = bool(new_findings) and previous_had_hard_correction

    return RegressionReport(
        new_findings=new_findings,
        fixed_findings=fixed_findings,
        persistent_findings=persistent_findings,
        regression_detected=regression,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_comparator.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/comparator.py tests/unit/fitness/test_comparator.py
git commit -m "feat(fitness): regression comparator (v1 task 16)"
```

---

## Task 17: corrector — two-gate routing + alternative-generation

Routes findings via two gates (low_confidence / maturity / mechanical disambiguation). Generates a primary fix and an alternative; materially-different alternatives flag disambiguation.

**Files:**
- Create: `src/dazzle/fitness/corrector.py`
- Test: `tests/unit/fitness/test_corrector.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_corrector.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from dazzle.fitness.corrector import (
    Fix,
    materially_same,
    route_finding,
    generate_fix,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding


def _finding(**overrides) -> Finding:
    base = {
        "id": "F1",
        "created": datetime(2026, 4, 13, tzinfo=timezone.utc),
        "run_id": "r",
        "cycle": None,
        "axis": "conformance",
        "locus": "lifecycle",
        "severity": "high",
        "persona": "a",
        "capability_ref": "c",
        "expected": "x",
        "observed": "y",
        "evidence_embedded": EvidenceEmbedded({}, [], []),
        "disambiguation": False,
        "low_confidence": False,
        "status": "PROPOSED",
        "route": "hard",
        "fix_commit": None,
        "alternative_fix": None,
    }
    base.update(overrides)
    return Finding(**base)


def test_low_confidence_always_goes_soft() -> None:
    f = _finding(low_confidence=True)
    assert route_finding(f, maturity="mvp") == "soft"


def test_stable_maturity_always_goes_soft() -> None:
    f = _finding()
    assert route_finding(f, maturity="stable") == "soft"


def test_disambiguation_goes_soft() -> None:
    f = _finding(disambiguation=True)
    assert route_finding(f, maturity="mvp") == "soft"


def test_mvp_clean_finding_goes_hard() -> None:
    f = _finding()
    assert route_finding(f, maturity="mvp") == "hard"


def test_spec_stale_goes_soft_regardless() -> None:
    f = _finding(locus="spec_stale")
    assert route_finding(f, maturity="mvp") == "soft"


def test_materially_same_identical_fixes() -> None:
    a = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x\n-y\n")
    b = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x\n-y\n")
    assert materially_same(a, b) is True


def test_materially_same_different_files() -> None:
    a = Fix(touched_files=["src/a.py"], summary="refactor", diff="+x")
    b = Fix(touched_files=["src/b.py"], summary="refactor", diff="+x")
    assert materially_same(a, b) is False


@pytest.mark.asyncio
async def test_generate_fix_flags_disambiguation_when_alternatives_diverge() -> None:
    fake_llm = AsyncMock()
    fake_llm.ask.side_effect = [
        '{"touched_files": ["src/a.py"], "summary": "fix route", "diff": "+a"}',
        '{"touched_files": ["src/b.py"], "summary": "fix template", "diff": "+b"}',
    ]
    f = _finding()
    primary, alternative, updated = await generate_fix(f, llm=fake_llm)

    assert primary.touched_files == ["src/a.py"]
    assert alternative is not None
    assert alternative.touched_files == ["src/b.py"]
    assert updated.disambiguation is True
    assert updated.alternative_fix is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_corrector.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement corrector**

```python
# src/dazzle/fitness/corrector.py
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from dazzle.fitness.models import Finding


Route = Literal["hard", "soft"]


@dataclass(frozen=True)
class Fix:
    touched_files: list[str]
    summary: str
    diff: str


class _LlmLike(Protocol):
    async def ask(self, prompt: str, **kwargs: Any) -> str: ...


def route_finding(
    finding: Finding, maturity: Literal["mvp", "beta", "stable"]
) -> Route:
    # Gate 0: low confidence always soft
    if finding.low_confidence:
        return "soft"

    # spec_stale is always paraphrased, never auto-corrected
    if finding.locus == "spec_stale":
        return "soft"

    # Gate 1: maturity kill-switch
    if maturity == "stable":
        return "soft"

    # Gate 2: mechanical disambiguation
    if finding.disambiguation:
        return "soft"

    return "hard"


def materially_same(a: Fix, b: Fix) -> bool:
    """Two fixes are 'materially same' if they touch the same files and
    produce equivalent diffs. Alternative semantic checks can be added in v1.1
    but this is sufficient for v1's disambiguation-flagging needs."""
    return (
        sorted(a.touched_files) == sorted(b.touched_files)
        and a.diff.strip() == b.diff.strip()
    )


_FIX_PROMPT = """You are the corrector. A fitness finding is presented below.

Generate a {variant} code fix for this finding. Return ONLY a JSON object:
  {{"touched_files": ["path/..."], "summary": "...", "diff": "unified diff"}}

Finding:
---
id: {id}
locus: {locus}
axis: {axis}
expected: {expected}
observed: {observed}
---
"""


async def _generate_one(finding: Finding, variant: str, llm: _LlmLike) -> Fix | None:
    prompt = _FIX_PROMPT.format(
        variant=variant,
        id=finding.id,
        locus=finding.locus,
        axis=finding.axis,
        expected=finding.expected,
        observed=finding.observed,
    )
    response = await llm.ask(prompt)
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return Fix(
        touched_files=list(data.get("touched_files", [])),
        summary=str(data.get("summary", "")),
        diff=str(data.get("diff", "")),
    )


async def generate_fix(
    finding: Finding, llm: _LlmLike
) -> tuple[Fix | None, Fix | None, Finding]:
    """Generate a primary fix and an alternative.

    The alternative's existence (when materially different) mechanically flags
    the finding as disambiguation-required. The corrector does NOT rely on
    self-reported uncertainty.
    """
    primary = await _generate_one(finding, variant="best", llm=llm)
    alternative = await _generate_one(
        finding, variant="different_approach", llm=llm
    )

    updated = finding
    if primary is not None and alternative is not None:
        if not materially_same(primary, alternative):
            updated = replace(
                finding,
                disambiguation=True,
                alternative_fix=alternative.summary,
            )

    return primary, alternative, updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_corrector.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/corrector.py tests/unit/fitness/test_corrector.py
git commit -m "feat(fitness): two-gate corrector with alt-generation (v1 task 17)"
```

---

## Task 18: paraphrase — skeleton for v1

v1 ships the interface only; UX wiring lands in v1.1. This keeps `spec_stale` routing wired without blocking on the full paraphrase loop.

**Files:**
- Create: `src/dazzle/fitness/paraphrase.py`
- Test: `tests/unit/fitness/test_paraphrase.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_paraphrase.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.paraphrase import (
    ParaphraseRequest,
    build_spec_revision_prompt,
    paraphrase_story,
)


def _finding(locus: str) -> Finding:
    return Finding(
        id="F",
        created=datetime(2026, 4, 13, tzinfo=timezone.utc),
        run_id="r",
        cycle=None,
        axis="coverage",
        locus=locus,  # type: ignore[arg-type]
        severity="low",
        persona="agent",
        capability_ref="story:export_csv",
        expected="Spec clause for export_csv",
        observed="No matching spec clause",
        evidence_embedded=EvidenceEmbedded({}, [], []),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def test_build_spec_revision_prompt_contains_finding_details() -> None:
    f = _finding(locus="spec_stale")
    request: ParaphraseRequest = build_spec_revision_prompt(f)
    assert "export_csv" in request.prompt
    assert request.kind == "spec_revision"
    assert request.target_finding_id == "F"


@pytest.mark.asyncio
async def test_paraphrase_story_returns_plain_english_summary() -> None:
    fake_llm = AsyncMock()
    fake_llm.ask.return_value = "When a customer emails, you want to triage quickly."

    class _Story:
        id = "s1"
        title = "triage_ticket"
        steps = ["open queue", "click triage"]

    summary = await paraphrase_story(_Story(), llm=fake_llm)
    assert "triage" in summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_paraphrase.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement paraphrase skeleton**

```python
# src/dazzle/fitness/paraphrase.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from dazzle.fitness.models import Finding


ParaphraseKind = Literal["story_review", "spec_revision"]


@dataclass(frozen=True)
class ParaphraseRequest:
    kind: ParaphraseKind
    prompt: str
    target_finding_id: str | None


class _LlmLike(Protocol):
    async def ask(self, prompt: str, **kwargs: Any) -> str: ...


def build_spec_revision_prompt(finding: Finding) -> ParaphraseRequest:
    """Build a Recognition-not-Generation prompt for a spec_stale finding.

    v1 ships this helper so the corrector's `spec_stale` route can call into
    the paraphrase subsystem. The full founder-facing UX ships in v1.1.
    """
    prompt = (
        "Based on how the app is being used, it looks like you actually want:\n\n"
        f"  {finding.capability_ref}\n\n"
        f"Your spec currently implies: {finding.expected}\n\n"
        "Should the spec be updated to reflect the observed behaviour? "
        "Answer with 'confirm', 'reject', or a one-line correction."
    )
    return ParaphraseRequest(
        kind="spec_revision",
        prompt=prompt,
        target_finding_id=finding.id,
    )


async def paraphrase_story(story: Any, llm: _LlmLike) -> str:
    """Generate a plain-English paraphrase of a DSL story for founder review."""
    title = getattr(story, "title", "(untitled)")
    steps = getattr(story, "steps", [])
    steps_str = "\n".join(f"  - {s}" for s in steps)

    prompt = (
        "Paraphrase this user story in plain English, using NO technical or "
        "framework vocabulary. Start with 'When...' or 'You want to...'.\n\n"
        f"Story: {title}\n"
        f"Steps:\n{steps_str}\n"
    )
    return await llm.ask(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_paraphrase.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/paraphrase.py tests/unit/fitness/test_paraphrase.py
git commit -m "feat(fitness): paraphrase skeleton (spec_revision + story review) (v1 task 18)"
```

---

## Task 19: engine — orchestrator

The engine composes all the pieces. This is the integration point and the only module that touches every other module.

**Files:**
- Create: `src/dazzle/fitness/engine.py`
- Test: `tests/unit/fitness/test_engine.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_engine.py
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.engine import FitnessEngine, FitnessRunResult


@pytest.mark.asyncio
async def test_engine_runs_pass1_when_budget_available(tmp_path: Path) -> None:
    # Wire up minimal fakes for every dependency
    spec_md = tmp_path / "spec.md"
    spec_md.write_text("# App\n\nTriage tickets.\n")

    fake_app = MagicMock()
    fake_app.stories = [
        MagicMock(id="s1", persona="agent", title="triage", steps=[])
    ]
    fake_app.entities = []

    fake_llm = AsyncMock()
    fake_llm.ask.side_effect = [
        '[{"capability":"triage","persona":"agent"}]',  # spec_extractor
        '[{"capability":"triage","persona":"agent"}]',  # adversary
    ]

    fake_agent = MagicMock()
    fake_agent.run = AsyncMock(return_value="transcript")

    fake_executor = MagicMock()
    fake_executor.goto = AsyncMock()
    fake_executor.click = AsyncMock()
    fake_executor.fill = AsyncMock()

    fake_pool = MagicMock()
    fake_pool.fetch = AsyncMock(return_value=[])

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(),
        app_spec=fake_app,
        spec_md_path=spec_md,
        agent=fake_agent,
        executor=fake_executor,
        db_pool=fake_pool,
        llm=fake_llm,
    )

    result: FitnessRunResult = await engine.run()

    assert result.pass1_run_count >= 1
    assert result.findings is not None
    assert "run_id" in result.run_metadata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_engine.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement engine**

```python
# src/dazzle/fitness/engine.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dazzle.fitness.adversary import synthesize_from_stories
from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.budget import BudgetController, CycleProfile
from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.cross_check import cross_check_capabilities
from dazzle.fitness.extractor import extract_findings_from_diff
from dazzle.fitness.independence import measure_independence
from dazzle.fitness.ledger_snapshot import SnapshotLedger
from dazzle.fitness.maturity import read_maturity
from dazzle.fitness.models import Finding
from dazzle.fitness.progress_evaluator import evaluate_progress
from dazzle.fitness.proxy import run_proxy_mission
from dazzle.fitness.spec_extractor import extract_spec_capabilities
from dazzle.fitness.walker import walk_story


@dataclass
class FitnessRunResult:
    pass1_run_count: int
    findings: list[Finding]
    profile: CycleProfile
    independence_jaccard: float
    run_metadata: dict[str, Any] = field(default_factory=dict)


class FitnessEngine:
    def __init__(
        self,
        project_root: Path,
        config: FitnessConfig,
        app_spec: Any,
        spec_md_path: Path,
        agent: Any,
        executor: Any,
        db_pool: Any,
        llm: Any,
    ) -> None:
        self._project_root = project_root
        self._config = config
        self._app = app_spec
        self._spec_path = spec_md_path
        self._agent = agent
        self._executor = executor
        self._pool = db_pool
        self._llm = llm

    async def run(self) -> FitnessRunResult:
        run_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)
        maturity = read_maturity(self._project_root)

        profile = BudgetController(self._config).plan(
            available_tokens=self._config.max_tokens_per_cycle
        )

        repr_map = self._collect_repr_fields()
        ledger = SnapshotLedger(pool=self._pool, repr_fields=repr_map)
        ledger.open(run_id)

        # Pass 1: deterministic story walks
        pass1_results: list[Any] = []
        if profile.run_pass1:
            for story in getattr(self._app, "stories", []):
                result = await walk_story(
                    story=story, executor=self._executor, ledger=ledger
                )
                pass1_results.append(result)

        # Pass 2a sub-steps
        findings: list[Finding] = []
        jaccard = 0.0

        if profile.run_pass2a:
            spec_caps = await extract_spec_capabilities(
                self._spec_path, llm=self._llm
            )
            story_caps = (
                await synthesize_from_stories(
                    getattr(self._app, "stories", []), llm=self._llm
                )
                if profile.adversary_enabled
                else []
            )
            indep_report = measure_independence(
                spec_caps, story_caps,
                threshold=self._config.independence_threshold_jaccard,
            )
            jaccard = indep_report.jaccard
            low_conf = indep_report.degraded or profile.degraded

            findings.extend(
                cross_check_capabilities(
                    spec_capabilities=spec_caps,
                    stories=getattr(self._app, "stories", []),
                    run_id=run_id,
                    now=now,
                )
            )

            # Progress evaluation from lifecycle declarations
            diff = ledger.summarize()
            for entity in getattr(self._app, "entities", []):
                lifecycle = getattr(entity, "lifecycle", None)
                if lifecycle is None:
                    continue
                progress_records = evaluate_progress(
                    lifecycle, diff, entity_state={}  # v1 — empty; v1.1 hydrates from pool
                )
                # Replace progress on the diff by re-creating it
                from dataclasses import replace as _replace
                diff = _replace(diff, progress=diff.progress + progress_records)

            findings.extend(
                extract_findings_from_diff(
                    diff,
                    run_id=run_id,
                    persona="fitness_proxy",
                    low_confidence=low_conf,
                    now=now,
                )
            )

        # Pass 2b: free-roam proxy
        if profile.run_pass2b:
            for persona in getattr(self._app, "personas", [])[:1]:
                await run_proxy_mission(
                    agent=self._agent,
                    persona=persona,
                    intent="exercise the app as this persona would",
                    step_budget=profile.pass2b_step_budget,
                    ledger=ledger,
                )

        ledger.close()

        # Persist findings
        backlog_path = self._project_root / "dev_docs" / "fitness-backlog.md"
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        upsert_findings(backlog_path, findings)

        return FitnessRunResult(
            pass1_run_count=len(pass1_results),
            findings=findings,
            profile=profile,
            independence_jaccard=jaccard,
            run_metadata={
                "run_id": run_id,
                "maturity": maturity,
                "cycle_at": now.isoformat(),
            },
        )

    def _collect_repr_fields(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for entity in getattr(self._app, "entities", []):
            fitness = getattr(entity, "fitness", None)
            if fitness is not None and fitness.repr_fields:
                out[entity.name.lower()] = list(fitness.repr_fields)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_engine.py -v`
Expected: test PASSES.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/engine.py tests/unit/fitness/test_engine.py
git commit -m "feat(fitness): engine orchestrator (v1 task 19)"
```

---

## Task 20: /ux-cycle Strategy.FITNESS integration

Wires the fitness engine into `/ux-cycle` as a new rotating strategy.

**Files:**
- Create: `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py`
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/__init__.py` (or wherever `Strategy` enum lives)
- Test: `tests/unit/fitness/test_fitness_strategy_integration.py`

- [ ] **Step 1: Discovery — locate Strategy enum**

Run: `grep -rn "class Strategy\|Strategy\." src/dazzle/cli/runtime_impl/ 2>/dev/null | head`
Expected: finds the ux-cycle Strategy enum (MISSING_CONTRACTS, EDGE_CASES, etc.).
Record: exact path and enum name.

- [ ] **Step 2: Write failing test**

```python
# tests/unit/fitness/test_fitness_strategy_integration.py
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_fitness_strategy_calls_engine_run(tmp_path: Path) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.4,
            run_metadata={"run_id": "r1"},
        )
    )

    with patch(
        "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
        return_value=fake_engine,
    ):
        outcome = await run_fitness_strategy(
            example_app="support_tickets", project_root=tmp_path
        )

    assert fake_engine.run.await_count == 1
    assert "r1" in outcome.summary
```

- [ ] **Step 3: Implement fitness strategy**

```python
# src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py
"""/ux-cycle Strategy.FITNESS wiring.

Invoked by the top-level ux_cycle runner when it rotates to FITNESS. Owns
example-app lifecycle (starts runtime, runs the engine, tears down) and
aggregates the result into a /ux-cycle outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StrategyOutcome:
    strategy: str
    summary: str
    degraded: bool
    findings_count: int


async def run_fitness_strategy(
    example_app: str, project_root: Path
) -> StrategyOutcome:
    engine = _build_engine(example_app=example_app, project_root=project_root)
    result = await engine.run()
    summary = (
        f"fitness run {result.run_metadata.get('run_id')}: "
        f"{len(result.findings)} findings, "
        f"independence={result.independence_jaccard:.3f}"
    )
    return StrategyOutcome(
        strategy="FITNESS",
        summary=summary,
        degraded=result.profile.degraded,
        findings_count=len(result.findings),
    )


def _build_engine(example_app: str, project_root: Path) -> Any:
    """Construct a FitnessEngine for the given example app.

    This is a factory function so tests can patch it cleanly. The real
    implementation needs Task 0 discovery notes to wire up asyncpg pool,
    DazzleAgent, PlaywrightExecutor, and the LLM facade from the example's
    RuntimeServices.
    """
    from dazzle.fitness.config import FitnessConfig
    from dazzle.fitness.engine import FitnessEngine
    # TODO(v1 integration): wire real dependencies using discovery findings
    raise NotImplementedError(
        "fitness_strategy._build_engine: wire RuntimeServices + DazzleAgent "
        "after Task 0 discovery of engine dependencies"
    )
```

- [ ] **Step 4: Wire Strategy enum value**

Modify the Strategy enum (location from step 1 discovery). Add `FITNESS = "fitness"` entry and register the new strategy in whatever dispatch table routes the enum value to a runner.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_fitness_strategy_integration.py -v`
Expected: test PASSES.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py src/dazzle/cli/runtime_impl/ux_cycle_impl/__init__.py tests/unit/fitness/test_fitness_strategy_integration.py
git commit -m "feat(ux-cycle): Strategy.FITNESS integration (v1 task 20)"
```

---

## Task 21: Wire fitness log append

Every cycle appends a line to `dev_docs/fitness-log.md`: timestamp, run_id, independence metric, findings count, degraded flag.

**Files:**
- Modify: `src/dazzle/fitness/engine.py` (add log append at end of `run`)
- Test: `tests/unit/fitness/test_engine_log.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/fitness/test_engine_log.py
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.engine import FitnessEngine


@pytest.mark.asyncio
async def test_engine_appends_log_line(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("app")

    fake_app = MagicMock(stories=[], entities=[], personas=[])
    fake_llm = AsyncMock()
    fake_llm.ask.return_value = "[]"
    fake_pool = MagicMock()
    fake_pool.fetch = AsyncMock(return_value=[])
    fake_agent = MagicMock()
    fake_agent.run = AsyncMock()
    fake_executor = MagicMock()

    engine = FitnessEngine(
        project_root=tmp_path,
        config=FitnessConfig(),
        app_spec=fake_app,
        spec_md_path=spec,
        agent=fake_agent,
        executor=fake_executor,
        db_pool=fake_pool,
        llm=fake_llm,
    )
    await engine.run()

    log_path = tmp_path / "dev_docs" / "fitness-log.md"
    assert log_path.exists()
    text = log_path.read_text()
    assert "jaccard" in text.lower() or "independence" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/fitness/test_engine_log.py -v`
Expected: FAIL — engine does not currently write the log.

- [ ] **Step 3: Add log append to engine**

Edit `src/dazzle/fitness/engine.py`. Near the end of `run()`, before `return FitnessRunResult(...)`:

```python
log_path = self._project_root / "dev_docs" / "fitness-log.md"
log_path.parent.mkdir(parents=True, exist_ok=True)
if not log_path.exists():
    log_path.write_text("# Fitness Log\n\n")
line = (
    f"- {now.isoformat()} run={run_id} "
    f"independence_jaccard={jaccard:.3f} "
    f"findings={len(findings)} "
    f"degraded={profile.degraded}\n"
)
with log_path.open("a") as f:
    f.write(line)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/fitness/test_engine_log.py tests/unit/fitness/test_engine.py -v`
Expected: both tests PASS (including the earlier engine test).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/fitness/engine.py tests/unit/fitness/test_engine_log.py
git commit -m "feat(fitness): append per-run log line with independence metric (v1 task 21)"
```

---

## Task 22: E2E test against support_tickets

Exercises the full engine against a running `support_tickets` example app. This is the v1 success-criteria proof.

**Files:**
- Create: `tests/e2e/fitness/__init__.py`
- Create: `tests/e2e/fitness/test_support_tickets_fitness.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/e2e/fitness/test_support_tickets_fitness.py
"""E2E: fitness engine runs against support_tickets example app.

Preconditions:
  1. `support_tickets` example has lifecycle ADR applied (Ticket entity with
     status lifecycle + fitness.repr_fields).
  2. Dazzle runtime is available.

This test is slow (spins up runtime, runs full engine). It is marked `e2e`
and skipped in the default `pytest tests/ -m "not e2e"` run.
"""
import pytest
from pathlib import Path


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_support_tickets_fitness_cycle_completes() -> None:
    # Construct real engine dependencies via RuntimeServices.
    # The engine must:
    #  - Run at least one Pass 1 story walk (support_tickets has several)
    #  - Produce a FitnessDiff whose row counts are non-negative
    #  - Emit at least zero findings (may be zero on a perfectly-spec'd app)
    #  - Write fitness-backlog.md and fitness-log.md to the project dev_docs/
    #  - Complete in under 10 minutes
    from dazzle.fitness.engine import FitnessEngine
    from dazzle.fitness.config import FitnessConfig

    example_root = Path(__file__).parents[3] / "examples" / "support_tickets"

    # Skeleton wiring — Task 0 discovery determines the real RuntimeServices
    # call. The implementing agent must fill this in based on what exists in
    # the codebase, following the same pattern used by `dazzle ux verify`.
    pytest.skip("E2E wiring pending — requires RuntimeServices handle from Task 0")


@pytest.mark.asyncio
async def test_support_tickets_induced_regression_is_caught() -> None:
    """Self-validation: an intentionally broken correction must be caught
    by the regression comparator on the next cycle.

    v1 success criterion #5: at least one intentionally-buggy correction
    is caught by the regression comparator.
    """
    pytest.skip("E2E self-validation pending — requires full engine wiring")
```

- [ ] **Step 2: Verify E2E test is discoverable**

Run: `pytest tests/e2e/fitness/ --collect-only -q`
Expected: 2 tests collected, both marked `e2e`.

- [ ] **Step 3: Verify skipped in default run**

Run: `pytest tests/e2e/fitness/ -m "not e2e" --collect-only -q`
Expected: 0 tests collected.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/fitness/__init__.py tests/e2e/fitness/test_support_tickets_fitness.py
git commit -m "test(fitness): E2E test harness against support_tickets (v1 task 22)"
```

Note: the two E2E tests are marked `pytest.skip(...)` with an explicit reason. The subagent-driven workflow will unblock them as part of the final integration task (Task 24) once real `RuntimeServices` wiring is in place.

---

## Task 23: User-facing reference docs + CHANGELOG

Documentation for the `docs/reference/` tree and the CHANGELOG entry.

**Files:**
- Create: `docs/reference/fitness-methodology.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the reference doc**

```markdown
# Fitness Methodology

The **Agent-Led Fitness Methodology** is an optional V&V loop that checks
whether your Dazzle app is *fit for the purpose described by your `spec.md`*.

It differs from `dazzle ux verify --contracts` in that it asks semantic
questions — does this persona actually make progress through their lifecycles?
does the DSL cover everything the spec implies? — rather than mechanical ones.

## When to use

- Run on every CI cycle if your project's `[dazzle.maturity].level` is `mvp`
- Run on every PR if your project's maturity is `beta`
- Run weekly (soft mode only) if your project's maturity is `stable`

## Running

```bash
# Full cycle
dazzle fitness run

# Just findings
dazzle fitness findings

# Story paraphrase-confirm loop
dazzle fitness confirm-stories
```

MCP users:

```
mcp__dazzle__fitness.run()
mcp__dazzle__fitness.findings(axis=conformance)
```

## Configuration

Add to `pyproject.toml`:

```toml
[dazzle.maturity]
level = "mvp"          # or "beta" / "stable"

[dazzle.fitness]
max_tokens_per_cycle = 100000
independence_threshold_jaccard = 0.85

[dazzle.fitness.independence_mechanism]
primary = "prompt_plus_model_family"
```

## Required DSL additions

Every entity participating in fitness must declare `fitness.repr_fields`:

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[new, in_progress, resolved] required
  assignee_id: ref User

  fitness:
    repr_fields: [title, status, assignee_id]
```

v1 emits a non-fatal lint warning if this is missing. v1.1 makes it fatal.

Entities with lifecycles must also declare a `lifecycle:` block (see
[ADR-0020](../adr/ADR-0020-lifecycle-evidence-predicates.md)).

## Findings

Findings live in `dev_docs/fitness-backlog.md`. Each row has:

- `axis`: coverage vs conformance
- `locus`: implementation | story_drift | spec_stale | lifecycle
- `severity`, `persona`, `capability_ref`
- `evidence_embedded`: self-contained evidence envelope, durable after the
  underlying ledger has expired

## Three corners

The methodology triangulates across three independent sensors:

1. `spec.md` — your natural-language oracle
2. DSL stories — /bootstrap's interpretation of your intent
3. Running app — what the code actually does

Each cycle measures `independence_jaccard` between corners 1 and 2 to verify
the sensors haven't collapsed into a single (correlated) signal. When they do,
all findings from that cycle are marked `low_confidence=true` and cannot
auto-correct.

## Further reading

- Design spec: `docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md`
- Lifecycle prerequisite: ADR-0020
```

- [ ] **Step 2: Update CHANGELOG**

Edit `CHANGELOG.md`. Under `## [Unreleased]` → `### Added`:

```markdown
- **Agent-Led Fitness Methodology (v1)** — new subsystem at `src/dazzle/fitness/`.
  Continuous V&V loop triangulating `spec.md`, DSL stories, and the running
  app. Ships Pass 1 (story walker), Pass 2a (spec cross-check with structural
  independence), Pass 2b (behavioural proxy with EXPECT/ACTION/OBSERVE hard
  interlock), snapshot-based FitnessLedger, regression comparator, and
  two-gate corrector with alternative-generation disambiguation. See
  `docs/reference/fitness-methodology.md`.
- **DSL:** new `fitness.repr_fields` block on entities — required for entities
  that participate in fitness evaluation. v1 emits a non-fatal lint warning
  when missing; v1.1 will make this fatal.
- **/ux-cycle:** new `Strategy.FITNESS` — rotates alongside MISSING_CONTRACTS
  and EDGE_CASES.

### Agent Guidance

- **Fitness prerequisite:** entities participating in fitness must declare
  both `fitness.repr_fields` (this release) and a `lifecycle:` block
  (ADR-0020). Check the lint output — missing declarations will silently
  skip the entity from fitness evaluation in v1 and error in v1.1.
- **Fitness findings routing:** never auto-correct findings with
  `low_confidence=true`. They go to soft mode (PR queue) regardless of
  maturity level. See `src/dazzle/fitness/corrector.py:route_finding`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/reference/fitness-methodology.md CHANGELOG.md
git commit -m "docs(fitness): user reference + CHANGELOG entry (v1 task 23)"
```

---

## Task 24: Final integration check

Run the full quality-gate suite. Every module should pass lint, types, unit tests, and the E2E test should collect.

- [ ] **Step 1: Lint everything**

Run: `ruff check src/dazzle/fitness/ tests/unit/fitness/ tests/e2e/fitness/ --fix && ruff format src/dazzle/fitness/ tests/unit/fitness/ tests/e2e/fitness/`
Expected: no remaining errors after auto-fix.

- [ ] **Step 2: Type-check the new subsystem**

Run: `mypy src/dazzle/fitness/ --ignore-missing-imports`
Expected: no type errors.

- [ ] **Step 3: Run the full unit test suite**

Run: `pytest tests/unit/fitness/ -v`
Expected: every test added across tasks 1-21 PASSES. Count should match the sum from each task.

- [ ] **Step 4: Validate existing test suite still passes**

Run: `pytest tests/ -m "not e2e" -x`
Expected: all existing tests continue to pass. If any test broke, investigate whether the break was caused by the parser change in Task 2 (entity `fitness:` block) or by the lint rule addition. Fix the regression before proceeding.

- [ ] **Step 5: Validate every example app still parses**

Run: `for ex in examples/*/; do echo "--- $ex"; (cd "$ex" && dazzle validate) || echo "FAIL: $ex"; done`
Expected: every example app passes `dazzle validate`. The new `fitness.repr_fields_missing` rule is a warning, not an error, so existing examples should still validate successfully (possibly with warnings).

- [ ] **Step 6: Verify E2E test collection**

Run: `pytest tests/e2e/fitness/ --collect-only`
Expected: 2 tests collected, both skipped with "E2E wiring pending" reason. This is expected — full E2E wiring ships as part of v1.0.1 after Task 0 discovery validates the real RuntimeServices handle.

- [ ] **Step 7: Verify CHANGELOG and CLAUDE.md consistency**

Read: `CHANGELOG.md` — verify the fitness entry is under `## [Unreleased]`.
Read: `.claude/CLAUDE.md` — the Architecture table may need a new row for `src/dazzle/fitness/`. Add one if it fits the existing pattern.

- [ ] **Step 8: Final commit**

If any lint/type fixes were applied in steps 1-2, or CLAUDE.md was updated in step 7:

```bash
git add -u
git commit -m "chore(fitness): v1 final integration — lint + types + docs"
```

- [ ] **Step 9: Push and verify CI**

```bash
git push
```

Monitor CI via `gh run list --branch main --limit 3`. All jobs must pass. If any job fails, diagnose:
- `lint` or `type-check` failure in `src/dazzle/fitness/` → fix in place
- `python-tests` failure in `tests/unit/fitness/` → re-read the failing test, fix the offending module
- `python-tests` failure elsewhere → the parser/validator change from Task 2 may have unintended side effects; investigate

Do NOT merge until CI is green.

---

## Self-Review

After writing the complete plan above, a final check:

**1. Spec coverage** — spot-check against the spec's v1 bullet list (§14):

| Spec bullet | Covered by task |
|---|---|
| FitnessLedger v1 snapshot | Task 4 |
| Pass 1 walker | Task 12 |
| Pass 2a three sub-steps | Tasks 8, 11, 9 |
| independence.py metric | Task 10 |
| Pass 2b proxy + hard interlock | Tasks 5, 13 |
| Structural-independence adversary | Task 9 |
| progress_evaluator.py | Task 7 |
| extractor.py self-contained | Task 14 |
| backlog.py | Task 15 |
| Corrector with alternative-generation | Task 17 |
| spec_stale → paraphrase | Task 18 + Task 17 routing |
| budget.py degradation ladder | Task 6 |
| /ux-cycle Strategy.FITNESS | Task 20 |
| fitness.repr_fields lint warning | Task 2 |
| Unit tests + E2E against support_tickets | Tasks 1-21 unit, Task 22 E2E |
| Regression comparator | Task 16 |
| Per-cycle independence logging | Task 21 |

All v1 bullets covered.

**2. Type consistency** — verified the shared dataclasses in Task 3 (`Finding`, `LedgerStep`, `FitnessDiff`, `RowChange`, `EvidenceEmbedded`) are used consistently across all downstream tasks.

**3. Dependency ordering** — verified by inspection: Task 3 (models) before Task 4 (ledger uses models); Task 4 before Task 7 (progress_evaluator uses FitnessDiff); Task 8 (spec_extractor) before Task 9 (adversary reuses Capability type); Tasks 1-18 before Task 19 (engine composes all).

**4. Prerequisite gate** — Task 0 Step 5 blocks if ADR-0020's `LifecycleSpec` is not yet available. This correctly enforces the "lifecycle plan ships first" sequencing.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-13-agent-led-fitness-v1-plan.md`.

**Prerequisites before execution:**
1. ADR-0020 lifecycle implementation plan must be executed and merged first. See `docs/superpowers/plans/2026-04-13-lifecycle-evidence-predicates-plan.md`.
2. Task 0 discovery must be completed before Task 1 — the implementer should verify assumptions about DazzleAgent, RuntimeServices, and the LLM facade before writing code.

**Execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, controller curates context. Best for a plan this size (24 tasks, ~15 files of new production code).
2. **Inline Execution** — execute tasks sequentially in-session using `superpowers:executing-plans`. Faster setup but pollutes main agent context.

Given that this plan covers a ~2000-LOC new subsystem with shared dataclasses threading across 20+ modules, **Subagent-Driven** is the recommended approach. Each task has self-contained test + implementation + commit and the shared models in Task 3 give all later tasks a stable vocabulary.
