# Rhythm & Scene Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `rhythm`, `phase`, and `scene` as first-class DSL constructs with parser, IR, linker validation, static evaluation, and 5 MCP operations.

**Architecture:** New DSL keywords (`rhythm`, `phase`, `scene`) are tokenized by the lexer, parsed by a new `RhythmParserMixin`, stored as `RhythmSpec`/`PhaseSpec`/`SceneSpec` in the IR, validated by the linker (persona, surface, entity cross-references), and exposed via a `rhythm` MCP tool with propose/evaluate/coverage/get/list operations.

**Tech Stack:** Python 3.12, Pydantic v2, existing DAZZLE parser infrastructure, MCP server handler pattern.

**Design doc:** `docs/plans/2026-03-11-rhythm-scene-evaluation-design.md`

---

### Task 1: IR Types — SceneSpec, PhaseSpec, RhythmSpec

**Files:**
- Create: `src/dazzle/core/ir/rhythm.py`
- Test: `tests/unit/test_rhythm_ir.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_ir.py
"""Tests for rhythm IR types."""

from dazzle.core.ir.rhythm import PhaseSpec, RhythmSpec, SceneSpec


def test_scene_spec_minimal():
    """Scene requires name and surface."""
    scene = SceneSpec(name="browse", surface="course_list")
    assert scene.name == "browse"
    assert scene.surface == "course_list"
    assert scene.actions == []
    assert scene.entity is None
    assert scene.expects is None
    assert scene.story is None
    assert scene.title is None


def test_scene_spec_full():
    """Scene with all optional fields."""
    scene = SceneSpec(
        name="enroll",
        title="Enroll in Course",
        surface="course_detail",
        actions=["submit"],
        entity="Enrollment",
        expects="enrollment_confirmed",
        story="enroll_story",
    )
    assert scene.title == "Enroll in Course"
    assert scene.actions == ["submit"]
    assert scene.entity == "Enrollment"
    assert scene.expects == "enrollment_confirmed"
    assert scene.story == "enroll_story"


def test_scene_spec_frozen():
    """SceneSpec is immutable."""
    scene = SceneSpec(name="browse", surface="course_list")
    try:
        scene.name = "other"
        assert False, "Should have raised"
    except Exception:
        pass


def test_phase_spec():
    """Phase groups scenes."""
    scenes = [
        SceneSpec(name="browse", surface="course_list"),
        SceneSpec(name="enroll", surface="course_detail"),
    ]
    phase = PhaseSpec(name="discovery", scenes=scenes)
    assert phase.name == "discovery"
    assert len(phase.scenes) == 2


def test_rhythm_spec_minimal():
    """Rhythm requires name and persona."""
    rhythm = RhythmSpec(name="onboarding", persona="new_user")
    assert rhythm.name == "onboarding"
    assert rhythm.persona == "new_user"
    assert rhythm.cadence is None
    assert rhythm.phases == []
    assert rhythm.title is None


def test_rhythm_spec_full():
    """Rhythm with phases, cadence, title."""
    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                scenes=[SceneSpec(name="browse", surface="course_list")],
            ),
            PhaseSpec(
                name="mastery",
                scenes=[SceneSpec(name="progress", surface="dashboard")],
            ),
        ],
    )
    assert rhythm.title == "New User Onboarding"
    assert rhythm.cadence == "quarterly"
    assert len(rhythm.phases) == 2
    assert rhythm.phases[0].scenes[0].name == "browse"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_ir.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.ir.rhythm'`

**Step 3: Write minimal implementation**

```python
# src/dazzle/core/ir/rhythm.py
"""
Rhythm specification types for DAZZLE longitudinal UX evaluation.

Rhythms are non-Turing-complete journey maps that describe a single
persona's path through the app over temporal phases. Each phase
contains scenes — discrete actions on specific surfaces.

Structural references (persona, surface, entity, story) are validated
at link time. Semantic hints (cadence, action, expects) are free-form
strings interpreted by AI agents per domain.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .location import SourceLocation


class SceneSpec(BaseModel):
    """
    A single scene — a persona action on a surface within a rhythm phase.

    Attributes:
        name: Scene identifier (unique within rhythm)
        title: Human-readable title
        surface: Surface name this scene exercises (validated at link time)
        actions: Free-form action verbs (agent-interpreted)
        entity: Optional entity reference (validated at link time)
        expects: Free-form expected outcome (agent-interpreted)
        story: Optional link to an existing story (validated at link time)
        source: Source location for error reporting
    """

    name: str = Field(..., description="Scene identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    surface: str = Field(..., description="Surface this scene exercises")
    actions: list[str] = Field(default_factory=list, description="Action verbs")
    entity: str | None = Field(default=None, description="Entity reference")
    expects: str | None = Field(default=None, description="Expected outcome")
    story: str | None = Field(default=None, description="Link to existing story")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class PhaseSpec(BaseModel):
    """
    A named phase within a rhythm — groups scenes in temporal order.

    Attributes:
        name: Phase identifier (unique within rhythm)
        scenes: Ordered list of scenes in this phase
        source: Source location for error reporting
    """

    name: str = Field(..., description="Phase identifier")
    scenes: list[SceneSpec] = Field(default_factory=list, description="Scenes in phase")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class RhythmSpec(BaseModel):
    """
    A rhythm — a longitudinal journey map for a persona through the app.

    Attributes:
        name: Rhythm identifier
        title: Human-readable title
        persona: Persona reference (validated at link time)
        cadence: Free-form temporal frequency hint (agent-interpreted)
        phases: Ordered list of phases in the journey
        source: Source location for error reporting
    """

    name: str = Field(..., description="Rhythm identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    persona: str = Field(..., description="Persona this rhythm is for")
    cadence: str | None = Field(default=None, description="Temporal frequency hint")
    phases: list[PhaseSpec] = Field(default_factory=list, description="Journey phases")
    source: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_rhythm_ir.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add src/dazzle/core/ir/rhythm.py tests/unit/test_rhythm_ir.py
git commit -m "feat: add rhythm/phase/scene IR types (#444)"
```

---

### Task 2: Wire IR into Module, AppSpec, and Exports

**Files:**
- Modify: `src/dazzle/core/ir/__init__.py:551-559` (add imports after stories block)
- Modify: `src/dazzle/core/ir/__init__.py:878-884` (add to __all__ after stories)
- Modify: `src/dazzle/core/ir/module.py:136` (add rhythms field after stories)
- Modify: `src/dazzle/core/ir/appspec.py:166` (add rhythms field after notifications)

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_ir_integration.py
"""Tests for rhythm IR integration with ModuleFragment and AppSpec."""

from dazzle.core import ir


def test_rhythm_exported_from_ir():
    """RhythmSpec, PhaseSpec, SceneSpec exported from ir package."""
    assert hasattr(ir, "RhythmSpec")
    assert hasattr(ir, "PhaseSpec")
    assert hasattr(ir, "SceneSpec")


def test_module_fragment_has_rhythms():
    """ModuleFragment has rhythms field."""
    frag = ir.ModuleFragment()
    assert frag.rhythms == []


def test_module_fragment_with_rhythm():
    """ModuleFragment can hold rhythms."""
    rhythm = ir.RhythmSpec(name="onboarding", persona="new_user")
    frag = ir.ModuleFragment(rhythms=[rhythm])
    assert len(frag.rhythms) == 1
    assert frag.rhythms[0].name == "onboarding"


def test_appspec_has_rhythms():
    """AppSpec has rhythms field."""
    spec = ir.AppSpec(
        name="test",
        title="Test",
        domain=ir.DomainSpec(entities=[]),
    )
    assert spec.rhythms == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_ir_integration.py -v`
Expected: FAIL with `AttributeError: module 'dazzle.core.ir' has no attribute 'RhythmSpec'`

**Step 3: Make changes**

In `src/dazzle/core/ir/__init__.py`, after line 559 (after stories imports):
```python
# Rhythms (v0.39.0 Longitudinal UX Evaluation)
from .rhythm import PhaseSpec, RhythmSpec, SceneSpec
```

In `src/dazzle/core/ir/__init__.py`, in `__all__` after line 884 (after StoryTrigger):
```python
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    "RhythmSpec",
    "PhaseSpec",
    "SceneSpec",
```

In `src/dazzle/core/ir/module.py`, after line 136 (`stories` field):
```python
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    rhythms: list[RhythmSpec] = Field(default_factory=list)
```

Also add the import at the top of `module.py` — find where `StorySpec` is imported and add `RhythmSpec` nearby.

In `src/dazzle/core/ir/appspec.py`, after line 166 (`notifications` field):
```python
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    rhythms: list[RhythmSpec] = Field(default_factory=list)
```

Also add the import at the top of `appspec.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_rhythm_ir_integration.py tests/unit/test_rhythm_ir.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add src/dazzle/core/ir/__init__.py src/dazzle/core/ir/module.py src/dazzle/core/ir/appspec.py tests/unit/test_rhythm_ir_integration.py
git commit -m "feat: wire rhythm IR into ModuleFragment and AppSpec (#444)"
```

---

### Task 3: Lexer — Add RHYTHM, PHASE, SCENE Tokens

**Files:**
- Modify: `src/dazzle/core/lexer.py:254` (add tokens after UNLESS)
- Test: `tests/unit/test_rhythm_lexer.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_lexer.py
"""Tests for rhythm lexer tokens."""

from pathlib import Path

from dazzle.core.lexer import TokenType, tokenize


def test_rhythm_keyword_tokenized():
    """'rhythm' is tokenized as RHYTHM."""
    tokens = tokenize("rhythm onboarding", Path("test.dsl"))
    assert tokens[0].type == TokenType.RHYTHM
    assert tokens[0].value == "rhythm"


def test_phase_keyword_tokenized():
    """'phase' is tokenized as PHASE."""
    tokens = tokenize("phase discovery", Path("test.dsl"))
    assert tokens[0].type == TokenType.PHASE
    assert tokens[0].value == "phase"


def test_scene_keyword_tokenized():
    """'scene' is tokenized as SCENE."""
    tokens = tokenize("scene browse", Path("test.dsl"))
    assert tokens[0].type == TokenType.SCENE
    assert tokens[0].value == "scene"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_lexer.py -v`
Expected: FAIL with `AttributeError: 'TokenType' object has no attribute 'RHYTHM'`

**Step 3: Add tokens to lexer**

In `src/dazzle/core/lexer.py`, after line 254 (after `UNLESS = "unless"`):
```python
    # v0.39.0 Rhythm DSL Keywords
    RHYTHM = "rhythm"
    PHASE = "phase"
    SCENE = "scene"
```

The KEYWORDS dict auto-generates from TokenType values, so no further changes needed.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_rhythm_lexer.py -v`
Expected: PASS (all 3 tests)

**Step 5: Run full test suite to check for conflicts**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: PASS — no existing DSL uses "rhythm", "phase", or "scene" as identifiers in a way that would conflict.

**Note:** If "phase" or "scene" conflict with existing identifier usage, they'll need to be handled in the parser dispatch (only match when at top-level or within rhythm context). Check the error output carefully.

**Step 6: Commit**

```bash
git add src/dazzle/core/lexer.py tests/unit/test_rhythm_lexer.py
git commit -m "feat: add RHYTHM, PHASE, SCENE lexer tokens (#444)"
```

---

### Task 4: Parser Mixin — RhythmParserMixin

**Files:**
- Create: `src/dazzle/core/dsl_parser_impl/rhythm.py`
- Test: `tests/unit/test_rhythm_parser.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_parser.py
"""Tests for rhythm DSL parser."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl


def test_parse_minimal_rhythm():
    """Parse rhythm with one phase and one scene."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "New User Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse Courses":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert len(fragment.rhythms) == 1
    rhythm = fragment.rhythms[0]
    assert rhythm.name == "onboarding"
    assert rhythm.title == "New User Onboarding"
    assert rhythm.persona == "new_user"
    assert len(rhythm.phases) == 1
    assert rhythm.phases[0].name == "discovery"
    assert len(rhythm.phases[0].scenes) == 1
    scene = rhythm.phases[0].scenes[0]
    assert scene.name == "browse"
    assert scene.title == "Browse Courses"
    assert scene.surface == "course_list"


def test_parse_rhythm_with_cadence():
    """Parse rhythm with cadence hint."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user
  cadence: "quarterly"

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    rhythm = fragment.rhythms[0]
    assert rhythm.cadence == "quarterly"


def test_parse_scene_with_all_fields():
    """Parse scene with action, entity, expects, story."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase engagement:
    scene enroll "Enroll in Course":
      on: course_detail
      action: submit, browse
      entity: Enrollment
      expects: "enrollment_confirmed"
      story: enroll_story
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    scene = fragment.rhythms[0].phases[0].scenes[0]
    assert scene.surface == "course_detail"
    assert scene.actions == ["submit", "browse"]
    assert scene.entity == "Enrollment"
    assert scene.expects == "enrollment_confirmed"
    assert scene.story == "enroll_story"


def test_parse_multiple_phases():
    """Parse rhythm with multiple phases each containing scenes."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list

  phase engagement:
    scene enroll "Enroll":
      on: course_detail
    scene study "Study":
      on: module_view

  phase mastery:
    scene progress "Check Progress":
      on: dashboard
"""
    _mod, _app, _title, _config, _uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    rhythm = fragment.rhythms[0]
    assert len(rhythm.phases) == 3
    assert rhythm.phases[0].name == "discovery"
    assert len(rhythm.phases[0].scenes) == 1
    assert rhythm.phases[1].name == "engagement"
    assert len(rhythm.phases[1].scenes) == 2
    assert rhythm.phases[2].name == "mastery"
    assert len(rhythm.phases[2].scenes) == 1


def test_parse_rhythm_missing_persona_raises():
    """Rhythm without persona raises parse error."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    import pytest
    with pytest.raises(Exception, match="persona"):
        parse_dsl(dsl, Path("test.dsl"))


def test_parse_scene_missing_on_raises():
    """Scene without 'on' (surface) raises parse error."""
    dsl = """\
module test_app
app test "Test"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      action: browse
"""
    import pytest
    with pytest.raises(Exception, match="on"):
        parse_dsl(dsl, Path("test.dsl"))
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_parser.py -v`
Expected: FAIL — parser doesn't know about RHYTHM token yet

**Step 3: Write the parser mixin**

```python
# src/dazzle/core/dsl_parser_impl/rhythm.py
"""
Rhythm parser mixin for DAZZLE DSL.

Parses rhythm blocks with phase/scene structure.

DSL Syntax (v0.39.0):
    rhythm onboarding "New User Onboarding":
      persona: new_user
      cadence: "quarterly"

      phase discovery:
        scene browse "Browse Courses":
          on: course_list
          action: filter, browse
          entity: Course
          expects: "visible_results"
          story: browse_courses
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class RhythmParserMixin:
    """Parser mixin for rhythm blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _source_location: Any

    def parse_rhythm(self) -> ir.RhythmSpec:
        """
        Parse a rhythm block.

        Grammar:
            rhythm IDENTIFIER STRING? COLON NEWLINE INDENT
              persona COLON IDENTIFIER NEWLINE
              [cadence COLON STRING NEWLINE]
              (phase IDENTIFIER COLON NEWLINE INDENT
                (scene IDENTIFIER STRING? COLON NEWLINE INDENT
                  on COLON IDENTIFIER NEWLINE
                  [action COLON identifier_list NEWLINE]
                  [entity COLON IDENTIFIER NEWLINE]
                  [expects COLON STRING NEWLINE]
                  [story COLON IDENTIFIER NEWLINE]
                DEDENT)*
              DEDENT)*
            DEDENT
        """
        loc = self._source_location()

        # rhythm name "Title":
        name = self.expect_identifier_or_keyword().value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        persona = None
        cadence = None
        phases: list[ir.PhaseSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.PERSONA):
                self.advance()
                self.expect(TokenType.COLON)
                persona = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.PHASE):
                self.advance()
                phases.append(self._parse_rhythm_phase())

            else:
                # Handle cadence and unknown fields via identifier
                token = self.current_token()
                if token.value == "cadence":
                    self.advance()
                    self.expect(TokenType.COLON)
                    cadence = self.expect(TokenType.STRING).value
                    self.skip_newlines()
                else:
                    self.advance()
                    if self.match(TokenType.COLON):
                        self.advance()
                        self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        if persona is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Rhythm missing required 'persona' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.RhythmSpec(
            name=name,
            title=title,
            persona=persona,
            cadence=cadence,
            phases=phases,
            source=loc,
        )

    def _parse_rhythm_phase(self) -> ir.PhaseSpec:
        """Parse a phase block within a rhythm."""
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        scenes: list[ir.SceneSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SCENE):
                self.advance()
                scenes.append(self._parse_rhythm_scene())
            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        return ir.PhaseSpec(name=name, scenes=scenes, source=loc)

    def _parse_rhythm_scene(self) -> ir.SceneSpec:
        """Parse a scene block within a phase."""
        loc = self._source_location()

        name = self.expect_identifier_or_keyword().value
        title = None
        if self.match(TokenType.STRING):
            title = self.advance().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        surface = None
        actions: list[str] = []
        entity = None
        expects = None
        story = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "on":
                self.advance()
                self.expect(TokenType.COLON)
                surface = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "action":
                self.advance()
                self.expect(TokenType.COLON)
                actions = self._parse_rhythm_identifier_list()
                self.skip_newlines()

            elif field_name == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "expects":
                self.advance()
                self.expect(TokenType.COLON)
                expects = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "story":
                self.advance()
                self.expect(TokenType.COLON)
                story = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_rhythm_field()

        self.expect(TokenType.DEDENT)

        if surface is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Scene missing required 'on' field (surface reference)",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.SceneSpec(
            name=name,
            title=title,
            surface=surface,
            actions=actions,
            entity=entity,
            expects=expects,
            story=story,
            source=loc,
        )

    def _parse_rhythm_identifier_list(self) -> list[str]:
        """Parse comma-separated identifiers on a single line: submit, browse."""
        items: list[str] = []
        items.append(self.expect_identifier_or_keyword().value)

        while self.match(TokenType.COMMA):
            self.advance()
            items.append(self.expect_identifier_or_keyword().value)

        return items

    def _skip_rhythm_field(self) -> None:
        """Skip tokens until we reach the next field or end of block."""
        while not self.match(
            TokenType.PHASE,
            TokenType.SCENE,
            TokenType.PERSONA,
            TokenType.DEDENT,
            TokenType.EOF,
            TokenType.NEWLINE,
        ):
            self.advance()
        self.skip_newlines()
```

**Step 4: Register the mixin**

In `src/dazzle/core/dsl_parser_impl/__init__.py`:

After line 41 (after `from .story import StoryParserMixin`):
```python
from .rhythm import RhythmParserMixin
```

In the Parser class (after line 64, after `StoryParserMixin`):
```python
    RhythmParserMixin,
```

In the parse() loop (after line 185, after the STORY dispatch):
```python
            # v0.39.0 Rhythms
            elif self.match(TokenType.RHYTHM):
                self.advance()  # consume 'rhythm' token
                rhythm = self.parse_rhythm()
                fragment = _updated(fragment, rhythms=[*fragment.rhythms, rhythm])
```

In `__all__` (after line 398, after `"StoryParserMixin"`):
```python
    "RhythmParserMixin",
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_rhythm_parser.py -v`
Expected: PASS (all 6 tests)

**Step 6: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: PASS — no regressions

**Step 7: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/rhythm.py src/dazzle/core/dsl_parser_impl/__init__.py tests/unit/test_rhythm_parser.py
git commit -m "feat: add rhythm/phase/scene parser (#444)"
```

---

### Task 5: Linker — Symbol Registration and Cross-Reference Validation

**Files:**
- Modify: `src/dazzle/core/linker_impl.py:97-122` (ProcessSymbols), `~489` (symbol collection), `~829+` (validate_references), `~1113` (build_appspec)
- Test: `tests/unit/test_rhythm_linker.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_linker.py
"""Tests for rhythm linker validation."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec


def _parse_and_link(dsl: str) -> tuple:
    """Parse DSL and build appspec, returning (appspec, errors)."""
    mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    from dazzle.core.ir import ModuleIR
    module = ModuleIR(
        name=mod_name or "test",
        file=Path("test.dsl"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )
    return build_appspec([module])


def test_rhythm_collected_in_appspec():
    """Rhythm appears in AppSpec after linking."""
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

entity Course "Course":
  id: uuid pk
  title: str(200) required

surface course_list "Courses":
  uses entity Course
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    appspec = _parse_and_link(dsl)
    assert len(appspec.rhythms) == 1
    assert appspec.rhythms[0].name == "onboarding"


def test_rhythm_invalid_persona_error():
    """Rhythm referencing nonexistent persona produces error."""
    dsl = """\
module test_app
app test "Test"

surface course_list "Courses":
  uses entity Course
  mode: list
  section main:
    field title "Title"

entity Course "Course":
  id: uuid pk
  title: str(200) required

rhythm onboarding "Onboarding":
  persona: nonexistent_persona

  phase discovery:
    scene browse "Browse":
      on: course_list
"""
    with pytest.raises(Exception, match="persona|nonexistent"):
        _parse_and_link(dsl)


def test_rhythm_invalid_surface_error():
    """Scene referencing nonexistent surface produces error."""
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: nonexistent_surface
"""
    with pytest.raises(Exception, match="surface|nonexistent"):
        _parse_and_link(dsl)


def test_rhythm_invalid_entity_error():
    """Scene referencing nonexistent entity produces error."""
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene enroll "Enroll":
      on: course_list
      entity: NonexistentEntity
"""
    with pytest.raises(Exception, match="entity|Nonexistent"):
        _parse_and_link(dsl)


def test_rhythm_duplicate_scene_name_error():
    """Two scenes with same name in one rhythm produces error."""
    dsl = """\
module test_app
app test "Test"

persona new_user "New User":
  goals:
    - "Learn things"

surface course_list "Courses":
  mode: list
  section main:
    field title "Title"

rhythm onboarding "Onboarding":
  persona: new_user

  phase discovery:
    scene browse "Browse":
      on: course_list

  phase engagement:
    scene browse "Browse Again":
      on: course_list
"""
    with pytest.raises(Exception, match="[Dd]uplicate.*scene|scene.*browse.*already"):
        _parse_and_link(dsl)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_linker.py -v`
Expected: FAIL — rhythms not collected or validated

**Step 3: Modify linker_impl.py**

Add to `ProcessSymbols` (after line 103):
```python
    rhythms: dict[str, ir.RhythmSpec] = field(default_factory=dict)

    def add_rhythm(
        self, rhythm: ir.RhythmSpec, module_name: str, sources: dict[str, str] | None = None
    ) -> None:
        _add_symbol(
            self.rhythms, rhythm.name, rhythm, "rhythm", module_name,
            sources if sources is not None else {},
        )
```

Add delegated property on SymbolTable (near other `@property` methods):
```python
    @property
    def rhythms(self) -> dict[str, ir.RhythmSpec]:
        return self._process.rhythms

    def add_rhythm(self, rhythm: ir.RhythmSpec, module_name: str) -> None:
        self._process.add_rhythm(rhythm, module_name, self.symbol_sources)
```

Add to symbol collection (after line 489, after stories):
```python
        # Add rhythms (v0.39.0)
        for rhythm in module.fragment.rhythms:
            symbols.add_rhythm(rhythm, module.name)
```

Add to `validate_references()` (near the end, before `return errors`):
```python
    # Validate rhythm references (v0.39.0)
    for rhythm_name, rhythm in symbols.rhythms.items():
        # Persona must exist
        if rhythm.persona not in symbols.personas:
            errors.append(
                f"Rhythm '{rhythm_name}' references unknown persona '{rhythm.persona}'"
            )

        # Track scene names for uniqueness within rhythm
        seen_scenes: set[str] = set()
        for phase in rhythm.phases:
            for scene in phase.scenes:
                # Scene name unique within rhythm
                if scene.name in seen_scenes:
                    errors.append(
                        f"Rhythm '{rhythm_name}' has duplicate scene name '{scene.name}'"
                    )
                seen_scenes.add(scene.name)

                # Surface must exist
                if scene.surface not in symbols.surfaces:
                    errors.append(
                        f"Rhythm '{rhythm_name}' scene '{scene.name}' references "
                        f"unknown surface '{scene.surface}'"
                    )

                # Entity must exist (if specified)
                if scene.entity and scene.entity not in symbols.entities:
                    errors.append(
                        f"Rhythm '{rhythm_name}' scene '{scene.name}' references "
                        f"unknown entity '{scene.entity}'"
                    )

                # Story must exist (if specified)
                if scene.story and scene.story not in symbols.stories:
                    errors.append(
                        f"Rhythm '{rhythm_name}' scene '{scene.name}' references "
                        f"unknown story '{scene.story}'"
                    )
```

Add to `build_appspec` (near line 1113, after stories):
```python
        rhythms=list(symbols.rhythms.values()),  # v0.39.0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_rhythm_linker.py -v`
Expected: PASS (all 5 tests)

**Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: PASS

**Step 6: Commit**

```bash
git add src/dazzle/core/linker_impl.py tests/unit/test_rhythm_linker.py
git commit -m "feat: add rhythm linker validation (#444)"
```

---

### Task 6: MCP Handler — rhythm operations

**Files:**
- Create: `src/dazzle/mcp/server/handlers/rhythm.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py:316+` (add handler), `~1780` (register in map)
- Modify: `src/dazzle/mcp/server/tools_consolidated.py:285+` (add tool schema)
- Test: `tests/unit/test_rhythm_mcp.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_rhythm_mcp.py
"""Tests for rhythm MCP handler."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_appspec():
    """Create a mock AppSpec with rhythms."""
    from dazzle.core.ir.rhythm import PhaseSpec, RhythmSpec, SceneSpec

    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                scenes=[
                    SceneSpec(name="browse", title="Browse Courses", surface="course_list"),
                    SceneSpec(
                        name="enroll",
                        title="Enroll",
                        surface="course_detail",
                        actions=["submit"],
                        entity="Enrollment",
                    ),
                ],
            ),
        ],
    )
    spec = MagicMock()
    spec.rhythms = [rhythm]
    spec.personas = [MagicMock(id="new_user", name="New User")]
    spec.surfaces = [MagicMock(name="course_list"), MagicMock(name="course_detail")]
    spec.domain.entities = [MagicMock(name="Enrollment")]
    return spec


def test_list_rhythms(mock_appspec):
    """list operation returns rhythm summaries."""
    from dazzle.mcp.server.handlers.rhythm import list_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = list_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert len(data["rhythms"]) == 1
        assert data["rhythms"][0]["name"] == "onboarding"
        assert data["rhythms"][0]["persona"] == "new_user"


def test_get_rhythm(mock_appspec):
    """get operation returns full rhythm detail."""
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert data["name"] == "onboarding"
        assert data["persona"] == "new_user"
        assert len(data["phases"]) == 1
        assert len(data["phases"][0]["scenes"]) == 2


def test_get_rhythm_not_found(mock_appspec):
    """get operation with unknown name returns error."""
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "nonexistent"})
        data = json.loads(result)
        assert "error" in data


def test_evaluate_rhythm(mock_appspec):
    """evaluate operation returns gap analysis."""
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = evaluate_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert "rhythm" in data
        assert "checks" in data


def test_coverage_rhythms(mock_appspec):
    """coverage operation returns persona/surface coverage."""
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert "personas_with_rhythms" in data
        assert "personas_without_rhythms" in data
        assert "surfaces_exercised" in data
        assert "surfaces_unexercised" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rhythm_mcp.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Create handler**

```python
# src/dazzle/mcp/server/handlers/rhythm.py
"""
Rhythm tool handlers.

Handles rhythm listing, retrieval, evaluation, coverage, and proposal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import error_response, load_project_appspec, wrap_handler_errors


@wrap_handler_errors
def list_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all rhythms in the project."""
    app_spec = load_project_appspec(project_root)

    rhythms = []
    for r in app_spec.rhythms:
        rhythms.append({
            "name": r.name,
            "title": r.title,
            "persona": r.persona,
            "cadence": r.cadence,
            "phase_count": len(r.phases),
            "scene_count": sum(len(p.scenes) for p in r.phases),
        })

    return json.dumps({"rhythms": rhythms}, indent=2)


@wrap_handler_errors
def get_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get full details of a specific rhythm."""
    app_spec = load_project_appspec(project_root)
    name = args.get("name")

    for r in app_spec.rhythms:
        if r.name == name:
            return json.dumps({
                "name": r.name,
                "title": r.title,
                "persona": r.persona,
                "cadence": r.cadence,
                "phases": [
                    {
                        "name": p.name,
                        "scenes": [
                            {
                                "name": s.name,
                                "title": s.title,
                                "surface": s.surface,
                                "actions": s.actions,
                                "entity": s.entity,
                                "expects": s.expects,
                                "story": s.story,
                            }
                            for s in p.scenes
                        ],
                    }
                    for p in r.phases
                ],
            }, indent=2)

    return error_response(f"Rhythm '{name}' not found")


@wrap_handler_errors
def evaluate_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Evaluate a rhythm — static analysis of completeness."""
    app_spec = load_project_appspec(project_root)
    name = args.get("name")

    rhythm = None
    for r in app_spec.rhythms:
        if r.name == name:
            rhythm = r
            break

    if rhythm is None:
        return error_response(f"Rhythm '{name}' not found")

    # Build lookup sets
    surface_names = {s.name for s in app_spec.surfaces}
    entity_names = {e.name for e in app_spec.domain.entities}
    persona_ids = {p.id for p in app_spec.personas}

    # Surface entity mapping: which surfaces use which entities
    surface_entities: dict[str, str | None] = {}
    for s in app_spec.surfaces:
        surface_entities[s.name] = getattr(s, "entity_ref", None)

    checks: list[dict[str, Any]] = []

    # Check persona exists
    checks.append({
        "check": "persona_exists",
        "target": rhythm.persona,
        "pass": rhythm.persona in persona_ids,
    })

    for phase in rhythm.phases:
        for scene in phase.scenes:
            # Check surface exists
            checks.append({
                "check": "surface_exists",
                "phase": phase.name,
                "scene": scene.name,
                "target": scene.surface,
                "pass": scene.surface in surface_names,
            })

            # Check entity exists (if referenced)
            if scene.entity:
                entity_exists = scene.entity in entity_names
                checks.append({
                    "check": "entity_exists",
                    "phase": phase.name,
                    "scene": scene.name,
                    "target": scene.entity,
                    "pass": entity_exists,
                })

                # Check surface uses the referenced entity
                if scene.surface in surface_entities:
                    surf_entity = surface_entities[scene.surface]
                    entity_match = surf_entity == scene.entity if surf_entity else False
                    checks.append({
                        "check": "surface_entity_match",
                        "phase": phase.name,
                        "scene": scene.name,
                        "surface": scene.surface,
                        "entity": scene.entity,
                        "surface_entity": surf_entity,
                        "pass": entity_match,
                    })

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)

    return json.dumps({
        "rhythm": name,
        "summary": f"{passed}/{total} checks passed",
        "checks": checks,
    }, indent=2)


@wrap_handler_errors
def coverage_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse persona and surface coverage across all rhythms."""
    app_spec = load_project_appspec(project_root)

    all_persona_ids = {p.id for p in app_spec.personas}
    all_surface_names = {s.name for s in app_spec.surfaces}

    personas_with_rhythms: set[str] = set()
    surfaces_exercised: set[str] = set()

    for r in app_spec.rhythms:
        personas_with_rhythms.add(r.persona)
        for phase in r.phases:
            for scene in phase.scenes:
                surfaces_exercised.add(scene.surface)

    return json.dumps({
        "total_personas": len(all_persona_ids),
        "total_surfaces": len(all_surface_names),
        "total_rhythms": len(app_spec.rhythms),
        "personas_with_rhythms": sorted(personas_with_rhythms),
        "personas_without_rhythms": sorted(all_persona_ids - personas_with_rhythms),
        "surfaces_exercised": sorted(surfaces_exercised),
        "surfaces_unexercised": sorted(all_surface_names - surfaces_exercised),
    }, indent=2)


@wrap_handler_errors
def propose_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Propose a rhythm for a given persona based on app analysis.

    Analyses the app's surfaces, entities, and persona to generate a
    rhythm DSL block that covers the persona's likely journey.
    """
    app_spec = load_project_appspec(project_root)
    persona_id = args.get("persona")

    if not persona_id:
        return error_response("'persona' parameter required for propose")

    # Find the persona
    persona = None
    for p in app_spec.personas:
        if p.id == persona_id:
            persona = p
            break

    if persona is None:
        return error_response(f"Persona '{persona_id}' not found")

    # Group surfaces by their entity to form natural phases
    # Phase 1: list surfaces (discovery) → Phase 2: detail/form surfaces (engagement)
    list_surfaces: list[str] = []
    detail_surfaces: list[str] = []

    for s in app_spec.surfaces:
        mode = getattr(s, "mode", None)
        if mode == "list":
            list_surfaces.append(s.name)
        else:
            detail_surfaces.append(s.name)

    # Build DSL output
    lines = [
        f'rhythm {persona_id}_journey "{getattr(persona, "name", persona_id)} Journey":',
        f"  persona: {persona_id}",
        "",
    ]

    if list_surfaces:
        lines.append("  phase discovery:")
        for sname in list_surfaces:
            safe = sname.replace(" ", "_").lower()
            lines.append(f'    scene browse_{safe} "Browse {sname}":')
            lines.append(f"      on: {sname}")
            lines.append("      action: browse")
            lines.append("")

    if detail_surfaces:
        lines.append("  phase engagement:")
        for sname in detail_surfaces:
            safe = sname.replace(" ", "_").lower()
            entity_ref = None
            for s in app_spec.surfaces:
                if s.name == sname:
                    entity_ref = getattr(s, "entity_ref", None)
                    break
            lines.append(f'    scene use_{safe} "Use {sname}":')
            lines.append(f"      on: {sname}")
            lines.append("      action: submit")
            if entity_ref:
                lines.append(f"      entity: {entity_ref}")
            lines.append("")

    return json.dumps({
        "persona": persona_id,
        "proposed_dsl": "\n".join(lines),
    }, indent=2)
```

**Step 4: Register in handlers_consolidated.py**

After line 349 (after `handle_story`):
```python
# =============================================================================
# Rhythm Handler
# =============================================================================


def handle_rhythm(arguments: dict[str, Any]) -> str:
    """Handle consolidated rhythm operations."""
    from .handlers.rhythm import (
        coverage_rhythms_handler,
        evaluate_rhythm_handler,
        get_rhythm_handler,
        list_rhythms_handler,
        propose_rhythm_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    ops: dict[str, Callable[..., str]] = {
        "propose": propose_rhythm_handler,
        "evaluate": evaluate_rhythm_handler,
        "coverage": coverage_rhythms_handler,
        "get": get_rhythm_handler,
        "list": list_rhythms_handler,
    }

    handler = ops.get(operation)
    if handler is None:
        return unknown_op_response(operation, "rhythm")
    return handler(project_path, arguments)
```

At line ~1780, add to CONSOLIDATED_TOOL_HANDLERS:
```python
    "rhythm": handle_rhythm,
```

**Step 5: Register tool schema in tools_consolidated.py**

After the story tool schema (after line ~340):
```python
        Tool(
            name="rhythm",
            description="Rhythm operations: propose, evaluate, coverage, get, list. Rhythms are longitudinal persona journey maps through the app, organized into temporal phases containing scenes (actions on surfaces).",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["propose", "evaluate", "coverage", "get", "list"],
                        "description": "Operation to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Rhythm name (for get, evaluate)",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona ID (for propose)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
```

**Step 6: Run tests**

Run: `pytest tests/unit/test_rhythm_mcp.py -v`
Expected: PASS (all 5 tests)

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: PASS

**Step 7: Commit**

```bash
git add src/dazzle/mcp/server/handlers/rhythm.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py tests/unit/test_rhythm_mcp.py
git commit -m "feat: add rhythm MCP tool with propose/evaluate/coverage/get/list (#444)"
```

---

### Task 7: Grammar Documentation

**Files:**
- Modify: `docs/reference/grammar.md`

**Step 1: Add rhythm EBNF to grammar reference**

Find the section for story syntax and add after it:

```markdown
### Rhythm (v0.39.0)

```ebnf
rhythm_block = "rhythm" IDENTIFIER [STRING] ":" NEWLINE INDENT
    "persona" ":" IDENTIFIER NEWLINE
    ["cadence" ":" STRING NEWLINE]
    phase_block*
  DEDENT

phase_block = "phase" IDENTIFIER ":" NEWLINE INDENT
    scene_block*
  DEDENT

scene_block = "scene" IDENTIFIER [STRING] ":" NEWLINE INDENT
    "on" ":" IDENTIFIER NEWLINE
    ["action" ":" identifier_list NEWLINE]
    ["entity" ":" IDENTIFIER NEWLINE]
    ["expects" ":" STRING NEWLINE]
    ["story" ":" IDENTIFIER NEWLINE]
  DEDENT

identifier_list = IDENTIFIER ("," IDENTIFIER)*
```
```

**Step 2: Commit**

```bash
git add docs/reference/grammar.md
git commit -m "docs: add rhythm/phase/scene grammar reference (#444)"
```

---

### Task 8: Quality Checks and Final Verification

**Step 1: Lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

**Step 2: Type check**

Run: `mypy src/dazzle`
Fix any type errors in changed files.

**Step 3: Full test suite**

Run: `pytest tests/ -m "not e2e" -x`
Expected: PASS — all tests including new rhythm tests

**Step 4: Verify CLAUDE.md constructs list**

Update `/Volumes/SSD/Dazzle/.claude/CLAUDE.md` to add `rhythm` to the DSL constructs list:

Find `**Constructs**:` line and add `rhythm` to the list.

**Step 5: Final commit if needed**

```bash
git add -A
git commit -m "chore: lint, type fixes, and CLAUDE.md update for rhythm (#444)"
```

---

### Task 9: Close Issue

**Step 1: Push all commits**

```bash
git push
```

**Step 2: Comment and close issue #444**

```bash
gh issue comment 444 --body "Implemented rhythm/phase/scene as first-class DSL constructs with:
- IR types: RhythmSpec, PhaseSpec, SceneSpec
- Parser: RhythmParserMixin with full syntax support
- Linker: cross-reference validation (persona, surface, entity, story)
- MCP tool: rhythm with propose/evaluate/coverage/get/list operations
- Static evaluation: surface existence, entity coverage, navigation coherence
- Design doc: docs/plans/2026-03-11-rhythm-scene-evaluation-design.md"

gh issue close 444
```
