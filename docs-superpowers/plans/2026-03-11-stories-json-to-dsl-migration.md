# Stories JSON → DSL Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `stories.json` persistence — stories become DSL-only constructs with `status:` field support.

**Architecture:** Extend DSL parser with `status:` field, build a DSL emitter for stories, rewrite all persistence callers to use appspec + emitter, convert example projects, delete the JSON path.

**Tech Stack:** Python 3.12, Pydantic, custom DSL parser/lexer/linker

**Spec:** `docs/superpowers/specs/2026-03-11-stories-json-to-dsl-migration-design.md`

---

## Chunk 1: Parser + Emitter (Foundation)

### Task 1: Add `status:` field to story parser

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/story.py:108-163` (field parsing loop)
- Test: `tests/unit/test_parser.py`

- [ ] **Step 1: Write failing test for `status: accepted`**

Add to `tests/unit/test_parser.py`:

```python
def test_story_with_status_accepted(self):
    dsl = '''
module test_mod
app test "Test"

story ST-001 "Test story":
  status: accepted
  actor: Admin
  trigger: form_submitted
  scope: [Task]

  then:
    - "Task is created"
'''
    modules = parse_modules_from_string(dsl)
    story = modules[0].fragment.stories[0]
    assert story.status == StoryStatus.ACCEPTED

def test_story_status_defaults_to_draft(self):
    dsl = '''
module test_mod
app test "Test"

story ST-001 "Test story":
  actor: Admin
  trigger: form_submitted
'''
    modules = parse_modules_from_string(dsl)
    story = modules[0].fragment.stories[0]
    assert story.status == StoryStatus.DRAFT

def test_story_with_invalid_status_raises(self):
    dsl = '''
module test_mod
app test "Test"

story ST-001 "Test story":
  status: pending
  actor: Admin
  trigger: form_submitted
'''
    with pytest.raises(ParseError):
        parse_modules_from_string(dsl)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_parser.py -k "test_story_with_status" -v`
Expected: FAIL — parser ignores `status:` field (hits unknown-field skip branch)

- [ ] **Step 3: Add `status:` parsing to story parser**

In `src/dazzle/core/dsl_parser_impl/story.py`, add to the field parsing loop (after the `elif self.match(TokenType.UNLESS)` block, before the `else`):

```python
# Add status field
status = None

# ... in the while loop, add this elif:
elif self.match(TokenType.STATUS):
    self.advance()
    self.expect(TokenType.COLON)
    status_str = self.expect_identifier_or_keyword().value
    status = self._parse_story_status(status_str)
    self.skip_newlines()
```

Add the status to the `return ir.StorySpec(...)` call:

```python
status=status or ir.StoryStatus.DRAFT,
```

Add the status parser method:

```python
def _parse_story_status(self, status_str: str) -> ir.StoryStatus:
    """Parse status string to StoryStatus enum."""
    status_map = {
        "draft": ir.StoryStatus.DRAFT,
        "accepted": ir.StoryStatus.ACCEPTED,
        "rejected": ir.StoryStatus.REJECTED,
    }
    if status_str in status_map:
        return status_map[status_str]

    from ..errors import make_parse_error
    valid_statuses = ", ".join(status_map.keys())
    raise make_parse_error(
        f"Invalid story status '{status_str}'. Valid statuses: {valid_statuses}",
        self.file,
        self.current_token().line,
        self.current_token().column,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_parser.py -k "test_story" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/story.py tests/unit/test_parser.py
git commit -m "feat(parser): add status field to story DSL grammar"
```

---

### Task 2: Build the DSL story emitter

**Files:**
- Create: `src/dazzle/core/story_emitter.py`
- Test: `tests/unit/test_story_emitter.py`

- [ ] **Step 1: Write failing tests for the emitter**

Create `tests/unit/test_story_emitter.py`:

```python
"""Tests for story DSL emitter."""
import pytest
from dazzle.core.ir.stories import (
    StoryCondition,
    StoryException,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.story_emitter import emit_story_dsl


class TestEmitStoryDsl:
    def test_minimal_story(self):
        story = StorySpec(
            story_id="ST-001",
            title="Admin creates task",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )
        result = emit_story_dsl(story)
        assert 'story ST-001 "Admin creates task":' in result
        assert "actor: Admin" in result
        assert "trigger: form_submitted" in result
        assert "status:" not in result  # draft is default, omitted

    def test_accepted_status_emitted(self):
        story = StorySpec(
            story_id="ST-002",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            status=StoryStatus.ACCEPTED,
        )
        result = emit_story_dsl(story)
        assert "status: accepted" in result

    def test_draft_status_omitted(self):
        story = StorySpec(
            story_id="ST-003",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            status=StoryStatus.DRAFT,
        )
        result = emit_story_dsl(story)
        assert "status:" not in result

    def test_scope_emitted(self):
        story = StorySpec(
            story_id="ST-004",
            title="Test",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task", "User"],
        )
        result = emit_story_dsl(story)
        assert "scope: [Task, User]" in result

    def test_empty_scope_omitted(self):
        story = StorySpec(
            story_id="ST-005",
            title="Test",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=[],
        )
        result = emit_story_dsl(story)
        assert "scope:" not in result

    def test_given_when_then(self):
        story = StorySpec(
            story_id="ST-006",
            title="Test",
            actor="Admin",
            trigger=StoryTrigger.STATUS_CHANGED,
            given=[StoryCondition(expression="Task.status is 'open'")],
            when=[StoryCondition(expression="Admin clicks complete")],
            then=[StoryCondition(expression="Task.status becomes 'done'")],
        )
        result = emit_story_dsl(story)
        assert '- "Task.status is \'open\'"' in result
        assert '- "Admin clicks complete"' in result
        assert '- "Task.status becomes \'done\'"' in result

    def test_unless_branches(self):
        story = StorySpec(
            story_id="ST-007",
            title="Test",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
            unless=[
                StoryException(
                    condition="Task.title is empty",
                    then_outcomes=["Validation error is shown"],
                )
            ],
        )
        result = emit_story_dsl(story)
        assert '- "Task.title is empty":' in result
        assert 'then: "Validation error is shown"' in result

    def test_empty_sections_omitted(self):
        story = StorySpec(
            story_id="ST-008",
            title="Test",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
            given=[],
            when=[],
            then=[],
            unless=[],
        )
        result = emit_story_dsl(story)
        assert "given:" not in result
        assert "when:" not in result
        assert "then:" not in result
        assert "unless:" not in result

    def test_description_emitted(self):
        story = StorySpec(
            story_id="ST-009",
            title="Test",
            description="A longer description of this story",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )
        result = emit_story_dsl(story)
        assert '"A longer description of this story"' in result


class TestEmitStoryRoundTrip:
    """Verify emit -> parse -> emit produces identical output."""

    def test_round_trip_full_story(self):
        from dazzle.core.parser import parse_modules_from_string

        story = StorySpec(
            story_id="ST-010",
            title="Staff sends invoice",
            actor="StaffUser",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Invoice", "Client"],
            status=StoryStatus.ACCEPTED,
            given=[StoryCondition(expression="Invoice.status is 'draft'")],
            when=[StoryCondition(expression="Invoice.status changes to 'sent'")],
            then=[StoryCondition(expression="Email is sent to Client.email")],
            unless=[
                StoryException(
                    condition="Client.email is missing",
                    then_outcomes=["FollowupTask is created"],
                )
            ],
        )
        dsl = emit_story_dsl(story)

        # Wrap in module for parser
        full_dsl = f'module test_mod\napp test "Test"\n\n{dsl}\n'
        modules = parse_modules_from_string(full_dsl)
        parsed = modules[0].fragment.stories[0]

        # Emit again and compare
        dsl2 = emit_story_dsl(parsed)
        assert dsl == dsl2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_story_emitter.py -v`
Expected: FAIL — `story_emitter` module does not exist

- [ ] **Step 3: Implement the emitter**

Create `src/dazzle/core/story_emitter.py`:

```python
"""DSL emitter for story specifications.

Serializes StorySpec objects to DAZZLE DSL text format.
"""

from __future__ import annotations

from .ir.stories import StorySpec, StoryStatus


def emit_story_dsl(story: StorySpec) -> str:
    """Emit a StorySpec as DAZZLE DSL text.

    Omits empty sections and default values (status: draft) for clean output.

    Args:
        story: The story specification to emit.

    Returns:
        DSL text for the story block.
    """
    lines: list[str] = []

    # Header
    lines.append(f'story {story.story_id} "{story.title}":')

    # Description (docstring-style)
    if story.description:
        lines.append(f'  "{story.description}"')

    # Status (omit draft — it's the default)
    if story.status != StoryStatus.DRAFT:
        lines.append(f"  status: {story.status.value}")

    # Required fields
    lines.append(f"  actor: {story.actor}")
    lines.append(f"  trigger: {story.trigger.value}")

    # Scope
    if story.scope:
        lines.append(f"  scope: [{', '.join(story.scope)}]")

    # Gherkin sections
    for section_name, conditions in [
        ("given", story.given),
        ("when", story.when),
        ("then", story.then),
    ]:
        if conditions:
            lines.append("")
            lines.append(f"  {section_name}:")
            for cond in conditions:
                lines.append(f'    - "{cond.expression}"')

    # Unless branches
    if story.unless:
        lines.append("")
        lines.append("  unless:")
        for exc in story.unless:
            if len(exc.then_outcomes) == 1:
                # Inline form
                lines.append(f'    - "{exc.condition}":')
                lines.append(f'        then: "{exc.then_outcomes[0]}"')
            elif exc.then_outcomes:
                # Multi-line form
                lines.append(f'    - "{exc.condition}":')
                for outcome in exc.then_outcomes:
                    lines.append(f'        then: "{outcome}"')
            else:
                lines.append(f'    - "{exc.condition}"')

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_story_emitter.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/story_emitter.py tests/unit/test_story_emitter.py
git commit -m "feat(core): add DSL story emitter with round-trip tests"
```

---

### Task 3: Add `get_next_story_id` to appspec-based lookup

The old `get_next_story_id` reads from JSON. We need a version that reads from an AppSpec.

**Files:**
- Modify: `src/dazzle/core/story_emitter.py` (add function)
- Test: `tests/unit/test_story_emitter.py` (add tests)

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_story_emitter.py`:

```python
from dazzle.core.story_emitter import get_next_story_id_from_appspec


class TestGetNextStoryId:
    def test_no_stories_returns_st_001(self):
        assert get_next_story_id_from_appspec([]) == "ST-001"

    def test_increments_from_highest(self):
        stories = [
            StorySpec(story_id="ST-001", title="A", actor="X", trigger=StoryTrigger.USER_CLICK),
            StorySpec(story_id="ST-005", title="B", actor="X", trigger=StoryTrigger.USER_CLICK),
            StorySpec(story_id="ST-003", title="C", actor="X", trigger=StoryTrigger.USER_CLICK),
        ]
        assert get_next_story_id_from_appspec(stories) == "ST-006"

    def test_handles_non_numeric_ids(self):
        stories = [
            StorySpec(story_id="ST-ABC", title="A", actor="X", trigger=StoryTrigger.USER_CLICK),
            StorySpec(story_id="ST-002", title="B", actor="X", trigger=StoryTrigger.USER_CLICK),
        ]
        assert get_next_story_id_from_appspec(stories) == "ST-003"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_story_emitter.py::TestGetNextStoryId -v`
Expected: FAIL — function does not exist

- [ ] **Step 3: Implement**

Add to `src/dazzle/core/story_emitter.py`:

```python
def get_next_story_id_from_appspec(stories: list[StorySpec]) -> str:
    """Generate the next story ID from existing stories.

    Scans story IDs matching ST-NNN pattern, finds the highest number,
    and returns the next sequential ID.

    Args:
        stories: List of existing story specs (from appspec.stories).

    Returns:
        Next story ID in ST-NNN format.
    """
    max_num = 0
    for story in stories:
        if story.story_id.startswith("ST-"):
            try:
                num = int(story.story_id[3:])
                max_num = max(max_num, num)
            except ValueError:
                continue
    return f"ST-{max_num + 1:03d}"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_story_emitter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/story_emitter.py tests/unit/test_story_emitter.py
git commit -m "feat(core): add appspec-based story ID generation"
```

---

## Chunk 2: IR Cleanup + Delete JSON Path

### Task 4: Remove legacy fields from StorySpec IR

**Files:**
- Modify: `src/dazzle/core/ir/stories.py`
- Modify: `src/dazzle/core/ir/__init__.py` (remove `StoriesContainer` export)
- Modify: `tests/unit/test_stories.py` (rewrite)

- [ ] **Step 1: Remove legacy fields from StorySpec**

In `src/dazzle/core/ir/stories.py`:

Remove these fields from `StorySpec`:
- `preconditions` (line 192-193)
- `happy_path_outcome` (line 195-196)
- `side_effects` (line 198-199)
- `constraints` (line 201-202)
- `variants` (line 204)
- `created_at` (line 207)
- `accepted_at` (line 208)

Remove these methods/properties:
- `with_status()` method (lines 214-235)
- `effective_given` property (lines 237-242)
- `effective_then` property (lines 244-249)

Delete `StoriesContainer` class (lines 252-267).

Update the docstring to remove references to legacy fields and JSON.

- [ ] **Step 2: Remove `StoriesContainer` from `ir/__init__.py`**

Remove `StoriesContainer` from imports and `__all__` in `src/dazzle/core/ir/__init__.py`.

- [ ] **Step 3: Rewrite `tests/unit/test_stories.py`**

Delete all tests that use `stories_persistence` functions (load, save, add, update_status, get_by_status, get_next_id). These will be replaced by emitter tests (Task 2) and handler tests (later tasks).

Keep any tests that test `StorySpec` model construction with Gherkin fields.

Update all `StorySpec(...)` constructors to remove legacy fields.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_stories.py tests/unit/test_story_emitter.py -v`
Expected: PASS (some tests deleted, remaining ones pass)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/stories.py src/dazzle/core/ir/__init__.py tests/unit/test_stories.py
git commit -m "refactor(ir): remove legacy story fields and StoriesContainer"
```

---

### Task 5: Delete `stories_persistence.py` and `_inject_json_stories`

**Files:**
- Delete: `src/dazzle/core/stories_persistence.py`
- Modify: `src/dazzle/core/appspec_loader.py` (remove `_inject_json_stories`)
- Modify: `src/dazzle/mcp/server/handlers/dsl/validate.py` (remove injection call)
- Modify: `src/dazzle/mcp/server/handlers/project.py` (remove injection calls)
- Modify: `src/dazzle/mcp/server/tool_handlers.py` (remove injection import + calls)
- Modify: `src/dazzle/mcp/event_first_tools.py` (remove injection import + calls)
- Modify: `src/dazzle/mcp/knowledge_graph/handlers/population_handlers.py` (remove injection call)

- [ ] **Step 1: Delete `stories_persistence.py`**

```bash
git rm src/dazzle/core/stories_persistence.py
```

- [ ] **Step 2: Remove `_inject_json_stories` from `appspec_loader.py`**

Delete the `_inject_json_stories` function. Remove its import of `load_stories` from `stories_persistence`. Remove any references to it in `load_project_appspec`.

The function `load_project_appspec` should now just do:
```python
modules = parse_modules(dsl_files)
return build_appspec(modules, manifest.project_root)
```

- [ ] **Step 3: Remove all `_inject_json_stories` call sites**

In each of these files, remove the import and all calls to `_inject_json_stories`:
- `src/dazzle/mcp/server/handlers/dsl/validate.py` (line 10, 32)
- `src/dazzle/mcp/server/handlers/project.py` (line 14, 114, 329)
- `src/dazzle/mcp/server/tool_handlers.py` (line 15 import, calls at ~129, ~314, ~358)
- `src/dazzle/mcp/event_first_tools.py` (line 21 import, 6 call sites)
- `src/dazzle/mcp/knowledge_graph/handlers/population_handlers.py` (line ~167)

- [ ] **Step 4: Run lint + type check**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/ && mypy src/dazzle`

- [ ] **Step 5: Run tests (expect some failures from callers not yet updated)**

Run: `pytest tests/ -m "not e2e" -x -q`

Note any failures — these are files that still import from `stories_persistence`. They'll be fixed in subsequent tasks.

- [ ] **Step 6: Commit**

```bash
git add -u  # stages all deletions and modifications
git commit -m "refactor(core): delete stories_persistence and _inject_json_stories"
```

---

## Chunk 3: Rewrite MCP Story Handlers

### Task 6: Rewrite `story propose` handler

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/stories.py`
- Modify: `tests/unit/mcp/test_stories_handlers.py`

- [ ] **Step 1: Rewrite propose handler**

The handler currently builds `StorySpec` objects using legacy fields (`preconditions`, `happy_path_outcome`, etc.) and saves via `add_stories()`.

Change to:
1. Build `StorySpec` objects using Gherkin fields (`given`, `when`, `then`)
2. Convert `preconditions` text → `StoryCondition(expression=text)`
3. Convert `happy_path_outcome` text → `StoryCondition(expression=text)`
4. Use `emit_story_dsl()` to serialize
5. Append to `dsl/stories.dsl` using the helper below
6. Replace `get_next_story_id(project_root)` with `get_next_story_id_from_appspec(app_spec.stories)`

Replace all imports of `stories_persistence` functions with imports from `story_emitter`.

**File append algorithm** (add as `append_stories_to_dsl` in `story_emitter.py`):

```python
def append_stories_to_dsl(project_root: Path, stories: list[StorySpec]) -> Path:
    """Append story blocks to dsl/stories.dsl, creating it if needed."""
    stories_file = project_root / "dsl" / "stories.dsl"
    stories_file.parent.mkdir(parents=True, exist_ok=True)

    new_text = "\n\n".join(emit_story_dsl(s) for s in stories)

    if stories_file.exists():
        existing = stories_file.read_text(encoding="utf-8").rstrip()
        stories_file.write_text(existing + "\n\n" + new_text + "\n", encoding="utf-8")
    else:
        stories_file.write_text(new_text + "\n", encoding="utf-8")

    return stories_file
```

- [ ] **Step 2: Rewrite `story save` handler**

Change from JSON persistence to DSL file write:
- Accept story data, build StorySpec
- Emit via `emit_story_dsl()`
- Append to `dsl/stories.dsl`

- [ ] **Step 3: Rewrite `story get` / `story wall` handlers**

Change from `load_stories(project_root)` / `get_stories_by_status()` to reading from `app_spec.stories` (loaded via `load_project_appspec`).

Filter by status using list comprehension on `app_spec.stories`.

- [ ] **Step 4: Rewrite `story coverage` handler**

Replace `load_story_index(project_root)` with reading from `app_spec.stories`.

- [ ] **Step 5: Update tests**

In `tests/unit/mcp/test_stories_handlers.py`:
- Remove all mocks of `stories_persistence` functions
- Update StorySpec construction to use Gherkin fields
- Test that propose writes DSL text to file
- Test that get reads from appspec

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/mcp/test_stories_handlers.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/server/handlers/stories.py tests/unit/mcp/test_stories_handlers.py
git commit -m "refactor(mcp): rewrite story handlers for DSL-only persistence"
```

---

### Task 7: Update remaining MCP handlers that reference stories

**Files:**
- Modify: `src/dazzle/mcp/server/tool_handlers.py` (story-related functions)
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py` (story-related functions)
- Modify: `src/dazzle/mcp/server/handlers/process/coverage.py`
- Modify: `src/dazzle/mcp/server/handlers/process/proposals.py`
- Modify: `src/dazzle/mcp/server/handlers/process/inspection.py`
- Modify: `src/dazzle/mcp/server/handlers/process/storage.py`
- Modify: `src/dazzle/mcp/server/handlers/process/scope_fidelity.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/status.py`
- Modify: `src/dazzle/mcp/server/handlers/dsl/analysis.py`
- Modify: `src/dazzle/mcp/server/handlers/dsl_test.py`
- Modify: `src/dazzle/mcp/event_first_tools.py`

- [ ] **Step 1: Replace all `load_stories(project_root)` calls**

In each file, replace:
```python
from dazzle.core.stories_persistence import load_stories
stories = load_stories(project_root)
```
with reading from appspec:
```python
app_spec = load_project_appspec(project_root)
stories = app_spec.stories
```

Or if `app_spec` is already in scope, just use `app_spec.stories`.

- [ ] **Step 2: Replace `load_story_index(project_root)` calls**

In `process/coverage.py` and `process/scope_fidelity.py`, replace with `app_spec.stories`.

**Important type change**: `load_story_index` returned `list[dict[str, Any]]` with keys like `s["story_id"]`, `s["scope"]`, `s.get("happy_path_outcome", [])`. Replace all dict access with attribute access on `StorySpec` objects:
- `s["story_id"]` → `s.story_id`
- `s["scope"]` → `s.scope`
- `s["status"]` → `s.status.value` (or compare with `StoryStatus.ACCEPTED`)
- `s.get("happy_path_outcome", [])` → `[c.expression for c in s.then]`
- `s.get("then", [])` → `s.then` (returns `list[StoryCondition]`)

- [ ] **Step 3: Replace `get_stories_by_status` calls**

Replace:
```python
stories = get_stories_by_status(project_root, StoryStatus.ACCEPTED)
```
with:
```python
stories = [s for s in app_spec.stories if s.status == StoryStatus.ACCEPTED]
```

- [ ] **Step 4: Replace `effective_given` / `effective_then` / `side_effects` references**

These properties/fields no longer exist. Replace:
- `story.effective_given` → `[c.expression for c in story.given]`
- `story.effective_then` → `[c.expression for c in story.then]`
- `story.side_effects` → remove (field deleted)
- `story.preconditions` → `[c.expression for c in story.given]`
- `story.happy_path_outcome` → `[c.expression for c in story.then]`

- [ ] **Step 5: Update `tool_handlers.py` story propose/save/get functions**

Same changes as Task 6 but for the legacy tool_handlers versions. Use Gherkin fields, emit DSL, read from appspec.

- [ ] **Step 6: Update `handlers_consolidated.py` story functions**

Same pattern — replace all `stories_persistence` imports and calls.

- [ ] **Step 7: Run lint + tests**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Run: `pytest tests/ -m "not e2e" -x -q`

- [ ] **Step 8: Commit**

```bash
git add -u
git commit -m "refactor(mcp): update all handlers to read stories from appspec"
```

---

## Chunk 4: CLI + Non-MCP Callers

### Task 8: Rewrite CLI story commands

**Files:**
- Modify: `src/dazzle/cli/story.py`
- Modify: `src/dazzle/cli/testing.py`

- [ ] **Step 1: Rewrite `cli/story.py`**

- `story propose`: Build StorySpec with Gherkin fields, emit DSL, write to file
- `story list`: Load appspec, filter stories by status
- `story generate-tests`: Load from appspec instead of `get_stories_by_status`
- Replace all `stories_persistence` imports with `story_emitter` imports
- Replace legacy field construction with Gherkin fields

- [ ] **Step 2: Rewrite story-related code in `cli/testing.py`**

- Replace `add_stories`, `get_next_story_id`, `save_stories` imports
- Use Gherkin fields in StorySpec construction
- Use `get_next_story_id_from_appspec`

- [ ] **Step 3: Run CLI tests**

Run: `pytest tests/ -m "not e2e" -k "story or testing" -v`

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/story.py src/dazzle/cli/testing.py
git commit -m "refactor(cli): rewrite story commands for DSL-only persistence"
```

---

### Task 9: Update remaining non-MCP callers

**Files:**
- Modify: `src/dazzle/pitch/extractor.py`
- Modify: `src/dazzle/core/fidelity_scorer.py`
- Modify: `src/dazzle/sentinel/agents/business_logic.py` (uses StoryTrigger — may be fine)

- [ ] **Step 1: Update `pitch/extractor.py`**

Replace `load_stories(project_root)` with `app_spec.stories` (build appspec if not available in scope).

- [ ] **Step 2: Update `fidelity_scorer.py`**

Replace `load_stories(project_root)` with reading from appspec.

- [ ] **Step 3: Verify `sentinel/agents/business_logic.py`**

This only imports `StoryTrigger` — no changes needed. Just verify it still compiles.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS (no more `stories_persistence` imports anywhere)

- [ ] **Step 5: Verify no remaining references**

Run: `grep -r "stories_persistence\|_inject_json_stories\|load_stories\|save_stories\|add_stories\|StoriesContainer" src/ --include="*.py"`
Expected: No matches (except maybe comments)

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "refactor: update remaining callers to use appspec for stories"
```

---

## Chunk 5: Migrate Examples + Final Cleanup

### Task 10: Convert example project stories from JSON to DSL

**Files:**
- Delete: `examples/*/dsl/seeds/stories/` directories
- Delete: `examples/*/.dazzle/stories/` directories
- Create: `examples/*/dsl/stories.dsl` for each project with stories

- [ ] **Step 1: Write migration helper**

Write a one-off Python script (not committed) that:
1. Reads `stories.json` from each example
2. Converts legacy fields → Gherkin (preconditions→given, happy_path_outcome→then)
3. Emits DSL via `emit_story_dsl()`
4. Writes `dsl/stories.dsl`

- [ ] **Step 2: Run migration for each example**

Run the script for: `simple_task`, `contact_manager`, `ops_dashboard`, `support_tickets`, `fieldtest_hub`, `rbac_validation`, `pra`, `llm_ticket_classifier`

- [ ] **Step 3: Validate each migrated project**

For each example with stories, run:
```bash
cd examples/<project> && dazzle validate
```
Expected: All validate successfully.

- [ ] **Step 4: Delete JSON files and directories**

```bash
find examples/ -path "*/.dazzle/stories" -type d -exec rm -rf {} +
find examples/ -path "*/dsl/seeds/stories" -type d -exec rm -rf {} +
```

- [ ] **Step 5: Run full test suite one final time**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS

- [ ] **Step 6: Run lint + type check**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/ && mypy src/dazzle`
Expected: Clean

- [ ] **Step 7: Commit**

```bash
git add -A examples/
git commit -m "migrate: convert example stories from JSON to DSL"
```

---

### Task 11: Update documentation and grammar reference

**Files:**
- Modify: `docs/reference/grammar.md` (add `status:` to story grammar)
- Modify: `.claude/CLAUDE.md` (update DSL Quick Reference if needed)

- [ ] **Step 1: Update grammar reference**

Add `status:` to the story grammar section in `docs/reference/grammar.md`.

- [ ] **Step 2: Update CLAUDE.md DSL Quick Reference**

If the story example in CLAUDE.md doesn't show `status:`, add it.

- [ ] **Step 3: Commit**

```bash
git add docs/reference/grammar.md .claude/CLAUDE.md
git commit -m "docs: update grammar reference with story status field"
```

---

### Task 12: Final verification and version bump

- [ ] **Step 1: Verify no JSON story references remain**

```bash
grep -r "stories\.json\|stories_persistence\|_inject_json_stories\|StoriesContainer" src/ tests/ --include="*.py" -l
```
Expected: No matches.

- [ ] **Step 2: Run full quality gate**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/ -m "not e2e" -x -q
```
Expected: All clean, all pass.

- [ ] **Step 3: Update CHANGELOG.md**

Under `## [Unreleased]`:

```markdown
### Changed
- Stories are now DSL-only constructs — `stories.json` persistence removed
- Story DSL grammar now supports `status: draft|accepted|rejected`
- `story propose` MCP tool writes DSL files instead of JSON
- All story handlers read from parsed AppSpec instead of JSON files

### Removed
- `stories_persistence.py` module (JSON read/write)
- `_inject_json_stories()` linker bridge
- Legacy story fields: `preconditions`, `happy_path_outcome`, `side_effects`, `constraints`, `variants`
- `StoriesContainer` model
- `.dazzle/stories/` and `dsl/seeds/stories/` directories
```

- [ ] **Step 4: Commit changelog**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for stories DSL migration"
```
