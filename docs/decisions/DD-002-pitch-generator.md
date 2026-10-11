# DD-002: Pitch deck generator (`dazzle pitch`)

```yaml
id: DD-002
status: PARKED
issues: []
adrs: [0057, 0003]
decided: 2026-10-11
decided_at_sha: 82c9a8571
parent: null
```

## One-line intent

The investor pitch-deck generator (`src/dazzle/pitch/`, `dazzle pitch …`, MCP
`pitch`) is removed under ADR-0057 consumer-forced growth: no consumer has
regenerated a deck, so the ~4k source lines and ~1.9k test lines are parked
rather than maintained.

## Plan (what we already concluded)

Restore, do not redesign. The working implementation lives at
`decided_at_sha` (82c9a8571):

- `src/dazzle/pitch/` — `ir.py` (PitchSpec models), `loader.py`
  (`pitchspec.yaml` load/validate, `PitchSpecValidationResult`),
  `extractor.py` (AppSpec → pitch facts), `generators/` (pptx slides,
  matplotlib charts, markdown narrative, plugin loader).
- `src/dazzle/cli/pitch.py` (`dazzle pitch scaffold|generate|validate|review|update|enrich|init-assets`)
  registered in `src/dazzle/cli/__init__.py`.
- MCP `pitch` tool (`get` op): `src/dazzle/mcp/server/handlers/pitch.py`,
  `_tool_pitch()` in `tools_consolidated.py`, `handle_pitch` in
  `handlers_consolidated.py`, the `pitch_deck` workflow in `mcp/cli_help.py`.
- Tests: `tests/unit/test_pitch_{ir,loader,extractor,generator}.py`.
- Optional extra `pitch = ["python-pptx>=0.6.21", "matplotlib>=3.7.0"]` in
  `pyproject.toml` (and in the CI type-check extras list).

`git checkout 82c9a8571 -- <paths>` restores them; re-run `uv lock`,
regenerate the `mcp-tools` API-surface baseline and the generated reference
pages, and add a CHANGELOG entry.

Counter-priors: do **not** fold deck generation into `sitespec` or the
spec-narrative pipeline; do **not** add an LLM call that writes deck prose
from DSL without the fact-only brief discipline of `dazzle spec brief`.

## Reopen when (consumer force)

1. **Named consumer** — AegisMark (which carries `pitchspec.yaml` and a
   generated `pitch_deck/` directory) or another consumer app asks to
   regenerate a deck from `pitchspec.yaml`.
2. **Evidence** — the request in an issue, or a consumer CI/Makefile step
   invoking `dazzle pitch generate`.
3. **Acceptance that unblocks** — the consumer's `pitchspec.yaml` regenerates
   its deck with `dazzle pitch generate` and is exercised by a consumer test.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- AegisMark's existing deck (`pitch_deck/`) generated from its
  `pitchspec.yaml` — it stays valid as a static artefact in that repo.
- Flense inventory evidence (`docs/reference/flense-inventory.md`):
  `dazzle pitch` CLI and the `pitch` MCP tool at zero uses for every consumer.

## Explicitly out of scope until force

- The marketing site — that is `sitespec`, not pitch.
- New deck formats, themes, or chart types.

## Trail

| Date | Event |
|------|--------|
| 2026-10-11 | Parked (this DD); code removed in Flense ship B1 (ADR-0057 Phase 3) |
