# Stories JSON → DSL Migration

**Date**: 2026-03-11
**Status**: Approved
**Scope**: Deprecate `stories.json` persistence; stories become DSL-only constructs

## Problem

Stories are persisted in `.dazzle/stories/stories.json`, then injected into the linker
symbol table via `_inject_json_stories()` before `build_appspec()`. This creates:

- A dual-storage problem (DSL files *and* JSON for the same concept)
- A fragile injection bridge that caused bugs #463 and #464
- A file that no human reads — agents interact via MCP tools and the KG

Rhythms already reference stories via `story: "ST-001"` in DSL. Stories should live
in DSL too.

## Decision

**Big Bang migration (Approach A).** One coordinated change: extend the DSL grammar,
build an emitter, rewrite persistence, convert examples, delete the JSON path.

No backward-compatibility shims. No dual-path intermediate release.

## DSL Grammar

One addition: optional `status:` field. All other story syntax is unchanged.

```dsl
story ST-001 "Staff sends invoice to client":
  status: accepted
  actor: StaffUser
  trigger: status_changed
  scope: [Invoice, Client]

  given:
    - "Invoice.status is 'draft'"
    - "Client.email is set"

  when:
    - "Invoice.status changes to 'sent'"

  then:
    - "Invoice email is sent to Client.email"
    - "Invoice.sent_at is recorded"

  unless:
    - "Client.email is missing":
        then: "FollowupTask is created"
```

- `status:` is optional, defaults to `draft`
- Valid values: `draft`, `accepted`, `rejected`
- `STATUS` is already a lexer keyword
- No timestamps — git history and KG track that
- `description` works as a docstring after the title (parser already supports this)

## File Organization

- Stories live in `dsl/stories.dsl` (or split across `dsl/stories/*.dsl` for large projects)
- Discovered by `discover_dsl_files()` — no special path logic
- `story propose` appends new story blocks to `dsl/stories.dsl`
- No more `.dazzle/stories/` or `dsl/seeds/stories/` directories

## DSL Emitter

New file: `src/dazzle/core/story_emitter.py`

`emit_story_dsl(story: StorySpec) -> str` serializes a StorySpec to DSL text.

Key rules:
- Omit `status: draft` (it's the default) — keeps proposed stories clean
- Only emit non-empty sections (skip `given:` if empty)
- Convert legacy fields during migration: `preconditions` → `given:`,
  `happy_path_outcome` → `then:`, best-effort for `side_effects`/`constraints`/`variants`

Used by `story propose` and `story save` MCP handlers, and the CLI `story propose` command.

## IR Changes (stories.py)

**Remove**:
- `preconditions`, `happy_path_outcome`, `side_effects`, `constraints`, `variants` fields
- `effective_given`, `effective_then` properties
- `with_status()` method
- `created_at`, `accepted_at` fields
- `StoriesContainer` class

**Keep**:
- `StorySpec` (with remaining fields)
- `StoryStatus` enum — used standalone for filtering/comparison across modules
- `StoryTrigger` enum — used standalone for test design trigger mapping
- `StoryCondition` model — structured parse data (expression + field_path)
- `StoryException` model — condition + then_outcomes (two-field structure)

## Deletions

| Target | Action |
|--------|--------|
| `src/dazzle/core/stories_persistence.py` | Delete entirely |
| `_inject_json_stories()` in `appspec_loader.py` | Delete function |
| All `_inject_json_stories` call sites across MCP handlers | Remove calls |
| Legacy fields on `StorySpec` | Remove (see IR Changes) |
| `.dazzle/stories/` in examples | Delete |
| `dsl/seeds/stories/` in examples | Delete |
| `stories.json` files in examples | Replace with `dsl/stories.dsl` |

## Rewrites

| Module | Change |
|--------|--------|
| `story propose` MCP handler | Emit DSL via `emit_story_dsl()`, append to `dsl/stories.dsl` |
| `story save` MCP handler | Write DSL text to file |
| `story get` / `story wall` handlers | Read from `appspec.stories` (already populated by parser) |
| `story coverage` handler | Read from appspec |
| `get_next_story_id()` | Scan `appspec.stories` instead of JSON |
| CLI `story propose` / `list` / `generate-tests` | Use appspec + emitter |
| `update_story_status()` callers | Rewrite story block in DSL file (find-and-replace `status:` line) |

## Testing

**Unit tests**:
- Parser: `status:` field parsing (all three values + default-to-draft)
- Emitter: round-trip `emit_story_dsl(parse(dsl)) == dsl`
- ID generation from appspec

**Existing test updates**:
- Rewrite/delete tests importing from `stories_persistence`
- Update `StorySpec` construction to use Gherkin fields only
- Update MCP handler tests to expect DSL file output

**Migration validation**:
- Convert each example project `stories.json` → `stories.dsl`
- Run `dazzle validate` on each to confirm parser round-trip
- Full test suite pass after migration

## Migration Script

One-time conversion of existing example projects:
1. Read `stories.json`
2. Convert each story: `preconditions` → `given:`, `happy_path_outcome` → `then:`
3. Best-effort for `constraints` → `unless:` branches, `side_effects` → `then:` items
4. Emit via `emit_story_dsl()` to `dsl/stories.dsl`
5. Delete JSON files and directories

## Out of Scope

- Timestamps in DSL (git/KG handles versioning)
- Multi-file story splitting (can be done later; single file is fine for now)
- Changes to KG population (it already reads from `appspec.stories`)
