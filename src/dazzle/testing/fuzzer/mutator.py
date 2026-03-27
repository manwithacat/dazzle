"""Token-level and grammar-aware mutation strategies for DSL fuzzing.

Each mutator takes DSL text + a deterministic seed and returns mutated text.
Determinism allows reproducing specific failures.
"""

from __future__ import annotations

import random

# Keywords that appear in various DSL constructs — used for insertion mutations
DSL_KEYWORDS: list[str] = [
    "entity",
    "surface",
    "workspace",
    "experience",
    "process",
    "story",
    "rhythm",
    "service",
    "integration",
    "ledger",
    "approval",
    "sla",
    "persona",
    "scenario",
    "field",
    "action",
    "section",
    "mode",
    "permit",
    "scope",
    "for",
    "uses",
    "filter",
    "sort",
    "ux",
    "required",
    "unique",
    "pk",
    "owner",
    "access",
    "step",
    "when",
    "on",
    "schedule",
    "enum",
    "view",
    "webhook",
    "island",
    "has_many",
    "has_one",
    "belongs_to",
    "ref",
    "bool",
    "str",
    "int",
    "text",
    "uuid",
    "date",
    "datetime",
    "email",
    "json",
    "money",
    "state_machine",
    "state",
    "transition",
    "trigger",
]

# Common YAML-isms and wrong-syntax patterns agents produce
NEAR_MISS_FRAGMENTS: list[str] = [
    'allow_personas: ["admin"]',
    "filter: status = active",
    'field name "Name": required',
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
        if first_word in (
            "entity",
            "surface",
            "workspace",
            "process",
            "story",
            "rhythm",
            "persona",
            "integration",
            "service",
        ):
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
    result_lines = (
        target_lines[:insert_pos] + [""] + fragment_lines + [""] + target_lines[insert_pos:]
    )
    return "\n".join(result_lines)
