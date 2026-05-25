---
id: regex_in_dsl_parser
name: Regex in the DSL parser
layer: grammar
status: active
summary: >-
  When a DSL parser reaches for `re.compile`, the right next step is a new IR
  type + dispatcher method — not a regex. Regex parses a string at runtime;
  the IR is invisible to the linter, IDE completion, doc generators, and the
  predicate validators. ADR-0024 + `tests/unit/test_no_regex_in_parser.py`
  enforce the closure; the allowlist sits at zero.
triggers_text:
  - "parse this shape with regex"
  - "use re.compile"
  - "match the DSL pattern"
  - "regex on a call form"
  - "regex on a keyword"
  - "easier to regex than parse"
triggers_code:
  - 're\.compile\b'
  - 'import\s+re\b'
  - '_RE\s*=\s*re\.'
refs:
  adrs:
    - ADR-0024
  tests:
    - tests/unit/test_no_regex_in_parser.py
---

# Regex in the DSL parser

## The corpus prior

Tutorials on writing DSLs, mini-languages, and config parsers default to regex. Stack Overflow's top answers to "how do I parse this format" overwhelmingly recommend a `re.compile(...)` followed by `.match(...)`. The corpus is full of parsers that started as one regex and grew capture groups, branches, and lookaheads as the syntax accreted features.

The shape feels appealing because it's compact and the example always works on the toy input. The cost shows up later: regex on grammar shapes hides the structure from every other tool that wants to read it (IDE completion, linter, doc generator, validator), forces every downstream consumer to re-parse the same string, and accretes hacks (`(?P<disambiguator>...)` branches, special-case captures) instead of admitting that the grammar is now a real grammar.

## Wrong shape

```python
_AGGREGATE_RE = re.compile(
    r"^(?P<func>count|sum|avg|min|max)\((?P<arg>\w+)\)$"
)


def _parse_aggregate(text: str) -> dict | None:
    m = _AGGREGATE_RE.match(text.strip())
    if not m:
        return None
    return {
        "function": m.group("func"),
        # count(X) means "rows of entity X"; sum/avg/etc. mean "column X"
        "is_entity_count": m.group("func") == "count",
        "target": m.group("arg"),
    }
```

What this gives up:

- The disambiguation (`is_entity_count = func == "count"`) is invisible to the IR. The linter can't reason about it; the validator can't cross-check it against the FK graph.
- Adding a new aggregate form (e.g. cross-entity `count(X via Junction)`) means either bolting a second regex on, or extending the capture groups until the regex is unreadable — and either way, downstream consumers still see strings.
- Tests against the regex pass; tests against semantic intent are hard to write because the IR shape is implicit.
- Real symptom from #1144: the regex closed off cross-entity aggregates as a side-effect, visible only when the issue surfaced.

## Right shape

Recognise the regex as a *signal* — the grammar is asking to be extended.

1. Add an IR type (Pydantic, frozen) that captures the semantic shape, not the lexical surface: `AggregateExpr(function: Literal["count", "sum", ...], target: AggregateTarget, ...)`.
2. Write a recursive-descent / dispatcher method in `src/dazzle/core/dsl_parser_impl/` that consumes tokens and emits the IR. See `core/dsl_parser_impl/aggregate.py` for the canonical shape.
3. The validator and linter now have something to inspect. Cross-entity validation becomes a checked property, not a runtime surprise.
4. The regex disappears entirely — it served as scaffolding for a missing IR type, and it's not needed once the IR exists.

The narrow exception is **lexical**-shape regex inside a single token: identifiers, duration literals (`"5m"`, `"3h"`), numeric forms, escape sequences. Those are tokenisation, not grammar. They live in `_lexical.py` modules and stay small.

## Why this matters here

Dazzle's DSL is agent-first (ADR-0004) and precision-over-ergonomics. Every IR type is a hook that downstream tooling — IDE completion, hover docs, scope validator, fitness investigator, MCP introspection — can use to reason about author intent. A regex hides intent inside a string. The framework's whole value model assumes the IR is rich enough to be the substrate; regex-in-parser is a hole in the substrate.

ADR-0024 codifies the rule. `tests/unit/test_no_regex_in_parser.py` enforces it with an allowlist that sits at zero and is meant to *shrink*, not grow. When the test fails on a new parser commit, the question is not "how do we widen the allowlist" but "which IR type did we forget to add."

## Cross-references

- ADR-0024 (no regex in DSL parser) — the formal closure.
- `tests/unit/test_no_regex_in_parser.py` — the drift gate.
- `src/dazzle/core/dsl_parser_impl/aggregate.py` — the migration that proved the pattern (issue #1144).
- `src/dazzle/core/dsl_parser_impl/_lexical.py` — where lexical-shape regex is allowed.
