# Stories & Scenes Operating Model — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add phase kind enum, scene scoring dimensions, gaps analysis, and lifecycle operation to Dazzle's rhythm system, implementing the Cyfuture stories-and-scenes operating model.

**Architecture:** Extend the existing rhythm IR/parser/handler chain. New Pydantic models for evaluation and gaps output. Two new MCP operations (`gaps`, `lifecycle`) plus enriched `evaluate`. All advisory, never blocking.

**Tech Stack:** Python 3.12+, Pydantic v2, existing Dazzle parser/IR/MCP infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-11-stories-and-scenes-operating-model-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/dazzle/core/ir/rhythm.py` | IR models: PhaseKind enum, kind field on PhaseSpec, evaluation/gap/lifecycle models | Modify |
| `src/dazzle/core/dsl_parser_impl/rhythm.py` | Parse `kind:` field in phases | Modify |
| `src/dazzle/mcp/server/handlers/rhythm.py` | `gaps_handler`, `lifecycle_handler`, enriched `evaluate_handler`, updated `propose`, `coverage`, `get`, `list` | Modify |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register `gaps` + `lifecycle` in dispatch | Modify |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `gaps` + `lifecycle` to rhythm enum | Modify |
| `src/dazzle/mcp/server/handlers/pipeline.py` | Add `scene_gaps` quality step | Modify |
| `src/dazzle/core/ir/__init__.py` | Export new types: PhaseKind, evaluation/gap/lifecycle models | Modify |
| `src/dazzle/mcp/server/handlers/stories.py` | Update `propose` for planning inversion (procedural, not prompt) | Modify |
| `docs/reference/grammar.md` | Add `kind:` to rhythm phase grammar | Modify |
| `docs/reference/rhythms.md` | Document phase kinds, gaps, lifecycle | Modify |
| `tests/unit/test_rhythm_ir.py` | Tests for new IR models | Modify |
| `tests/unit/test_rhythm_parser.py` | Tests for `kind:` parsing | Modify |
| `tests/unit/test_rhythm_mcp.py` | Tests for gaps, lifecycle, enriched evaluate | Modify |

---

## Chunk 1: IR Models & Parser (Phase Kind)

### Task 1: Add PhaseKind enum and kind field to IR

**Files:**
- Modify: `src/dazzle/core/ir/rhythm.py`
- Test: `tests/unit/test_rhythm_ir.py`

- [ ] **Step 1: Write failing tests for PhaseKind and kind field**

In `tests/unit/test_rhythm_ir.py`, add:

```python
from dazzle.core.ir.rhythm import PhaseKind, PhaseSpec, SceneSpec


def test_phase_kind_enum_values():
    assert PhaseKind.ONBOARDING.value == "onboarding"
    assert PhaseKind.ACTIVE.value == "active"
    assert PhaseKind.PERIODIC.value == "periodic"
    assert PhaseKind.AMBIENT.value == "ambient"
    assert PhaseKind.OFFBOARDING.value == "offboarding"


def test_phase_spec_kind_none_by_default():
    phase = PhaseSpec(name="test", scenes=[])
    assert phase.kind is None


def test_phase_spec_kind_set():
    phase = PhaseSpec(name="test", kind=PhaseKind.AMBIENT, scenes=[])
    assert phase.kind == PhaseKind.AMBIENT


def test_phase_spec_kind_frozen():
    phase = PhaseSpec(name="test", kind=PhaseKind.ACTIVE, scenes=[])
    with pytest.raises(Exception):
        phase.kind = PhaseKind.AMBIENT  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "phase_kind or kind_none or kind_set or kind_frozen"`
Expected: FAIL — `PhaseKind` not importable

- [ ] **Step 3: Implement PhaseKind enum and kind field**

In `src/dazzle/core/ir/rhythm.py`, add the enum and field:

```python
from enum import Enum

class PhaseKind(str, Enum):
    """Phase kind — authorial intent for the temporal nature of a phase."""
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    PERIODIC = "periodic"
    AMBIENT = "ambient"
    OFFBOARDING = "offboarding"
```

Add to `PhaseSpec`:

```python
class PhaseSpec(BaseModel):
    name: str = Field(..., description="Phase identifier")
    kind: PhaseKind | None = Field(default=None, description="Phase kind hint")
    scenes: list[SceneSpec] = Field(default_factory=list, description="Scenes in phase")
    source: SourceLocation | None = None
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "phase_kind or kind_none or kind_set or kind_frozen"`
Expected: PASS

- [ ] **Step 5: Update `ir/__init__.py` exports**

In `src/dazzle/core/ir/__init__.py`, update the rhythm imports section:

```python
# Rhythms (v0.39.0 Longitudinal UX Evaluation)
from .rhythm import (
    PhaseKind,
    PhaseSpec,
    RhythmSpec,
    SceneSpec,
)
```

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/rhythm.py src/dazzle/core/ir/__init__.py tests/unit/test_rhythm_ir.py
git commit -m "feat(ir): add PhaseKind enum and kind field to PhaseSpec"
```

---

### Task 2: Parse `kind:` field in rhythm phases

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/rhythm.py`
- Test: `tests/unit/test_rhythm_parser.py`

- [ ] **Step 1: Write failing parser tests**

In `tests/unit/test_rhythm_parser.py`, add:

```python
def test_parse_phase_with_kind():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase setup:
    kind: onboarding
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    phase = fragment.rhythms[0].phases[0]
    assert phase.kind is not None
    assert phase.kind.value == "onboarding"


def test_parse_phase_kind_all_values():
    """Each PhaseKind value parses correctly."""
    for kind_val in ["onboarding", "active", "periodic", "ambient", "offboarding"]:
        dsl = f"""\
module test_app
app test "Test"

rhythm r "R":
  persona: user

  phase p:
    kind: {kind_val}
    scene s "S":
      on: surf
"""
        _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert fragment.rhythms[0].phases[0].kind is not None
        assert fragment.rhythms[0].phases[0].kind.value == kind_val


def test_parse_phase_without_kind_is_none():
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert fragment.rhythms[0].phases[0].kind is None


def test_parse_phase_invalid_kind_ignored():
    """Invalid kind value is skipped (treated as unknown field)."""
    dsl = """\
module test_app
app test "Test"

rhythm r "R":
  persona: user

  phase p:
    kind: nonexistent
    scene s "S":
      on: surf
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    # Invalid kind should be None — parser skips unrecognized values
    assert fragment.rhythms[0].phases[0].kind is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_parser.py -v -k "kind"`
Expected: FAIL — `kind` not parsed, always None

- [ ] **Step 3: Implement kind parsing in `_parse_rhythm_phase`**

In `src/dazzle/core/dsl_parser_impl/rhythm.py`, modify `_parse_rhythm_phase()`:

```python
def _parse_rhythm_phase(self) -> ir.PhaseSpec:
    """Parse a phase block within a rhythm."""
    loc = self._source_location()
    name = self.expect_identifier_or_keyword().value
    self.expect(TokenType.COLON)
    self.skip_newlines()
    self.expect(TokenType.INDENT)

    kind = None
    scenes: list[ir.SceneSpec] = []

    while not self.match(TokenType.DEDENT):
        self.skip_newlines()
        if self.match(TokenType.DEDENT):
            break

        if self.match(TokenType.SCENE):
            self.advance()
            scenes.append(self._parse_rhythm_scene())
        else:
            token = self.current_token()
            if token.value == "kind":
                self.advance()
                self.expect(TokenType.COLON)
                kind_value = self.expect_identifier_or_keyword().value
                try:
                    kind = ir.PhaseKind(kind_value)
                except ValueError:
                    kind = None  # unrecognized kind — treat as unspecified
                self.skip_newlines()
            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_rhythm_field()

    self.expect(TokenType.DEDENT)

    return ir.PhaseSpec(name=name, kind=kind, scenes=scenes, source=loc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_parser.py -v`
Expected: All PASS (new tests + existing tests unbroken)

- [ ] **Step 5: Run full rhythm test suite to check for regressions**

Run: `pytest tests/unit/test_rhythm_ir.py tests/unit/test_rhythm_parser.py tests/unit/test_rhythm_mcp.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/rhythm.py tests/unit/test_rhythm_parser.py
git commit -m "feat(parser): parse kind: field in rhythm phases"
```

---

### Task 3: Update MCP handlers to expose phase kind

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`
- Test: `tests/unit/test_rhythm_mcp.py`

- [ ] **Step 1: Write failing test for kind in list and get responses**

In `tests/unit/test_rhythm_mcp.py`, add tests that check the `list` and `get` handlers include `kind` in their output. The test fixtures need a PhaseSpec with `kind` set. Check existing fixture pattern and extend it.

```python
def test_list_rhythms_includes_phase_kinds(mock_appspec_with_kind):
    """list operation includes phase kind counts."""
    result = list_rhythms_handler(Path("/fake"), {})
    data = json.loads(result)
    rhythm = data["rhythms"][0]
    assert "ambient_phases" in rhythm


def test_get_rhythm_includes_phase_kind(mock_appspec_with_kind):
    """get operation includes kind field on phases."""
    result = get_rhythm_handler(Path("/fake"), {"name": "test_rhythm"})
    data = json.loads(result)
    phase = data["phases"][0]
    assert "kind" in phase
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "kind"`
Expected: FAIL

- [ ] **Step 3: Update list and get handlers to include kind**

In `src/dazzle/mcp/server/handlers/rhythm.py`:

In `list_rhythms_handler`, add to the rhythm dict:
```python
"ambient_phases": sum(
    1 for p in r.phases if p.kind and p.kind.value == "ambient"
),
```

In `get_rhythm_handler`, add `"kind"` to the phase dict:
```python
{
    "name": p.name,
    "kind": p.kind.value if p.kind else None,
    "scenes": [...],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_mcp.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_rhythm_mcp.py
git commit -m "feat(mcp): expose phase kind in rhythm list/get handlers"
```

---

## Chunk 2: Evaluation Models & Submit Scores

### Task 4: Add evaluation output models to IR

**Files:**
- Modify: `src/dazzle/core/ir/rhythm.py`
- Test: `tests/unit/test_rhythm_ir.py`

- [ ] **Step 1: Write failing tests for evaluation models**

```python
from dazzle.core.ir.rhythm import SceneDimensionScore, SceneEvaluation


def test_scene_dimension_score_creation():
    score = SceneDimensionScore(
        dimension="arrival",
        score="pass",
        evidence="Page loaded successfully",
        root_cause=None,
    )
    assert score.dimension == "arrival"
    assert score.score == "pass"


def test_scene_dimension_score_with_root_cause():
    score = SceneDimensionScore(
        dimension="action",
        score="fail",
        evidence="Submit button not found",
        root_cause="Missing story: create_task",
    )
    assert score.root_cause == "Missing story: create_task"


def test_scene_evaluation_creation():
    dims = [
        SceneDimensionScore(dimension="arrival", score="pass", evidence="ok"),
        SceneDimensionScore(dimension="orientation", score="pass", evidence="ok"),
        SceneDimensionScore(dimension="action", score="fail", evidence="no button"),
        SceneDimensionScore(dimension="completion", score="skip", evidence="n/a"),
        SceneDimensionScore(dimension="confidence", score="skip", evidence="n/a"),
    ]
    ev = SceneEvaluation(
        scene_name="browse",
        phase_name="discovery",
        dimensions=dims,
        gap_type="capability",
        story_ref="browse_courses",
    )
    assert ev.gap_type == "capability"
    assert len(ev.dimensions) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "dimension_score or scene_evaluation"`
Expected: FAIL — classes not importable

- [ ] **Step 3: Implement SceneDimensionScore and SceneEvaluation**

Add to `src/dazzle/core/ir/rhythm.py`:

```python
from typing import Literal

class SceneDimensionScore(BaseModel):
    """Score for a single evaluation dimension of a scene."""
    dimension: Literal["arrival", "orientation", "action", "completion", "confidence"]
    score: Literal["pass", "partial", "fail", "skip"]
    evidence: str = Field(..., description="What the agent observed")
    root_cause: str | None = Field(default=None, description="Only on partial/fail")
    model_config = ConfigDict(frozen=True)


class SceneEvaluation(BaseModel):
    """Agent-produced evaluation of a scene across five dimensions."""
    scene_name: str
    phase_name: str
    dimensions: list[SceneDimensionScore]
    gap_type: Literal["capability", "surface", "workflow", "feedback", "none"]
    story_ref: str | None = None
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "dimension_score or scene_evaluation"`
Expected: PASS

- [ ] **Step 5: Update `ir/__init__.py` exports**

Add `SceneDimensionScore` and `SceneEvaluation` to the rhythm imports in `src/dazzle/core/ir/__init__.py`.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/rhythm.py src/dazzle/core/ir/__init__.py tests/unit/test_rhythm_ir.py
git commit -m "feat(ir): add SceneDimensionScore and SceneEvaluation models"
```

---

### Task 5: Add Gap and GapsReport models to IR

**Files:**
- Modify: `src/dazzle/core/ir/rhythm.py`
- Test: `tests/unit/test_rhythm_ir.py`

- [ ] **Step 1: Write failing tests for Gap and GapsReport**

```python
from dazzle.core.ir.rhythm import Gap, GapsSummary, GapsReport


def test_gap_creation():
    gap = Gap(
        kind="capability",
        severity="blocking",
        scene="browse",
        phase="discovery",
        rhythm="onboarding",
        persona="new_user",
        story_ref="browse_courses",
        surface_ref="course_list",
        description="Story 'browse_courses' is DRAFT",
    )
    assert gap.kind == "capability"
    assert gap.severity == "blocking"


def test_gaps_summary():
    summary = GapsSummary(
        total=3,
        by_kind={"capability": 2, "ambient": 1},
        by_severity={"blocking": 2, "advisory": 1},
        by_persona={"new_user": 3},
    )
    assert summary.total == 3


def test_gaps_report():
    gap = Gap(
        kind="ambient",
        severity="advisory",
        scene=None,
        phase=None,
        rhythm="onboarding",
        persona="new_user",
        story_ref=None,
        surface_ref=None,
        description="No ambient phase for persona 'new_user'",
    )
    report = GapsReport(
        gaps=[gap],
        summary=GapsSummary(
            total=1,
            by_kind={"ambient": 1},
            by_severity={"advisory": 1},
            by_persona={"new_user": 1},
        ),
        roadmap_order=[gap],
    )
    assert len(report.gaps) == 1
    assert report.roadmap_order[0].kind == "ambient"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "gap"`
Expected: FAIL

- [ ] **Step 3: Implement Gap, GapsSummary, GapsReport**

Add to `src/dazzle/core/ir/rhythm.py`:

```python
class Gap(BaseModel):
    """A single gap identified by analysis."""
    kind: Literal[
        "capability", "surface", "workflow", "feedback",
        "ambient", "unmapped", "orphan", "unscored",
    ]
    severity: Literal["blocking", "degraded", "advisory"]
    scene: str | None = None
    phase: str | None = None
    rhythm: str
    persona: str
    story_ref: str | None = None
    surface_ref: str | None = None
    description: str
    model_config = ConfigDict(frozen=True)


class GapsSummary(BaseModel):
    """Aggregate gap counts."""
    total: int
    by_kind: dict[str, int]
    by_severity: dict[str, int]
    by_persona: dict[str, int]
    model_config = ConfigDict(frozen=True)


class GapsReport(BaseModel):
    """Full gaps analysis output."""
    gaps: list[Gap]
    summary: GapsSummary
    roadmap_order: list[Gap]
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "gap"`
Expected: PASS

- [ ] **Step 5: Update `ir/__init__.py` exports**

Add `Gap`, `GapsSummary`, `GapsReport` to the rhythm imports in `src/dazzle/core/ir/__init__.py`.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/rhythm.py src/dazzle/core/ir/__init__.py tests/unit/test_rhythm_ir.py
git commit -m "feat(ir): add Gap, GapsSummary, GapsReport models"
```

---

### Task 6: Add LifecycleStep and LifecycleReport models to IR

**Files:**
- Modify: `src/dazzle/core/ir/rhythm.py`
- Test: `tests/unit/test_rhythm_ir.py`

- [ ] **Step 1: Write failing tests**

```python
from dazzle.core.ir.rhythm import LifecycleStep, LifecycleReport


def test_lifecycle_step():
    step = LifecycleStep(
        step=1,
        name="model_domain",
        status="complete",
        evidence="5 entities with fields and relationships",
        suggestions=[],
    )
    assert step.status == "complete"


def test_lifecycle_report():
    steps = [
        LifecycleStep(step=1, name="model_domain", status="complete", evidence="ok", suggestions=[]),
        LifecycleStep(step=2, name="write_stories", status="not_started", evidence="", suggestions=["Run story propose"]),
    ]
    report = LifecycleReport(
        steps=steps, current_focus="write_stories", maturity="new_domain"
    )
    assert report.maturity == "new_domain"
    assert report.current_focus == "write_stories"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "lifecycle"`
Expected: FAIL

- [ ] **Step 3: Implement LifecycleStep and LifecycleReport**

Add to `src/dazzle/core/ir/rhythm.py`:

```python
class LifecycleStep(BaseModel):
    """Status of one step in the operating model lifecycle."""
    step: int
    name: str
    status: Literal["complete", "partial", "not_started"]
    evidence: str
    suggestions: list[str] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class LifecycleReport(BaseModel):
    """Full lifecycle status report."""
    steps: list[LifecycleStep]
    current_focus: str
    maturity: Literal["new_domain", "building", "evaluating", "mature"]
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_ir.py -v -k "lifecycle"`
Expected: PASS

- [ ] **Step 5: Update `ir/__init__.py` exports**

Add `LifecycleStep`, `LifecycleReport` to the rhythm imports in `src/dazzle/core/ir/__init__.py`.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/rhythm.py src/dazzle/core/ir/__init__.py tests/unit/test_rhythm_ir.py
git commit -m "feat(ir): add LifecycleStep and LifecycleReport models"
```

---

### Task 7: Implement submit_scores action on evaluate handler

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`
- Test: `tests/unit/test_rhythm_mcp.py`

- [ ] **Step 1: Write failing tests for submit_scores**

```python
def test_evaluate_submit_scores_persists(mock_appspec, tmp_path):
    """submit_scores action writes evaluation to .dazzle/evaluations/."""
    scores = [
        {
            "scene_name": "browse",
            "phase_name": "discovery",
            "dimensions": [
                {"dimension": "arrival", "score": "pass", "evidence": "ok"},
                {"dimension": "orientation", "score": "pass", "evidence": "ok"},
                {"dimension": "action", "score": "pass", "evidence": "ok"},
                {"dimension": "completion", "score": "pass", "evidence": "ok"},
                {"dimension": "confidence", "score": "pass", "evidence": "ok"},
            ],
            "gap_type": "none",
            "story_ref": None,
        }
    ]
    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    with patch("...load_project_appspec", return_value=mock_appspec):
        result = evaluate_rhythm_handler(
            project, {"name": "onboarding", "action": "submit_scores", "scores": scores}
        )
    data = json.loads(result)
    assert "stored" in data
    eval_dir = project / ".dazzle" / "evaluations"
    assert eval_dir.exists()
    eval_files = list(eval_dir.glob("eval-*.json"))
    assert len(eval_files) == 1


def test_evaluate_structural_returns_stored_scores(mock_appspec, tmp_path):
    """evaluate action returns stored scores when available."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    # First submit scores
    scores = [
        {
            "scene_name": "browse",
            "phase_name": "discovery",
            "dimensions": [
                {"dimension": "arrival", "score": "pass", "evidence": "ok"},
                {"dimension": "orientation", "score": "pass", "evidence": "ok"},
                {"dimension": "action", "score": "pass", "evidence": "ok"},
                {"dimension": "completion", "score": "pass", "evidence": "ok"},
                {"dimension": "confidence", "score": "pass", "evidence": "ok"},
            ],
            "gap_type": "none",
            "story_ref": None,
        }
    ]
    with patch("...load_project_appspec", return_value=mock_appspec):
        evaluate_rhythm_handler(
            project, {"name": "onboarding", "action": "submit_scores", "scores": scores}
        )
        # Then evaluate — should include stored scores
        result = evaluate_rhythm_handler(project, {"name": "onboarding"})
    data = json.loads(result)
    assert data["scene_scores"] is not None
    assert len(data["scene_scores"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "submit_scores or stored_scores"`
Expected: FAIL

- [ ] **Step 3: Implement submit_scores and score loading in evaluate handler**

In `src/dazzle/mcp/server/handlers/rhythm.py`, modify `evaluate_rhythm_handler`:

```python
@wrap_handler_errors
def evaluate_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Evaluate a rhythm — structural checks + optional scored evaluation."""
    action = args.get("action", "evaluate")

    if action == "submit_scores":
        return _submit_scores(project_root, args)

    # Existing structural evaluation code...
    app_spec = load_project_appspec(project_root)
    # ... existing checks ...

    # Load most recent stored scores if available
    stored_scores = _load_latest_scores(project_root, name)

    return json.dumps({
        "rhythm": name,
        "summary": f"{passed}/{total} checks passed",
        "checks": checks,
        "scene_scores": stored_scores,  # None if no scores exist
    }, indent=2)


def _submit_scores(project_root: Path, args: dict[str, Any]) -> str:
    """Persist agent-produced scene evaluation scores."""
    from dazzle.core.ir.rhythm import SceneEvaluation
    import datetime

    name = args.get("name")
    scores_data = args.get("scores", [])

    # Validate structure
    evaluations = [SceneEvaluation(**s) for s in scores_data]

    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    path = eval_dir / f"eval-{ts}.json"

    data = {
        "rhythm": name,
        "timestamp": ts,
        "evaluations": [e.model_dump() for e in evaluations],
    }
    path.write_text(json.dumps(data, indent=2))

    return json.dumps({"stored": str(path), "count": len(evaluations)})


def _load_latest_scores(project_root: Path, rhythm_name: str) -> list[dict] | None:
    """Load most recent evaluation scores for a rhythm."""
    eval_dir = project_root / ".dazzle" / "evaluations"
    if not eval_dir.exists():
        return None

    files = sorted(eval_dir.glob("eval-*.json"), reverse=True)
    for f in files:
        data = json.loads(f.read_text())
        if data.get("rhythm") == rhythm_name:
            return data.get("evaluations")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_mcp.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_rhythm_mcp.py
git commit -m "feat(mcp): implement submit_scores action on rhythm evaluate"
```

---

## Chunk 3: Gaps Analysis

### Task 8: Implement static gaps analysis handler

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`
- Test: `tests/unit/test_rhythm_mcp.py`

- [ ] **Step 1: Write failing tests for static gaps**

Write tests covering each static gap type:
- Scene with story ref pointing to DRAFT story → `capability` / `blocking`
- Scene with no story ref → `unmapped` / `advisory`
- Story not referenced by any scene → `orphan` / `advisory`
- Persona with rhythm but no ambient phase → `ambient` / `advisory`
- Persona with stories but no rhythm → `unscored` / `advisory`
- Scene with story ref to non-existent story → `capability` / `blocking`

```python
def test_gaps_static_missing_story(mock_appspec_with_gaps):
    """Scene referencing non-existent story produces capability gap."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    blocking = [g for g in data["gaps"] if g["severity"] == "blocking"]
    assert len(blocking) >= 1
    assert blocking[0]["kind"] == "capability"


def test_gaps_static_unmapped_scene(mock_appspec_no_story_refs):
    """Scene with no story: produces unmapped advisory gap."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    unmapped = [g for g in data["gaps"] if g["kind"] == "unmapped"]
    assert len(unmapped) >= 1
    assert unmapped[0]["severity"] == "advisory"


def test_gaps_static_orphan_story(mock_appspec_orphan_stories):
    """Story not referenced by any scene produces orphan advisory gap."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    orphans = [g for g in data["gaps"] if g["kind"] == "orphan"]
    assert len(orphans) >= 1


def test_gaps_static_no_ambient_phase(mock_appspec_no_ambient):
    """Persona with rhythm but no ambient phase produces ambient gap."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    ambient = [g for g in data["gaps"] if g["kind"] == "ambient"]
    assert len(ambient) >= 1


def test_gaps_roadmap_order_blocking_first(mock_appspec_with_gaps):
    """roadmap_order sorts blocking before advisory."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    severities = [g["severity"] for g in data["roadmap_order"]]
    blocking_idx = [i for i, s in enumerate(severities) if s == "blocking"]
    advisory_idx = [i for i, s in enumerate(severities) if s == "advisory"]
    if blocking_idx and advisory_idx:
        assert max(blocking_idx) < min(advisory_idx)


def test_gaps_summary_counts(mock_appspec_with_gaps):
    """Summary has correct counts."""
    result = gaps_rhythm_handler(Path("/fake"), {})
    data = json.loads(result)
    assert data["summary"]["total"] == len(data["gaps"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "gaps"`
Expected: FAIL — `gaps_rhythm_handler` not importable

- [ ] **Step 3: Implement gaps_rhythm_handler**

In `src/dazzle/mcp/server/handlers/rhythm.py`, add:

```python
@wrap_handler_errors
def gaps_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse gaps between scenes and stories."""
    app_spec = load_project_appspec(project_root)

    gaps: list[dict[str, Any]] = []

    # Build lookup sets
    # IMPORTANT: scene.story stores story_id values (e.g., "ST-001"),
    # matching the story_id field on StorySpec. The linker validates
    # scene.story against symbols.stories which is keyed by story_id.
    story_by_id = {s.story_id: s for s in app_spec.stories}
    scene_story_refs: set[str] = set()

    # Per-persona tracking
    persona_has_ambient: dict[str, bool] = {}
    personas_with_rhythms: set[str] = set()

    for rhythm in app_spec.rhythms:
        personas_with_rhythms.add(rhythm.persona)
        has_ambient = False

        for phase in rhythm.phases:
            if phase.kind and phase.kind.value == "ambient":
                has_ambient = True

            for scene in phase.scenes:
                if scene.story:
                    scene_story_refs.add(scene.story)
                    # Check if story exists and is accepted
                    story = story_by_id.get(scene.story)
                    if story is None:
                        gaps.append(_make_gap(
                            "capability", "blocking", scene, phase, rhythm,
                            story_ref=scene.story,
                            desc=f"Scene '{scene.name}' references non-existent story '{scene.story}'",
                        ))
                    elif story.status.value == "draft":
                        gaps.append(_make_gap(
                            "capability", "blocking", scene, phase, rhythm,
                            story_ref=scene.story,
                            desc=f"Scene '{scene.name}' references DRAFT story '{scene.story}'",
                        ))
                else:
                    gaps.append(_make_gap(
                        "unmapped", "advisory", scene, phase, rhythm,
                        desc=f"Scene '{scene.name}' has no story: reference",
                    ))

        persona_has_ambient[rhythm.persona] = has_ambient

    # Orphan stories
    for story_id in story_by_id:
        if story_id not in scene_story_refs:
            story = story_by_id[story_id]
            gaps.append({
                "kind": "orphan", "severity": "advisory",
                "scene": None, "phase": None,
                "rhythm": "", "persona": getattr(story, "actor", ""),
                "story_ref": story_id, "surface_ref": None,
                "description": f"Story '{story_id}' is not referenced by any scene",
            })

    # Ambient gaps
    for persona_id, has_ambient in persona_has_ambient.items():
        if not has_ambient:
            gaps.append({
                "kind": "ambient", "severity": "advisory",
                "scene": None, "phase": None,
                "rhythm": "", "persona": persona_id,
                "story_ref": None, "surface_ref": None,
                "description": f"Persona '{persona_id}' has no ambient phase",
            })

    # Unscored personas
    personas_with_stories = {s.actor for s in app_spec.stories if hasattr(s, "actor")}
    for pid in personas_with_stories - personas_with_rhythms:
        gaps.append({
            "kind": "unscored", "severity": "advisory",
            "scene": None, "phase": None,
            "rhythm": "", "persona": pid,
            "story_ref": None, "surface_ref": None,
            "description": f"Persona '{pid}' has stories but no rhythm",
        })

    # Layer in evaluated gaps if available
    _layer_evaluated_gaps(project_root, gaps)

    # Build summary
    summary = _build_gaps_summary(gaps)

    # Sort for roadmap
    severity_order = {"blocking": 0, "degraded": 1, "advisory": 2}
    roadmap = sorted(gaps, key=lambda g: severity_order.get(g["severity"], 9))

    result = {
        "gaps": gaps,
        "summary": summary,
        "roadmap_order": roadmap,
    }

    # Persist gaps report for lifecycle tracking
    import datetime
    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    (eval_dir / f"gaps-{ts}.json").write_text(json.dumps(result, indent=2))

    return json.dumps(result, indent=2)
```

Add helper functions `_make_gap()`, `_build_gaps_summary()`, `_layer_evaluated_gaps()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "gaps"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_rhythm_mcp.py
git commit -m "feat(mcp): implement static gaps analysis handler"
```

---

## Chunk 4: Lifecycle Operation & Tool Registration

### Task 9: Implement lifecycle handler

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`
- Test: `tests/unit/test_rhythm_mcp.py`

- [ ] **Step 1: Write failing tests for lifecycle**

```python
def test_lifecycle_empty_project(mock_empty_appspec, tmp_path):
    """Empty project returns new_domain maturity."""
    result = lifecycle_rhythm_handler(tmp_path, {})
    data = json.loads(result)
    assert data["maturity"] == "new_domain"
    assert len(data["steps"]) == 8
    assert data["steps"][0]["status"] == "not_started"


def test_lifecycle_with_entities_and_stories(mock_appspec_with_stories, tmp_path):
    """Project with entities + accepted stories is 'building'."""
    result = lifecycle_rhythm_handler(tmp_path, {})
    data = json.loads(result)
    assert data["steps"][0]["status"] == "complete"  # model_domain
    assert data["steps"][1]["status"] in ("complete", "partial")  # write_stories


def test_lifecycle_current_focus_is_first_incomplete(mock_appspec_partial, tmp_path):
    """current_focus recommends the first non-complete step."""
    result = lifecycle_rhythm_handler(tmp_path, {})
    data = json.loads(result)
    first_incomplete = next(s for s in data["steps"] if s["status"] != "complete")
    assert data["current_focus"] == first_incomplete["name"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "lifecycle"`
Expected: FAIL

- [ ] **Step 3: Implement lifecycle_rhythm_handler**

In `src/dazzle/mcp/server/handlers/rhythm.py`, add:

```python
@wrap_handler_errors
def lifecycle_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Report lifecycle status against the 8-step operating model."""
    app_spec = load_project_appspec(project_root)

    steps = []

    # Step 1: model_domain
    entities = app_spec.domain.entities
    has_entities = len(entities) > 0
    has_fields = any(len(e.fields) > 0 for e in entities) if entities else False
    step1_status = "complete" if has_entities and has_fields else ("partial" if has_entities else "not_started")
    steps.append({"step": 1, "name": "model_domain", "status": step1_status,
                  "evidence": f"{len(entities)} entities", "suggestions": [] if step1_status == "complete" else ["Define entities with fields"]})

    # Step 2: write_stories
    stories = app_spec.stories
    accepted = [s for s in stories if s.status.value == "accepted"]
    step2_status = "complete" if accepted else ("partial" if stories else "not_started")
    steps.append({"step": 2, "name": "write_stories", "status": step2_status,
                  "evidence": f"{len(accepted)} accepted, {len(stories)} total",
                  "suggestions": [] if step2_status == "complete" else ["Run story propose"]})

    # Step 3: write_rhythms
    rhythms = app_spec.rhythms
    persona_ids = {p.id for p in app_spec.personas}
    covered = {r.persona for r in rhythms}
    step3_status = "complete" if rhythms and covered >= persona_ids else ("partial" if rhythms else "not_started")
    steps.append({"step": 3, "name": "write_rhythms", "status": step3_status,
                  "evidence": f"{len(rhythms)} rhythms, {len(covered)}/{len(persona_ids)} personas covered",
                  "suggestions": [] if step3_status == "complete" else ["Run rhythm propose for uncovered personas"]})

    # Step 4: map_scenes_to_stories
    total_scenes = sum(len(p.scenes) for r in rhythms for p in r.phases)
    mapped = sum(1 for r in rhythms for p in r.phases for s in p.scenes if s.story)
    step4_status = "complete" if total_scenes > 0 and mapped == total_scenes else ("partial" if mapped > 0 else "not_started")
    steps.append({"step": 4, "name": "map_scenes_to_stories", "status": step4_status,
                  "evidence": f"{mapped}/{total_scenes} scenes mapped",
                  "suggestions": [] if step4_status == "complete" else [f"{total_scenes - mapped} scenes need story: references"]})

    # Step 5: build_from_stories
    test_designs_dir = project_root / ".dazzle" / "test_designs"
    has_tests = test_designs_dir.exists() and any(test_designs_dir.glob("*.json"))
    step5_status = "complete" if has_tests and accepted else ("partial" if has_tests or accepted else "not_started")
    steps.append({"step": 5, "name": "build_from_stories", "status": step5_status,
                  "evidence": "test designs exist" if has_tests else "no test designs",
                  "suggestions": [] if step5_status == "complete" else ["Run story generate_tests"]})

    # Step 6: evaluate_from_scenes
    eval_dir = project_root / ".dazzle" / "evaluations"
    has_evals = eval_dir.exists() and any(eval_dir.glob("eval-*.json"))
    step6_status = "complete" if has_evals else "not_started"
    steps.append({"step": 6, "name": "evaluate_from_scenes", "status": step6_status,
                  "evidence": "evaluations exist" if has_evals else "no evaluations",
                  "suggestions": [] if step6_status == "complete" else ["Run rhythm evaluate with submit_scores"]})

    # Step 7: find_gaps
    has_gaps = eval_dir.exists() and any(eval_dir.glob("gaps-*.json"))
    step7_status = "complete" if has_gaps else "not_started"
    steps.append({"step": 7, "name": "find_gaps", "status": step7_status,
                  "evidence": "gaps report exists" if has_gaps else "no gaps report",
                  "suggestions": [] if step7_status == "complete" else ["Run rhythm gaps"]})

    # Step 8: iterate (always partial — tracks delta)
    step8_status = "partial" if any(s["status"] == "complete" for s in steps) else "not_started"
    steps.append({"step": 8, "name": "iterate", "status": step8_status,
                  "evidence": "ongoing", "suggestions": ["Review gaps, add stories, re-evaluate"]})

    # Maturity
    complete_steps = {s["step"] for s in steps if s["status"] == "complete"}
    if {1, 2, 3, 4, 5, 6, 7} <= complete_steps:
        maturity = "mature"
    elif {1, 2, 3, 4, 5} <= complete_steps:
        maturity = "evaluating"
    elif {1, 2, 3} <= complete_steps:
        maturity = "building"
    else:
        maturity = "new_domain"

    # Current focus: first non-complete step
    current_focus = next((s["name"] for s in steps if s["status"] != "complete"), "iterate")

    return json.dumps({
        "steps": steps,
        "current_focus": current_focus,
        "maturity": maturity,
    }, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "lifecycle"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_rhythm_mcp.py
git commit -m "feat(mcp): implement lifecycle handler for operating model status"
```

---

### Task 10: Register new operations in tool schema and dispatch

**Files:**
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`

- [ ] **Step 1: Update rhythm tool schema in tools_consolidated.py**

Find the rhythm Tool definition and update:

1. Operation enum: `"enum": ["propose", "evaluate", "gaps", "lifecycle", "coverage", "get", "list"]`
2. Add new parameters for evaluate's enriched mode:
```python
"action": {
    "type": "string",
    "enum": ["evaluate", "submit_scores"],
    "description": "Evaluate action: 'evaluate' (structural, default) or 'submit_scores' (persist agent scores)",
},
"scores": {
    "type": "array",
    "description": "Scene evaluation scores (for submit_scores action)",
    "items": {"type": "object"},
},
```
3. Update the tool description string to mention gaps and lifecycle operations.

- [ ] **Step 2: Update handler dispatch in handlers_consolidated.py**

Add imports and dispatch entries:

```python
from .handlers.rhythm import (
    coverage_rhythms_handler,
    evaluate_rhythm_handler,
    gaps_rhythm_handler,
    get_rhythm_handler,
    lifecycle_rhythm_handler,
    list_rhythms_handler,
    propose_rhythm_handler,
)

ops: dict[str, Callable[..., str]] = {
    "propose": propose_rhythm_handler,
    "evaluate": evaluate_rhythm_handler,
    "gaps": gaps_rhythm_handler,
    "lifecycle": lifecycle_rhythm_handler,
    "coverage": coverage_rhythms_handler,
    "get": get_rhythm_handler,
    "list": list_rhythms_handler,
}
```

- [ ] **Step 3: Run full test suite to check for regressions**

Run: `pytest tests/unit/test_rhythm_ir.py tests/unit/test_rhythm_parser.py tests/unit/test_rhythm_mcp.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/tools_consolidated.py src/dazzle/mcp/server/handlers_consolidated.py
git commit -m "feat(mcp): register gaps and lifecycle operations in rhythm tool"
```

---

## Chunk 5: Pipeline Integration & Prompt Updates

### Task 11: Add scene_gaps quality step to pipeline

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/pipeline.py`

- [ ] **Step 1: Add scene_gaps step to `_build_quality_steps()`**

After the `story(coverage)` step, add:

```python
from .rhythm import gaps_rhythm_handler

steps.append(
    QualityStep(
        name="rhythm(gaps)",
        handler=gaps_rhythm_handler,
        handler_args=(project_path, {}),
        optional=True,
    )
)
```

- [ ] **Step 2: Write test for rhythm(gaps) step in pipeline**

```python
def test_pipeline_includes_rhythm_gaps_step():
    """Pipeline includes rhythm(gaps) as a quality step."""
    steps = _build_quality_steps(Path("/fake"))
    step_names = [s.name for s in steps]
    assert "rhythm(gaps)" in step_names
```

- [ ] **Step 3: Run pipeline tests**

Run: `pytest tests/unit/ -v -k "pipeline"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat(pipeline): add rhythm gaps as quality step"
```

---

### Task 12: Update propose prompts for planning inversion

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py` (propose)
- Modify: `src/dazzle/mcp/server/handlers/stories.py` (propose)

- [ ] **Step 1: Update rhythm propose to suggest ambient phases**

In `propose_rhythm_handler`, after generating discovery/engagement phases, add an ambient phase:

```python
lines.append("  phase ambient:")
lines.append("    kind: ambient")
lines.append(f'    scene check_status "Check Status":')
lines.append(f"      on: {list_surfaces[0] if list_surfaces else 'dashboard'}")
lines.append("      action: browse")
lines.append('      expects: "relevant_information_visible"')
lines.append("")
```

- [ ] **Step 2: Update story propose to generate stories from unmapped scenes**

In `src/dazzle/mcp/server/handlers/stories.py`, in `propose_stories_from_dsl_handler`, add a second generation loop after the entity-based stories loop. This implements the planning inversion — scenes that exist but have no backing story get stories generated for them.

The handler is **procedural** (builds `StorySpec` objects directly), not prompt-based. Add after the entity loop:

```python
    # Planning inversion: generate stories for unmapped scenes
    progress.log_sync("Generating stories from unmapped scenes...")
    for rhythm in app_spec.rhythms:
        for phase in rhythm.phases:
            for scene in phase.scenes:
                if scene.story:
                    continue  # already mapped
                if story_count >= max_stories:
                    break

                actor = rhythm.persona
                # Resolve persona label
                for p in app_spec.personas:
                    if p.id == rhythm.persona:
                        actor = p.label or p.id
                        break

                scope = [scene.entity] if scene.entity else []
                action_desc = ", ".join(scene.actions) if scene.actions else "interact"

                stories.append(
                    StorySpec(
                        story_id=next_id(),
                        title=f"{actor} {action_desc}s on {scene.surface}",
                        actor=actor,
                        trigger=StoryTrigger.USER_CLICK,
                        scope=scope,
                        preconditions=[f"{actor} is on {scene.surface} surface"],
                        happy_path_outcome=[
                            scene.expects or f"Action completes on {scene.surface}",
                        ],
                        side_effects=[],
                        constraints=[],
                        variants=[],
                        status=StoryStatus.DRAFT,
                        created_at=now,
                    )
                )
```

- [ ] **Step 3: Write tests for propose updates**

In `tests/unit/test_rhythm_mcp.py`:
```python
def test_propose_rhythm_includes_ambient_phase(mock_appspec):
    """Proposed rhythm includes an ambient phase."""
    result = propose_rhythm_handler(Path("/fake"), {"persona": "new_user"})
    data = json.loads(result)
    dsl = data["proposed_dsl"]
    assert "kind: ambient" in dsl
    assert "phase ambient:" in dsl
```

In `tests/unit/test_stories_mcp.py` (or equivalent):
```python
def test_propose_stories_from_unmapped_scenes(mock_appspec_with_unmapped_scenes):
    """Stories are generated for scenes without story: references."""
    result = propose_stories_from_dsl_handler(Path("/fake"), {})
    data = json.loads(result)
    # Should include stories generated from unmapped scenes
    titles = [s["title"] for s in data["stories"]]
    assert any("browse" in t.lower() for t in titles)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_rhythm_mcp.py tests/unit/test_stories_mcp.py -v -k "propose"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py src/dazzle/mcp/server/handlers/stories.py tests/
git commit -m "feat(mcp): update propose handlers for ambient phases and planning inversion"
```

---

### Task 13: Update coverage handler for ambient analysis

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py`

- [ ] **Step 1: Update coverage_rhythms_handler**

Add ambient coverage to the output:

```python
personas_with_ambient: set[str] = set()

for r in app_spec.rhythms:
    personas_with_rhythms.add(r.persona)
    for phase in r.phases:
        if phase.kind and phase.kind.value == "ambient":
            personas_with_ambient.add(r.persona)
        for scene in phase.scenes:
            surfaces_exercised.add(scene.surface)

# Add to return dict:
"personas_with_ambient": sorted(personas_with_ambient),
"personas_without_ambient": sorted(personas_with_rhythms - personas_with_ambient),
```

- [ ] **Step 2: Write test for ambient coverage**

```python
def test_coverage_includes_ambient_analysis(mock_appspec_with_ambient):
    """Coverage output includes ambient persona analysis."""
    result = coverage_rhythms_handler(Path("/fake"), {})
    data = json.loads(result)
    assert "personas_with_ambient" in data
    assert "personas_without_ambient" in data
```

- [ ] **Step 3: Run coverage tests**

Run: `pytest tests/unit/test_rhythm_mcp.py -v -k "coverage"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_rhythm_mcp.py
git commit -m "feat(mcp): add ambient coverage to rhythm coverage handler"
```

---

## Chunk 6: Knowledge Graph Relations

### Task 14: Seed scene_exercises_story relations from linker

**Files:**
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py` (or linker post-processing)
- Modify: `src/dazzle/mcp/server/handlers/rhythm.py` (gaps handler seeds gap_blocks_scene)
- Test: `tests/unit/test_kg_seed.py`

- [ ] **Step 1: Write failing test for scene_exercises_story relation**

```python
def test_kg_scene_exercises_story_relation(seeded_graph, app_spec_with_rhythm):
    """Scenes with story: refs create scene_exercises_story relations in KG."""
    from dazzle.mcp.knowledge_graph.seed import seed_scene_story_relations
    seed_scene_story_relations(seeded_graph, app_spec_with_rhythm)
    relations = seeded_graph.store.query_relations(
        source_id="scene:onboarding.browse",
        relation_type="scene_exercises_story",
    )
    assert len(relations) == 1
    assert relations[0].target_id == "story:browse_courses"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_kg_seed.py -v -k "scene_exercises_story"`
Expected: FAIL

- [ ] **Step 3: Implement seed_scene_story_relations**

Add to `src/dazzle/mcp/knowledge_graph/seed.py`:

```python
def seed_scene_story_relations(graph: KnowledgeGraph, app_spec: AppSpec) -> None:
    """Populate scene_exercises_story relations from rhythm scene story: refs."""
    for rhythm in app_spec.rhythms:
        for phase in rhythm.phases:
            for scene in phase.scenes:
                if scene.story:
                    source_id = f"scene:{rhythm.name}.{scene.name}"
                    target_id = f"story:{scene.story}"
                    graph.store.create_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type="scene_exercises_story",
                        metadata={"rhythm": rhythm.name, "phase": phase.name},
                    )
```

Call this from the appropriate initialization point (after appspec is loaded and KG is seeded).

- [ ] **Step 4: Add gap_blocks_scene seeding to gaps handler**

In the gaps handler, after computing gaps, seed KG relations:

```python
def _seed_gap_relations(project_root: Path, gaps: list[dict]) -> None:
    """Seed gap_blocks_scene relations into KG."""
    from dazzle.mcp.server.state import get_knowledge_graph
    graph = get_knowledge_graph()
    if graph is None:
        return
    import hashlib
    for gap in gaps:
        if gap.get("scene"):
            gap_id = f"gap:{gap['kind']}:{hashlib.md5(gap['description'].encode()).hexdigest()[:8]}"
            scene_id = f"scene:{gap['rhythm']}.{gap['scene']}"
            graph.store.create_relation(
                source_id=gap_id,
                target_id=scene_id,
                relation_type="gap_blocks_scene",
                metadata={"severity": gap["severity"], "kind": gap["kind"]},
            )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_kg_seed.py -v -k "scene_exercises or gap_blocks"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/server/handlers/rhythm.py tests/unit/test_kg_seed.py
git commit -m "feat(kg): add scene_exercises_story and gap_blocks_scene relations"
```

---

## Chunk 7: Documentation & Grammar

### Task 15: Update grammar reference

**Files:**
- Modify: `docs/reference/grammar.md`

- [ ] **Step 1: Add `kind:` to rhythm phase grammar**

Find the rhythm grammar section and update the phase production:

```
phase IDENTIFIER COLON NEWLINE INDENT
  [kind COLON PHASE_KIND NEWLINE]
  (scene ...)*
DEDENT

PHASE_KIND = "onboarding" | "active" | "periodic" | "ambient" | "offboarding"
```

- [ ] **Step 2: Commit**

```bash
git add docs/reference/grammar.md
git commit -m "docs: add phase kind to rhythm grammar reference"
```

---

### Task 16: Update rhythm documentation

**Files:**
- Modify: `docs/reference/rhythms.md`

- [ ] **Step 1: Add phase kinds section**

Add a section documenting phase kinds with examples. Add sections for gaps and lifecycle operations with usage examples.

- [ ] **Step 2: Commit**

```bash
git add docs/reference/rhythms.md
git commit -m "docs: document phase kinds, gaps analysis, and lifecycle operation"
```

---

### Task 17: Final integration test and lint

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All PASS

- [ ] **Step 2: Run linter**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 3: Run type checker**

Run: `mypy src/dazzle`
Expected: No new errors

- [ ] **Step 4: Final commit if any lint fixes**

```bash
git add -u
git commit -m "chore: lint and type fixes for stories-scenes operating model"
```
