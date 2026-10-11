# DSL Parser Fuzzer — Design Spec

**Issue**: #732 — DSL parser: improve error surface for near-miss syntax patterns
**Date**: 2026-03-27

## Problem

The DSL parser's error surface is poor for "near-miss" syntax — constructs that look plausible but are structurally wrong. AI agents and humans reading the grammar docs make reasonable inferences and get either cryptic errors or hangs. We need a systematic way to discover these gaps and verify that fixes hold.

## Approach: Hybrid LLM + Mutation Fuzzer

Three generation layers feed a shared classification oracle.

### Layer 1: LLM Generator (Haiku)

A weaker LLM naturally produces the exact distribution of errors we care about — syntactically close but structurally wrong. Haiku pattern-matches well enough to approximate valid DSL but makes the same mistakes real agents make: colon placement, keyword-in-wrong-block, YAML-isms, wrong modifier positions.

**Mechanism**:
- Feed Haiku the grammar summary + a random seed file from `examples/`
- Prompt it to write DSL for a described scenario (vary prompts across construct types)
- ~1000 samples per campaign at ~$0.001/sample
- Store generated samples for reproducibility

**Prompt variations** (one per run, targeting different construct coverage):
- Entity-heavy: "Define a CRM with 5 entities, relationships, and state machines"
- Surface-heavy: "Build admin dashboards with filters, actions, and custom layouts"
- Process-heavy: "Model an approval workflow with branching and SLA tracking"
- RBAC-heavy: "Define 4 personas with scoped access to shared entities"
- Integration-heavy: "Connect to 3 external APIs with webhooks and error handling"
- Kitchen-sink: "Build a complete project management app"

### Layer 2: Grammar-Aware Mutator

Takes valid DSL (from `examples/` or Haiku output) and makes structural mutations. Implemented as Hypothesis strategies.

**Mutation operators**:
- `swap_block_keyword`: Move a keyword to a wrong block type (e.g., `filter:` from workspace → surface)
- `shift_indent`: Indent/dedent a section by one level
- `cross_pollinate`: Graft a fragment from one construct type into another
- `colon_toggle`: Add/remove colons after field names and keywords
- `yaml_ify`: Replace DSL syntax with YAML equivalents (`access: persona(x)` → `allow_personas: ["x"]`)
- `modifier_misplace`: Put entity modifiers on surface fields or vice versa

### Layer 3: Token-Level Mutator

Lex valid DSL via the existing tokenizer, then apply random perturbations. Also Hypothesis strategies.

**Mutation operators**:
- `insert_token`: Insert a random keyword/identifier at a random position
- `delete_token`: Remove a random token
- `swap_adjacent`: Swap two adjacent tokens
- `duplicate_line`: Repeat a random line

### Classification Oracle

For each generated input, run `parse_dsl()` with a 5-second timeout:

| Result | Classification | Severity |
|--------|---------------|----------|
| Parse succeeds (from mutated input) | `unexpected_valid` | Warning — possible parser leniency |
| `ParseError` with actionable message | `clean_error` | Good — no action needed |
| `ParseError` with cryptic message | `bad_error` | Improvement needed |
| Timeout (>5s) | `hang` | Bug — file immediately |
| Unhandled exception (not ParseError) | `crash` | Bug — file immediately |

**Error quality assessment** (optional second pass): Feed the error message back to Haiku and ask "fix this DSL using only the error message." If it can't, the error message is insufficient. This closes the loop on error quality automatically.

### Construct Coverage Tracking

Track which parser constructs each sample exercises. Goal: every block type (entity, surface, workspace, experience, process, story, integration, service, ledger, rhythm, approval, sla) gets hit by at least N samples across the campaign.

## File Layout

```
src/dazzle/testing/fuzzer/
    __init__.py          # Public API: run_campaign(), FuzzResult
    generator.py         # Haiku-based DSL generation
    mutator.py           # Grammar-aware + token-level Hypothesis strategies
    oracle.py            # Classification engine with timeout
    report.py            # Results aggregation → markdown report
    corpus.py            # Load examples/, manage seed corpus + generated samples

tests/unit/test_parser_fuzz.py      # Hypothesis-driven fuzz tests (mutation layers)
tests/unit/test_fuzzer_oracle.py    # Oracle classification unit tests
```

## CLI Integration

```bash
dazzle sentinel fuzz                # Full campaign (all 3 layers)
dazzle sentinel fuzz --layer llm    # Haiku generation only
dazzle sentinel fuzz --layer mutate # Mutation layers only
dazzle sentinel fuzz --samples 500  # Override sample count
dazzle sentinel fuzz --dry-run      # Generate samples, don't classify
```

Fits under `sentinel` — it's a quality scanning concern, alongside the existing `dazzle sentinel scan`.

## Testing Strategy

- `test_parser_fuzz.py`: Hypothesis with `@settings(max_examples=500)` for mutation layers. Runs in normal CI.
- Haiku layer: `@pytest.mark.slow` — requires API key, runs on-demand via CLI.
- `test_fuzzer_oracle.py`: Unit tests with known inputs (valid DSL, known ParseError, known hang patterns from #731).
- Oracle timeout uses `signal.alarm` (Unix) or `multiprocessing` with timeout for cross-platform.

## Success Criteria

1. **No hangs**: Zero inputs cause parser timeout >5s
2. **Actionable errors**: Near-miss patterns produce errors that include correct syntax suggestions
3. **Construct coverage**: All block types exercised by fuzzer
4. **Reproducibility**: Every generated sample is stored with its classification for regression testing

## Dependencies

- `anthropic` SDK (already in `[llm]` extras) — for Haiku generation
- `hypothesis` (already in `[dev]` extras) — for mutation strategies
- No new dependencies required

## Non-Goals

- This fuzzer does not test semantic validation (type checking, FK graph, scope algebra). It tests the parser's syntactic error surface only.
- Not a replacement for hand-written near-miss tests. Phase 1 of #732 (targeted checks for known patterns) is complementary and should proceed independently.
