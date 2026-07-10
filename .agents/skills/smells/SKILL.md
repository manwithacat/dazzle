---
name: smells
description: Two-phase read-only code-smells analysis: regression checks + new systemic patterns
---

Run a two-phase code smells analysis: regression checks against established rules, then a scan for new systemic patterns. This is a read-only analysis — do NOT make any code changes.

**This command runs as a Workflow** (`.claude/workflows/smells.js`): the regression checks, the three pattern-category finders, and the **decay-harness finder** fan out as parallel agents, each returning schema-validated findings. This main loop then writes the report + log from the validated result and presents the summary. (Replaced the hand-rolled "dispatch 4 background subagents" prose — the Workflow gives deterministic fan-out + structured output.)

## Division of labour with the live decay harness (v0.83.26)

Structural decay is now measured precisely and **gated live in CI** by the framework structural-fitness harness — so `/smells` no longer re-derives it by grep heuristics, it *consumes* it:

- **The harness owns structure.** `dazzle fitness code` (churn×complexity hotspot queue → `dev_docs/framework-hotspots.md`), the complexity ratchet (`tests/unit/test_complexity_ratchet.py` + `tests/unit/fixtures/complexity_baseline.json` — gates new CC>15 / MI-rank drops), and the import-linter layer contracts (`[tool.importlinter]` — gates new `core↛back/ui`, `ui↛back`, `back↛sqlite`). The **decay-harness finder** surfaces the *standing baselined debt* these gates hold flat: top hotspots, the MI-rank-C set, the highest-CC functions, ratchet status, and the import allow-list size. Enforcement of *new* structural decay belongs to those gates, not to a smells recommendation.
- **`/smells` owns what the harness can't see.** Its real value-add is the **semantic** smells radon/import-linter are blind to: silent failures / swallowed exceptions, inconsistent error strategy, near-duplicate blocks, `Any`/`# type: ignore` masking, mutable globals/hidden singletons, and compat shims. The `complexity-globals` finder is now *seeded* by the hotspot queue — it spends agent judgment naming the structural smell inside the top decayed files rather than re-counting lines.
- **Net:** regression checks 1.6/1.7 read the radon baseline (no line-count grep); 1.3 notes the import contract subsumes it; 1.9 tracks the allow-list (ratchet posture — it only shrinks). The point of overlap with the harness is intentionally thin.

## Backward Compatibility Policy

**Backward compatibility is NOT a requirement at this stage.** The project has one major user who is fully engaged with the dev process. When recommending fixes:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Do not recommend wrapper functions, re-exports, or compatibility aliases.
- **Communicate breaking changes** via CHANGELOG.md entries and GitHub issue comments. That is sufficient notice.
- **Flag duplication caused by compat shims** as a smell. Wrapper functions that exist solely for backward compatibility are themselves a code smell to be eliminated.

(The workflow's finder prompts already encode this policy + the scope below.)

## Scope

Focus on `src/dazzle/` — the merged tree (`back/`, `ui/`, `render/` all live under it since the #1055 package merge; #1056 was the follow-on mypy burndown). Ignore `tests/`, `examples/`, and auto-generated files.

## 1. Run the workflow

Invoke the **Workflow** tool with `name: "smells"`. It returns:

```
{
  regressions: [{id, check, status: PASS|FAIL|TRACK, details}],
  patterns:    [{pattern, category, instances, root_cause, canonical_fix, done_criteria, enforcement}],
  decay:       {hotspots:[{rank,file,score,churn,mi_rank}], c_rank_files:[…], high_cc_functions:[{file,function,cc}],
                ratchet_status, import_contracts:{status,allowlist_size,entries:[…]}, priority_targets:[…], notes},
  regressed:   <count of FAIL regressions>
}
```

The finders inherit the session model (no `model` override) per the Subagent Model Policy in CLAUDE.md — pattern recognition is judgment work.

## 2. Write the report

From the returned data, write `agent/smells-report.md`:

```
## Code Smells Report — [date]

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
(one row per `regressions` entry)

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
(one row per `patterns` entry, ordered by severity × instance count)

### Structural Decay (live harness)
From `decay`. The CI ratchet + import contracts gate *new* decay; this is the standing baseline.

- **Ratchet:** [`decay.ratchet_status`]   **Import contracts:** [`decay.import_contracts.status`], allow-list size [`decay.import_contracts.allowlist_size`]
- **Priority refactor targets** (high-churn × MI-rank-C): [`decay.priority_targets`]

| Rank | Hotspot file | Score | Churn | MI |
|------|--------------|-------|-------|----|
(top rows from `decay.hotspots`)

Highest-CC functions: (top 3–5 from `decay.high_cc_functions` as `file:function (cc N)`). Note: [`decay.notes`].

### Recommended Next Actions
1. [highest-priority *semantic* pattern — the harness already owns structural enforcement]
2. [second]
3. [the single best refactor target from `decay.priority_targets`, if a finder named a concrete smell inside it]

### Comparison with Previous Round
- Regressions: X checks regressed
- New patterns: Y found
- Resolved since last round: [diff against the previous agent/smells-report.md if present]
- **Decay delta:** files that *climbed* the hotspot ranking vs the previous report's table (rising debt — the leading indicator); any change in `import_contracts.allowlist_size` (must not grow)
```

## 3. Append to the log

Append a timestamped summary to `agent/smells-log.md` (create if missing):

```
## Smells Run — [date]
- Regressions: X/Y checks passed
- New patterns: Z found
- Top concern: [highest priority pattern]
- Decay: ratchet [clean|N violations], import contracts [kept|broken], allow-list [size]; top target [priority_targets[0]]
- Commit: [current HEAD sha]
```

## 4. Report to the user

Present the regression table and the top patterns. **Surface any FAIL regressions first** — those are the ones that broke an established rule (note: `lint-imports` broken in 1.9 or a non-clean `ratchet_status` means a structural gate regressed — treat as a FAIL-class signal). Then give the one-line decay summary (ratchet/contracts status + the single best refactor target). Do NOT make any code changes; this is read-only analysis.
