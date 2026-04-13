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
