# DD-003: Agent-audience domain brief (`domain_brief`)

```yaml
# Machine-readable header (keep keys stable — greppable by agents)
id: DD-003
status: PARKED
issues: [1629, 1631]
adrs: [ADR-0057]
decided: 2026-10-12
decided_at_sha: 003c01392
parent: null
```

## One-line intent

The founder-prose → `AGENT_DOMAIN.md` → DSL intermediate is removed until a new
consumer is bootstrapped from founder prose and the `bootstrap` / `spec_analyze`
path proves insufficient. No current consumer uses it (flense inventory: zero
`dazzle domain` hits in AegisMark, cyfuture or pennydreadful; MCP `domain`
unused).

## Plan (what we already concluded)

Restore from `003c01392` rather than redesign:

- `src/dazzle/domain_brief/` (`extract`, `gaps`, `research`, `promote`, `store`,
  `models`, `noun_signals`) — offline, chrome-safe noun mining from founder
  prose into `AGENT_DOMAIN.md` + `agent_domain.json`.
- `src/dazzle/cli/domain_cli.py` — `dazzle domain extract|show|gaps|research|promote`.
- `src/dazzle/mcp/server/handlers/domain.py` + the `domain` tool in
  `tools_consolidated.py` / `handlers_consolidated.py`.
- `bootstrap`'s best-effort `agent_domain` payload and its domain-first
  generation steps; the `agent_domain` KB concept and the domain steps of the
  `first_principles_demo` workflow.
- Tests `tests/unit/test_domain_brief.py` and the extract cases that lived in
  `test_domain_brief_lifecycles.py`.

Lifecycle identification (`lifecycles.py`) was **not** removed: it moved to
`src/dazzle/mcp/server/handlers/spec_lifecycles.py` because `spec_analyze`
uses it. A restore re-imports it from there rather than re-forking it.

Counter-priors that still hold when forced: the domain doc is a cognition
draft, never SSOT; it never writes DSL; it never invents chrome nouns
(`bootstrap_pollution`).

## Reopen when (consumer force)

1. **Named consumer** — a new consumer app is bootstrapped from founder prose
   (a SPEC/brief, not an existing codebase).
2. **Evidence the kept path is insufficient** — the `bootstrap` /
   `spec_analyze` draft plus founder questions demonstrably mis-models that
   consumer's domain (polluted nouns, lost lifecycles or owners), recorded in
   this DD's Trail with the consumer path.
3. **Acceptance that unblocks** — the consumer's first DSL is authored from a
   restored `AGENT_DOMAIN` with fewer corrections than the bootstrap path.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Restore from `003c01392` per the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- The three consumers' DSL (AegisMark, cyfuture, pennydreadful) was authored
  without the domain intermediate.
- `bootstrap` and `spec_analyze` remain the new-consumer entry point, with
  `bootstrap_pollution` as the standing counter-prior.

## Explicitly out of scope until force

- `bootstrap` and `spec_analyze` — they stay and are not part of this parking.
- Re-adding `AGENT_DOMAIN.md` / `agent_domain.json` to the example apps.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); removed in flense ship C (ADR-0057, Phase 3) |
