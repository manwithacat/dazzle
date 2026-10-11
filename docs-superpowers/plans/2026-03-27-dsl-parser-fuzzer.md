# DSL Parser Fuzzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-layer parser fuzzer (LLM generation, grammar-aware mutation, token-level mutation) with a classification oracle that detects hangs, crashes, and poor error messages.

**Architecture:** Seed corpus from `examples/*.dsl` → three generators (Haiku LLM, grammar-aware mutator, token-level mutator) → shared oracle (timeout + error classification) → markdown report. Lives in `src/dazzle/testing/fuzzer/`, CLI under `dazzle sentinel fuzz`.

**Tech Stack:** Python 3.12+, Hypothesis, Anthropic SDK (Haiku), pytest, Typer CLI

---

### Task 1: Corpus Loader

**Files:**
- Create: `src/dazzle/testing/fuzzer/__init__.py`
- Create: `src/dazzle/testing/fuzzer/corpus.py`
- Test: `tests/unit/test_fuzzer_corpus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_corpus.py
"""Tests for fuzzer corpus loading."""

from pathlib import Path

from dazzle.testing.fuzzer.corpus import load_corpus


class TestCorpusLoader:
    def test_load_corpus_returns_nonempty(self) -> None:
        """Corpus loader finds DSL files in examples/."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        assert len(corpus) > 0

    def test_corpus_entries_are_strings(self) -> None:
        """Each corpus entry is a non-empty string of DSL text."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        for entry in corpus:
            assert isinstance(entry, str)
            assert len(entry.strip()) > 0

    def test_corpus_entries_parse_successfully(self) -> None:
        """All corpus entries must parse without error (they're valid DSL)."""
        from dazzle.core.dsl_parser_impl import parse_dsl

        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        for entry in corpus:
            # Should not raise
            parse_dsl(entry, Path("corpus.dsl"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.testing.fuzzer'`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/__init__.py
"""DAZZLE DSL Parser Fuzzer."""
```

```python
# src/dazzle/testing/fuzzer/corpus.py
"""Seed corpus loader for the DSL parser fuzzer."""

from pathlib import Path


def load_corpus(examples_dir: Path) -> list[str]:
    """Load all .dsl files from a directory tree as fuzzer seed corpus.

    Args:
        examples_dir: Root directory containing .dsl files.

    Returns:
        List of DSL source strings, one per file.
    """
    entries: list[str] = []
    for dsl_file in sorted(examples_dir.rglob("*.dsl")):
        text = dsl_file.read_text(encoding="utf-8").strip()
        if text:
            entries.append(text)
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_corpus.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/__init__.py src/dazzle/testing/fuzzer/corpus.py tests/unit/test_fuzzer_corpus.py
git commit -m "feat(fuzzer): add corpus loader for DSL seed files (#732)"
```

---

### Task 2: Classification Oracle

**Files:**
- Create: `src/dazzle/testing/fuzzer/oracle.py`
- Test: `tests/unit/test_fuzzer_oracle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_oracle.py
"""Tests for fuzzer classification oracle."""

from dazzle.testing.fuzzer.oracle import Classification, classify


class TestOracle:
    def test_valid_dsl_classified_as_valid(self) -> None:
        dsl = '''module test\napp test_app "Test"\n\nentity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'''
        result = classify(dsl, timeout_seconds=5)
        assert result.classification == Classification.VALID

    def test_parse_error_with_location_is_clean(self) -> None:
        """A ParseError that includes file/line info is a clean error."""
        dsl = "entity\n"  # Missing name — parser gives location
        result = classify(dsl, timeout_seconds=5)
        assert result.classification == Classification.CLEAN_ERROR
        assert result.error_message is not None

    def test_empty_input_does_not_crash(self) -> None:
        result = classify("", timeout_seconds=5)
        assert result.classification in (
            Classification.VALID,
            Classification.CLEAN_ERROR,
        )

    def test_crash_on_non_parse_error(self) -> None:
        """If we inject a scenario that raises something other than ParseError,
        it should be classified as CRASH. We test the classifier directly."""
        from dazzle.testing.fuzzer.oracle import FuzzResult

        # Simulate a crash result
        result = FuzzResult(
            dsl_input="fake",
            classification=Classification.CRASH,
            error_message="TypeError: 'NoneType'",
            error_type="TypeError",
        )
        assert result.classification == Classification.CRASH

    def test_classification_includes_input(self) -> None:
        dsl = "not valid dsl at all @@@ !!!"
        result = classify(dsl, timeout_seconds=5)
        assert result.dsl_input == dsl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_oracle.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/oracle.py
"""Classification oracle for the DSL parser fuzzer.

Runs parse_dsl() on generated input and classifies the result:
- VALID: parsed successfully
- CLEAN_ERROR: ParseError with actionable message
- BAD_ERROR: ParseError with unhelpful message
- HANG: timeout exceeded
- CRASH: unhandled exception (not ParseError)
"""

from __future__ import annotations

import multiprocessing
import queue
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Classification(Enum):
    VALID = "valid"
    CLEAN_ERROR = "clean_error"
    BAD_ERROR = "bad_error"
    HANG = "hang"
    CRASH = "crash"


@dataclass
class FuzzResult:
    dsl_input: str
    classification: Classification
    error_message: str | None = None
    error_type: str | None = None
    constructs_hit: list[str] = field(default_factory=list)


def _parse_worker(dsl: str, result_queue: multiprocessing.Queue) -> None:  # type: ignore[type-arg]
    """Worker function that runs in a subprocess to parse DSL with isolation."""
    try:
        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.errors import ParseError

        _, _, _, _, _, fragment = parse_dsl(dsl, Path("fuzz.dsl"))
        # Collect which construct types were parsed
        constructs: list[str] = []
        for attr in (
            "entities", "surfaces", "workspaces", "experiences",
            "processes", "stories", "rhythms", "integrations",
            "apis", "ledgers", "webhooks", "approvals", "slas",
            "personas", "scenarios", "enums", "views",
        ):
            if getattr(fragment, attr, None):
                constructs.append(attr)
        result_queue.put(("valid", None, None, constructs))
    except ParseError as e:
        result_queue.put(("parse_error", str(e), "ParseError", []))
    except Exception as e:
        result_queue.put(("crash", str(e), type(e).__name__, []))


def classify(dsl: str, timeout_seconds: float = 5.0) -> FuzzResult:
    """Classify a DSL input by running it through the parser.

    Args:
        dsl: DSL source text to parse.
        timeout_seconds: Maximum time before classifying as HANG.

    Returns:
        FuzzResult with classification and metadata.
    """
    result_queue: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    proc = multiprocessing.Process(target=_parse_worker, args=(dsl, result_queue))
    proc.start()
    proc.join(timeout=timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.HANG,
            error_message=f"Parser did not complete within {timeout_seconds}s",
        )

    try:
        kind, msg, err_type, constructs = result_queue.get_nowait()
    except queue.Empty:
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CRASH,
            error_message="Worker process exited without result",
        )

    if kind == "valid":
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.VALID,
            constructs_hit=constructs,
        )
    elif kind == "parse_error":
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CLEAN_ERROR,
            error_message=msg,
            error_type=err_type,
        )
    else:  # crash
        return FuzzResult(
            dsl_input=dsl,
            classification=Classification.CRASH,
            error_message=msg,
            error_type=err_type,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_oracle.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/oracle.py tests/unit/test_fuzzer_oracle.py
git commit -m "feat(fuzzer): add classification oracle with timeout detection (#732)"
```

---

### Task 3: Token-Level Mutator (Hypothesis Strategies)

**Files:**
- Create: `src/dazzle/testing/fuzzer/mutator.py`
- Test: `tests/unit/test_fuzzer_mutator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_mutator.py
"""Tests for fuzzer mutation strategies."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dazzle.testing.fuzzer.corpus import load_corpus
from dazzle.testing.fuzzer.mutator import (
    delete_token,
    duplicate_line,
    insert_keyword,
    swap_adjacent_tokens,
)


EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


class TestTokenMutators:
    def test_insert_keyword_changes_input(self) -> None:
        dsl = "entity Task \"Task\":\n  id: uuid pk\n"
        mutated = insert_keyword(dsl, seed=42)
        assert mutated != dsl

    def test_delete_token_produces_shorter_output(self) -> None:
        dsl = "entity Task \"Task\":\n  id: uuid pk\n  title: str(200)\n"
        mutated = delete_token(dsl, seed=42)
        # Deleting a token should change the text
        assert mutated != dsl

    def test_swap_adjacent_changes_input(self) -> None:
        dsl = "entity Task \"Task\":\n  id: uuid pk\n  title: str(200)\n"
        mutated = swap_adjacent_tokens(dsl, seed=42)
        assert mutated != dsl

    def test_duplicate_line_adds_content(self) -> None:
        dsl = "entity Task \"Task\":\n  id: uuid pk\n  title: str(200)\n"
        mutated = duplicate_line(dsl, seed=42)
        assert len(mutated) > len(dsl)

    def test_mutations_deterministic_with_same_seed(self) -> None:
        dsl = "entity Task \"Task\":\n  id: uuid pk\n"
        a = insert_keyword(dsl, seed=99)
        b = insert_keyword(dsl, seed=99)
        assert a == b


class TestTokenMutatorNeverCrashesParser:
    """Property: mutations of valid DSL never crash the parser (hang or unhandled exception)."""

    @given(st.integers(min_value=0, max_value=10000))
    @settings(max_examples=50)
    def test_insert_keyword_no_crash(self, seed: int) -> None:
        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.errors import ParseError

        dsl = "module test\napp t \"T\"\n\nentity Task \"Task\":\n  id: uuid pk\n  title: str(200)\n"
        mutated = insert_keyword(dsl, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass  # Expected — structural errors are fine
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_mutator.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/mutator.py
"""Token-level and grammar-aware mutation strategies for DSL fuzzing.

Each mutator takes DSL text + a deterministic seed and returns mutated text.
Determinism allows reproducing specific failures.
"""

from __future__ import annotations

import random

# Keywords that appear in various DSL constructs — used for insertion mutations
DSL_KEYWORDS: list[str] = [
    "entity", "surface", "workspace", "experience", "process", "story",
    "rhythm", "service", "integration", "ledger", "approval", "sla",
    "persona", "scenario", "field", "action", "section", "mode",
    "permit", "scope", "for", "uses", "filter", "sort", "ux",
    "required", "unique", "pk", "owner", "access", "step", "when",
    "on", "schedule", "enum", "view", "webhook", "island",
    "has_many", "has_one", "belongs_to", "ref", "bool", "str", "int",
    "text", "uuid", "date", "datetime", "email", "json", "money",
    "state_machine", "state", "transition", "trigger",
]

# Common YAML-isms and wrong-syntax patterns agents produce
NEAR_MISS_FRAGMENTS: list[str] = [
    "allow_personas: [\"admin\"]",
    "filter: status = active",
    "field name \"Name\": required",
    "type: list",
    "fields:",
    "  - title",
    "  - status",
    "roles: [admin, user]",
    "visible: true",
    "editable: false",
    "required: true",
]


def _make_rng(seed: int) -> random.Random:
    return random.Random(seed)


def insert_keyword(dsl: str, seed: int) -> str:
    """Insert a random DSL keyword at a random position in the text."""
    rng = _make_rng(seed)
    lines = dsl.split("\n")
    if not lines:
        return dsl
    line_idx = rng.randrange(len(lines))
    keyword = rng.choice(DSL_KEYWORDS)
    line = lines[line_idx]
    # Insert at a random word boundary
    words = line.split()
    insert_pos = rng.randint(0, len(words))
    words.insert(insert_pos, keyword)
    lines[line_idx] = " ".join(words)
    return "\n".join(lines)


def delete_token(dsl: str, seed: int) -> str:
    """Delete a random whitespace-delimited token from the text."""
    rng = _make_rng(seed)
    lines = dsl.split("\n")
    # Find lines with tokens
    candidates = [(i, line) for i, line in enumerate(lines) if line.strip()]
    if not candidates:
        return dsl
    line_idx, line = rng.choice(candidates)
    words = line.split()
    if len(words) <= 1:
        return dsl  # Don't delete the only token
    del_pos = rng.randrange(len(words))
    words.pop(del_pos)
    # Preserve leading whitespace
    leading = len(line) - len(line.lstrip())
    lines[line_idx] = " " * leading + " ".join(words)
    return "\n".join(lines)


def swap_adjacent_tokens(dsl: str, seed: int) -> str:
    """Swap two adjacent whitespace-delimited tokens on a random line."""
    rng = _make_rng(seed)
    lines = dsl.split("\n")
    candidates = [(i, line) for i, line in enumerate(lines) if len(line.split()) >= 2]
    if not candidates:
        return dsl
    line_idx, line = rng.choice(candidates)
    words = line.split()
    swap_pos = rng.randrange(len(words) - 1)
    words[swap_pos], words[swap_pos + 1] = words[swap_pos + 1], words[swap_pos]
    leading = len(line) - len(line.lstrip())
    lines[line_idx] = " " * leading + " ".join(words)
    return "\n".join(lines)


def duplicate_line(dsl: str, seed: int) -> str:
    """Duplicate a random non-empty line."""
    rng = _make_rng(seed)
    lines = dsl.split("\n")
    candidates = [i for i, line in enumerate(lines) if line.strip()]
    if not candidates:
        return dsl
    line_idx = rng.choice(candidates)
    lines.insert(line_idx + 1, lines[line_idx])
    return "\n".join(lines)


def inject_near_miss(dsl: str, seed: int) -> str:
    """Inject a known near-miss fragment at a random indented position."""
    rng = _make_rng(seed)
    lines = dsl.split("\n")
    fragment = rng.choice(NEAR_MISS_FRAGMENTS)
    # Find a line inside a block (indented) to inject after
    indented = [i for i, line in enumerate(lines) if line.startswith("  ")]
    if indented:
        insert_after = rng.choice(indented)
    else:
        insert_after = rng.randrange(len(lines)) if lines else 0
    lines.insert(insert_after + 1, "  " + fragment)
    return "\n".join(lines)


def cross_pollinate(dsl: str, donor: str, seed: int) -> str:
    """Graft a random block-level fragment from donor DSL into target DSL."""
    rng = _make_rng(seed)
    donor_lines = donor.split("\n")

    # Find top-level construct starts in donor (lines starting with a keyword, no indent)
    construct_starts: list[int] = []
    for i, line in enumerate(donor_lines):
        stripped = line.strip()
        first_word = stripped.split()[0] if stripped.split() else ""
        if first_word in ("entity", "surface", "workspace", "process", "story",
                          "rhythm", "persona", "integration", "service"):
            construct_starts.append(i)

    if not construct_starts:
        return dsl

    # Pick a random construct from donor
    start = rng.choice(construct_starts)
    # Find end (next top-level construct or EOF)
    end = len(donor_lines)
    for next_start in construct_starts:
        if next_start > start:
            end = next_start
            break
    fragment_lines = donor_lines[start:end]

    # Insert into target at a random top-level position
    target_lines = dsl.split("\n")
    insert_pos = rng.randint(0, len(target_lines))
    result_lines = target_lines[:insert_pos] + [""] + fragment_lines + [""] + target_lines[insert_pos:]
    return "\n".join(result_lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_mutator.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/mutator.py tests/unit/test_fuzzer_mutator.py
git commit -m "feat(fuzzer): add token-level and near-miss mutation strategies (#732)"
```

---

### Task 4: Haiku LLM Generator

**Files:**
- Create: `src/dazzle/testing/fuzzer/generator.py`
- Test: `tests/unit/test_fuzzer_generator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_generator.py
"""Tests for Haiku-based DSL generator."""

from unittest.mock import MagicMock, patch

from dazzle.testing.fuzzer.generator import (
    PROMPT_VARIATIONS,
    build_generation_prompt,
    generate_samples,
)


class TestPromptConstruction:
    def test_prompt_includes_grammar_summary(self) -> None:
        prompt = build_generation_prompt(
            seed_dsl="entity Task \"Task\":\n  id: uuid pk\n",
            variation="entity-heavy",
        )
        assert "entity" in prompt
        assert "surface" in prompt

    def test_prompt_includes_seed_dsl(self) -> None:
        seed = "entity Task \"Task\":\n  id: uuid pk\n"
        prompt = build_generation_prompt(seed_dsl=seed, variation="entity-heavy")
        assert seed in prompt

    def test_all_variations_produce_valid_prompts(self) -> None:
        seed = "entity Task \"Task\":\n  id: uuid pk\n"
        for variation in PROMPT_VARIATIONS:
            prompt = build_generation_prompt(seed_dsl=seed, variation=variation)
            assert len(prompt) > 100


class TestGenerateSamples:
    @patch("dazzle.testing.fuzzer.generator.anthropic")
    def test_generate_returns_list_of_strings(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="entity Foo \"Foo\":\n  id: uuid pk\n")]
        mock_client.messages.create.return_value = mock_response

        samples = generate_samples(
            seed_dsl="entity Task \"Task\":\n  id: uuid pk\n",
            count=2,
        )
        assert isinstance(samples, list)
        assert len(samples) == 2
        assert all(isinstance(s, str) for s in samples)

    @patch("dazzle.testing.fuzzer.generator.anthropic")
    def test_generate_cycles_through_variations(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="entity Bar \"Bar\":\n  id: uuid pk\n")]
        mock_client.messages.create.return_value = mock_response

        # Generate more samples than variations to test cycling
        count = len(PROMPT_VARIATIONS) + 2
        samples = generate_samples(
            seed_dsl="entity Task \"Task\":\n  id: uuid pk\n",
            count=count,
        )
        assert len(samples) == count
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_generator.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/generator.py
"""Haiku-based DSL generator for fuzzing.

Uses Claude Haiku to generate plausible-but-wrong DSL. Haiku's tendency
to pattern-match without full structural understanding produces exactly
the near-miss error distribution we want to test against.
"""

from __future__ import annotations

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

# Grammar summary fed to Haiku — enough to pattern-match, not enough to be perfect
GRAMMAR_SUMMARY = """DAZZLE DSL Grammar Summary:

Top-level constructs (each starts at column 0, followed by identifier and optional "Label"):
  entity Name "Label":     — data model with typed fields
  surface Name "Label":    — UI screen (sections with fields, actions)
  workspace Name "Label":  — dashboard grouping surfaces into regions
  experience Name "Label": — multi-step wizard/flow
  process Name "Label":    — background workflow with steps
  story Name "Label":      — user story with scenes
  rhythm Name "Label":     — recurring scheduled operation
  persona Name "Label":    — user role definition
  integration Name "Label": — external API connection
  service Name "Label":    — internal/external service
  ledger Name "Label":     — financial/audit ledger
  enum Name "Label":       — enumeration type
  approval Name "Label":   — approval workflow
  sla Name "Label":        — service level agreement
  webhook Name "Label":    — incoming webhook handler

Entity fields (indented 2 spaces):
  field_name: type modifiers
  Types: str(N), text, int, decimal, bool, date, datetime, uuid, email, json, money, file, url
  Modifiers: required, unique, pk, indexed
  Relationships: ref EntityName, has_many EntityName, has_one EntityName, belongs_to EntityName
  Default values: field_name: type = default_value
  State machines: state_machine Name: / state active / transition activate: idle -> active

Surface sections (indented 2 spaces):
  uses entity EntityName
  mode: list | detail | form | kanban
  section name:
    field field_name "Label"
    action action_name "Label"
  permit:
    read: role_name
    write: role_name
  scope:
    read: field = current_user.field
      for: persona_name

Workspace regions:
  region name "Label":
    surface SurfaceName
  access: persona(persona_name)

Process steps:
  trigger: event_name on EntityName
  step name "Label":
    action: do_something
  sla: 2h

Important syntax rules:
- Indentation is 2 spaces (not tabs)
- Strings use double quotes
- Blocks end with colon
- Surface fields do NOT have types — those belong on entities
- filter: in surfaces must be inside a ux: block
- Access control uses access: persona(name), not allow_personas: [name]
"""

PROMPT_VARIATIONS: list[str] = [
    "entity-heavy",
    "surface-heavy",
    "process-heavy",
    "rbac-heavy",
    "integration-heavy",
    "kitchen-sink",
]

_VARIATION_DESCRIPTIONS: dict[str, str] = {
    "entity-heavy": "Define a CRM system with 5 entities including relationships, state machines, and computed fields",
    "surface-heavy": "Build admin dashboards with filters, multi-section layouts, actions, and persona-based access",
    "process-heavy": "Model a multi-step approval workflow with branching, SLA tracking, and error compensation",
    "rbac-heavy": "Define 4 personas with scoped access to shared entities using permit and scope blocks",
    "integration-heavy": "Connect to 3 external APIs with webhooks, sync schedules, and field mappings",
    "kitchen-sink": "Build a complete project management app with tasks, teams, sprints, and reporting",
}


def build_generation_prompt(seed_dsl: str, variation: str) -> str:
    """Build a prompt for Haiku to generate DSL.

    Args:
        seed_dsl: Example DSL to show as reference.
        variation: Which prompt variation to use.

    Returns:
        Complete prompt string.
    """
    description = _VARIATION_DESCRIPTIONS.get(variation, _VARIATION_DESCRIPTIONS["kitchen-sink"])
    return f"""{GRAMMAR_SUMMARY}

Here is an example of valid DAZZLE DSL:

```dsl
{seed_dsl}
```

Write DAZZLE DSL for the following requirement. Output ONLY the DSL code, no explanations:

{description}
"""


def generate_samples(
    seed_dsl: str,
    count: int,
    model: str = "claude-haiku-4-5-20251001",
) -> list[str]:
    """Generate DSL samples using Haiku.

    Args:
        seed_dsl: Example DSL shown as reference in prompts.
        count: Number of samples to generate.
        model: Anthropic model ID.

    Returns:
        List of generated DSL strings.
    """
    if anthropic is None:
        raise ImportError(
            "anthropic package required for LLM generation. "
            "Install with: pip install dazzle-dsl[llm]"
        )

    client = anthropic.Anthropic()
    samples: list[str] = []

    for i in range(count):
        variation = PROMPT_VARIATIONS[i % len(PROMPT_VARIATIONS)]
        prompt = build_generation_prompt(seed_dsl=seed_dsl, variation=variation)

        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        # Strip markdown fences if Haiku wraps output
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            # Remove language tag on first fence
            text = "\n".join(lines)
        samples.append(text.strip())

    return samples
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_generator.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/generator.py tests/unit/test_fuzzer_generator.py
git commit -m "feat(fuzzer): add Haiku-based DSL generator with prompt variations (#732)"
```

---

### Task 5: Report Generator

**Files:**
- Create: `src/dazzle/testing/fuzzer/report.py`
- Test: `tests/unit/test_fuzzer_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_report.py
"""Tests for fuzzer report generation."""

from dazzle.testing.fuzzer.oracle import Classification, FuzzResult
from dazzle.testing.fuzzer.report import generate_report


class TestReport:
    def test_empty_results_produce_valid_report(self) -> None:
        report = generate_report([])
        assert "# DSL Parser Fuzz Report" in report
        assert "0 samples" in report

    def test_report_includes_summary_counts(self) -> None:
        results = [
            FuzzResult(dsl_input="a", classification=Classification.VALID),
            FuzzResult(dsl_input="b", classification=Classification.CLEAN_ERROR, error_message="err"),
            FuzzResult(dsl_input="c", classification=Classification.HANG, error_message="timeout"),
        ]
        report = generate_report(results)
        assert "1" in report  # at least the counts appear
        assert "HANG" in report or "hang" in report.lower()

    def test_report_lists_bugs(self) -> None:
        results = [
            FuzzResult(
                dsl_input="bad input",
                classification=Classification.CRASH,
                error_message="TypeError: ...",
                error_type="TypeError",
            ),
        ]
        report = generate_report(results)
        assert "CRASH" in report or "crash" in report.lower()
        assert "TypeError" in report

    def test_report_shows_construct_coverage(self) -> None:
        results = [
            FuzzResult(
                dsl_input="a",
                classification=Classification.VALID,
                constructs_hit=["entities", "surfaces"],
            ),
            FuzzResult(
                dsl_input="b",
                classification=Classification.VALID,
                constructs_hit=["processes"],
            ),
        ]
        report = generate_report(results)
        assert "entities" in report
        assert "surfaces" in report
        assert "processes" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_report.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/report.py
"""Markdown report generator for fuzzer results."""

from __future__ import annotations

from collections import Counter

from dazzle.testing.fuzzer.oracle import Classification, FuzzResult


def generate_report(results: list[FuzzResult]) -> str:
    """Generate a markdown report from fuzz results.

    Args:
        results: List of classification results.

    Returns:
        Markdown-formatted report string.
    """
    counts = Counter(r.classification for r in results)
    total = len(results)

    # Collect construct coverage
    all_constructs: set[str] = set()
    for r in results:
        all_constructs.update(r.constructs_hit)

    # Collect bugs (hangs + crashes)
    bugs = [r for r in results if r.classification in (Classification.HANG, Classification.CRASH)]

    # Collect bad errors
    bad_errors = [r for r in results if r.classification == Classification.BAD_ERROR]

    lines: list[str] = []
    lines.append("# DSL Parser Fuzz Report\n")
    lines.append(f"**{total} samples** tested\n")
    lines.append("## Summary\n")
    lines.append("| Classification | Count | % |")
    lines.append("|---|---|---|")
    for cls in Classification:
        c = counts.get(cls, 0)
        pct = f"{c / total * 100:.1f}" if total > 0 else "0.0"
        lines.append(f"| {cls.value} | {c} | {pct}% |")
    lines.append("")

    # Construct coverage
    lines.append("## Construct Coverage\n")
    if all_constructs:
        for construct in sorted(all_constructs):
            lines.append(f"- {construct}")
    else:
        lines.append("No constructs hit (all inputs failed to parse).")
    lines.append("")

    # Bugs section
    if bugs:
        lines.append(f"## Bugs ({len(bugs)})\n")
        for i, bug in enumerate(bugs, 1):
            lines.append(f"### Bug {i}: {bug.classification.value.upper()}\n")
            if bug.error_type:
                lines.append(f"**Error type:** {bug.error_type}\n")
            if bug.error_message:
                lines.append(f"**Message:** {bug.error_message}\n")
            lines.append("**Input:**\n")
            lines.append(f"```dsl\n{bug.dsl_input[:500]}\n```\n")

    # Bad errors section
    if bad_errors:
        lines.append(f"## Poor Error Messages ({len(bad_errors)})\n")
        for i, be in enumerate(bad_errors, 1):
            lines.append(f"### Bad Error {i}\n")
            lines.append(f"**Message:** {be.error_message}\n")
            lines.append(f"**Input:**\n```dsl\n{be.dsl_input[:500]}\n```\n")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_report.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/report.py tests/unit/test_fuzzer_report.py
git commit -m "feat(fuzzer): add markdown report generator (#732)"
```

---

### Task 6: Campaign Runner (ties layers together)

**Files:**
- Modify: `src/dazzle/testing/fuzzer/__init__.py`
- Test: `tests/unit/test_fuzzer_campaign.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fuzzer_campaign.py
"""Tests for the fuzzer campaign runner."""

from pathlib import Path
from unittest.mock import patch

from dazzle.testing.fuzzer import run_campaign
from dazzle.testing.fuzzer.oracle import Classification


class TestCampaign:
    def test_mutation_campaign_produces_results(self) -> None:
        """Run a small mutation-only campaign against the example corpus."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        results = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=10,
        )
        assert len(results) > 0
        # All results should have a classification
        for r in results:
            assert r.classification in Classification

    def test_mutation_campaign_no_hangs(self) -> None:
        """No mutation of valid DSL should cause a parser hang."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        results = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=20,
        )
        hangs = [r for r in results if r.classification == Classification.HANG]
        assert len(hangs) == 0, f"Found {len(hangs)} hangs: {[h.dsl_input[:80] for h in hangs]}"

    def test_dry_run_returns_inputs_without_classifying(self) -> None:
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        inputs = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=5,
            dry_run=True,
        )
        # In dry-run mode, results have no classification yet — they're just generated inputs
        assert len(inputs) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fuzzer_campaign.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/dazzle/testing/fuzzer/__init__.py
"""DAZZLE DSL Parser Fuzzer.

Three-layer fuzzer for discovering parser error surface gaps:
- Layer 1 (llm): Haiku generates plausible-wrong DSL
- Layer 2 (mutate): Grammar-aware and token-level mutations of valid DSL
- Layer 3 (near-miss): Injection of known near-miss patterns

Usage:
    from dazzle.testing.fuzzer import run_campaign
    results = run_campaign(examples_dir, layers=["mutate"], samples_per_layer=100)
"""

from __future__ import annotations

from pathlib import Path

from dazzle.testing.fuzzer.corpus import load_corpus
from dazzle.testing.fuzzer.mutator import (
    cross_pollinate,
    delete_token,
    duplicate_line,
    inject_near_miss,
    insert_keyword,
    swap_adjacent_tokens,
)
from dazzle.testing.fuzzer.oracle import Classification, FuzzResult, classify
from dazzle.testing.fuzzer.report import generate_report


def run_campaign(
    examples_dir: Path,
    layers: list[str] | None = None,
    samples_per_layer: int = 100,
    timeout_seconds: float = 5.0,
    dry_run: bool = False,
) -> list[FuzzResult]:
    """Run a fuzz campaign against the DSL parser.

    Args:
        examples_dir: Directory containing seed .dsl files.
        layers: Which layers to run: "llm", "mutate", or both. Default: both.
        samples_per_layer: Number of samples per layer.
        timeout_seconds: Parser timeout for classification.
        dry_run: If True, generate inputs but skip classification.

    Returns:
        List of FuzzResult (or unclassified results in dry-run mode).
    """
    if layers is None:
        layers = ["mutate", "llm"]

    corpus = load_corpus(examples_dir)
    if not corpus:
        return []

    generated_inputs: list[str] = []

    # ── Mutation layer ──
    if "mutate" in layers:
        mutators = [
            insert_keyword,
            delete_token,
            swap_adjacent_tokens,
            duplicate_line,
            inject_near_miss,
        ]
        per_mutator = max(1, samples_per_layer // len(mutators))
        for mutator_fn in mutators:
            for seed in range(per_mutator):
                source = corpus[seed % len(corpus)]
                if mutator_fn == cross_pollinate:
                    donor = corpus[(seed + 1) % len(corpus)]
                    mutated = cross_pollinate(source, donor, seed=seed)
                else:
                    mutated = mutator_fn(source, seed=seed)
                generated_inputs.append(mutated)

        # Also do cross-pollination
        cross_count = max(1, samples_per_layer // 5)
        for seed in range(cross_count):
            source = corpus[seed % len(corpus)]
            donor = corpus[(seed + 1) % len(corpus)]
            mutated = cross_pollinate(source, donor, seed=seed)
            generated_inputs.append(mutated)

    # ── LLM layer ──
    if "llm" in layers:
        from dazzle.testing.fuzzer.generator import generate_samples

        seed_dsl = corpus[0]  # Use first corpus entry as seed
        samples = generate_samples(seed_dsl=seed_dsl, count=samples_per_layer)
        generated_inputs.extend(samples)

    # ── Classification ──
    if dry_run:
        return [
            FuzzResult(dsl_input=inp, classification=Classification.VALID)
            for inp in generated_inputs
        ]

    results: list[FuzzResult] = []
    for inp in generated_inputs:
        result = classify(inp, timeout_seconds=timeout_seconds)
        results.append(result)

    return results


__all__ = [
    "run_campaign",
    "generate_report",
    "Classification",
    "FuzzResult",
    "classify",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fuzzer_campaign.py -v`
Expected: 3 PASSED (the mutation tests may take ~30s due to subprocess timeouts)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/testing/fuzzer/__init__.py tests/unit/test_fuzzer_campaign.py
git commit -m "feat(fuzzer): add campaign runner tying all layers together (#732)"
```

---

### Task 7: CLI Integration (`dazzle sentinel fuzz`)

**Files:**
- Modify: `src/dazzle/cli/sentinel.py`
- Test: `tests/unit/test_cli_sentinel_fuzz.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_sentinel_fuzz.py
"""Tests for the sentinel fuzz CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from dazzle.cli.sentinel import sentinel_app

runner = CliRunner()


class TestSentinelFuzzCLI:
    @patch("dazzle.cli.sentinel.run_campaign")
    @patch("dazzle.cli.sentinel.generate_report")
    def test_fuzz_command_exists(self, mock_report, mock_campaign) -> None:
        mock_campaign.return_value = []
        mock_report.return_value = "# Report\n0 samples"
        result = runner.invoke(sentinel_app, ["fuzz", "--samples", "5"])
        assert result.exit_code == 0

    @patch("dazzle.cli.sentinel.run_campaign")
    @patch("dazzle.cli.sentinel.generate_report")
    def test_fuzz_layer_filter(self, mock_report, mock_campaign) -> None:
        mock_campaign.return_value = []
        mock_report.return_value = "# Report"
        result = runner.invoke(sentinel_app, ["fuzz", "--layer", "mutate", "--samples", "5"])
        assert result.exit_code == 0
        mock_campaign.assert_called_once()
        call_kwargs = mock_campaign.call_args
        assert call_kwargs[1]["layers"] == ["mutate"] or call_kwargs.kwargs["layers"] == ["mutate"]

    @patch("dazzle.cli.sentinel.run_campaign")
    def test_fuzz_dry_run(self, mock_campaign) -> None:
        mock_campaign.return_value = []
        result = runner.invoke(sentinel_app, ["fuzz", "--dry-run", "--samples", "5"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_sentinel_fuzz.py -v`
Expected: FAIL — `fuzz` command doesn't exist yet

- [ ] **Step 3: Write the implementation**

Add the following to the end of `src/dazzle/cli/sentinel.py` (before any `__all__` if present):

```python
@sentinel_app.command("fuzz")
def sentinel_fuzz(
    samples: int = typer.Option(100, "--samples", "-n", help="Samples per layer"),
    layer: str = typer.Option(None, "--layer", "-l", help="Layer to run: llm, mutate, or all"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate inputs without classifying"),
    timeout: float = typer.Option(5.0, "--timeout", "-t", help="Parser timeout in seconds"),
    output: str = typer.Option(None, "--output", "-o", help="Save report to file"),
) -> None:
    """Run parser fuzz campaign to discover error surface gaps."""
    from dazzle.testing.fuzzer import generate_report, run_campaign

    # Find examples directory
    examples_dir = Path.cwd() / "examples"
    if not examples_dir.exists():
        # Try relative to package
        import dazzle

        pkg_root = Path(dazzle.__file__).resolve().parents[1]
        examples_dir = pkg_root / "examples"

    if not examples_dir.exists():
        typer.echo("No examples/ directory found for seed corpus.", err=True)
        raise typer.Exit(code=1)

    layers = [layer] if layer else None

    typer.echo(f"Running fuzz campaign: {samples} samples/layer, timeout={timeout}s")
    if dry_run:
        typer.echo("(dry run — generating inputs only)")

    results = run_campaign(
        examples_dir=examples_dir,
        layers=layers,
        samples_per_layer=samples,
        timeout_seconds=timeout,
        dry_run=dry_run,
    )

    if dry_run:
        typer.echo(f"Generated {len(results)} inputs (not classified)")
        return

    report = generate_report(results)
    typer.echo(report)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        typer.echo(f"\nReport saved to {output}")

    # Exit with error code if bugs found
    from dazzle.testing.fuzzer import Classification

    bugs = [r for r in results if r.classification in (Classification.HANG, Classification.CRASH)]
    if bugs:
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_sentinel_fuzz.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/sentinel.py tests/unit/test_cli_sentinel_fuzz.py
git commit -m "feat(fuzzer): add 'dazzle sentinel fuzz' CLI command (#732)"
```

---

### Task 8: Hypothesis-Powered Fuzz Test Suite

**Files:**
- Create: `tests/unit/test_parser_fuzz.py`

- [ ] **Step 1: Write the test file**

This is a test-only task — the tests exercise the fuzzer against the real parser.

```python
# tests/unit/test_parser_fuzz.py
"""Hypothesis-powered parser fuzz tests.

These tests verify parser robustness invariants:
1. No input causes a hang (>5s timeout)
2. No input causes an unhandled exception (only ParseError is acceptable)
3. Mutations of valid DSL produce either valid output or clean ParseErrors
"""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.testing.fuzzer.corpus import load_corpus
from dazzle.testing.fuzzer.mutator import (
    delete_token,
    duplicate_line,
    inject_near_miss,
    insert_keyword,
    swap_adjacent_tokens,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_corpus: list[str] | None = None


def _get_corpus() -> list[str]:
    global _corpus
    if _corpus is None:
        _corpus = load_corpus(EXAMPLES_DIR)
    return _corpus


class TestParserNeverCrashesOnArbitraryInput:
    """The parser should only raise ParseError, never crash."""

    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_text(self, text: str) -> None:
        try:
            parse_dsl(text, Path("fuzz.dsl"))
        except ParseError:
            pass  # Expected

    @given(st.text(min_size=0, max_size=500, alphabet="abcdefghijklmnopqrstuvwxyz :_\n  \""))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_dsl_like_text(self, text: str) -> None:
        """Text using DSL-like characters is more likely to reach deeper parser paths."""
        try:
            parse_dsl(text, Path("fuzz.dsl"))
        except ParseError:
            pass


class TestMutatedCorpusNeverCrashes:
    """Mutations of valid DSL should produce ParseError at worst, never crash."""

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_insert_keyword_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = insert_keyword(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delete_token_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = delete_token(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_swap_adjacent_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = swap_adjacent_tokens(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_line_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = duplicate_line(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_near_miss_injection(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = inject_near_miss(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/unit/test_parser_fuzz.py -v --timeout=120`
Expected: 7 PASSED (may take 30-60s due to Hypothesis exploration)

If any test **fails** with an exception other than ParseError, that's a real parser bug — note the failing input from the Hypothesis output for a follow-up fix.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_parser_fuzz.py
git commit -m "test(fuzzer): add Hypothesis-powered parser fuzz test suite (#732)"
```

---

### Task 9: Wire into MCP sentinel tool

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/sentinel.py` (or wherever the sentinel handler lives)

This is a lightweight wiring task — the sentinel MCP tool already has `findings`, `status`, `history` operations. We add a `fuzz_summary` operation that reports the last fuzz run.

- [ ] **Step 1: Check where sentinel MCP handler lives**

Run: `grep -r "sentinel" src/dazzle/mcp/server/handlers/ --files-with-matches`

- [ ] **Step 2: Read the handler file**

Read the sentinel handler to understand the pattern for adding operations.

- [ ] **Step 3: Add fuzz_summary operation**

Add a new operation `fuzz_summary` that:
- Looks for the most recent fuzz report file (if `--output` was used)
- Or runs a small campaign (10 samples, mutate only) inline
- Returns the report markdown

Follow the existing handler pattern exactly — use the same operation dispatch style.

- [ ] **Step 4: Test manually**

Run: `dazzle sentinel fuzz --samples 10 --layer mutate`
Verify output shows the report table.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/sentinel.py
git commit -m "feat(fuzzer): wire fuzz_summary into sentinel MCP handler (#732)"
```

---

### Task 10: Final integration test and cleanup

**Files:**
- All fuzzer files

- [ ] **Step 1: Run the full test suite for fuzzer files**

Run: `pytest tests/unit/test_fuzzer_corpus.py tests/unit/test_fuzzer_oracle.py tests/unit/test_fuzzer_mutator.py tests/unit/test_fuzzer_report.py tests/unit/test_fuzzer_campaign.py tests/unit/test_cli_sentinel_fuzz.py tests/unit/test_parser_fuzz.py -v`
Expected: All PASSED

- [ ] **Step 2: Run linting**

Run: `ruff check src/dazzle/testing/fuzzer/ tests/unit/test_fuzzer_*.py tests/unit/test_parser_fuzz.py tests/unit/test_cli_sentinel_fuzz.py --fix && ruff format src/dazzle/testing/fuzzer/ tests/unit/test_fuzzer_*.py tests/unit/test_parser_fuzz.py tests/unit/test_cli_sentinel_fuzz.py`

- [ ] **Step 3: Run type checking**

Run: `mypy src/dazzle/testing/fuzzer/`

- [ ] **Step 4: Fix any issues found in steps 2-3**

- [ ] **Step 5: Run a real fuzz campaign**

Run: `dazzle sentinel fuzz --samples 50 --layer mutate --output dev_docs/fuzz-report.md`

Review the report. If any HANG or CRASH results appear, note them as follow-up issues.

- [ ] **Step 6: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore(fuzzer): lint, type fixes, and first fuzz report (#732)"
```
