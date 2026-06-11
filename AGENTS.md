# AGENTS.md

**Canonical agent instructions live in [`.claude/CLAUDE.md`](.claude/CLAUDE.md). Read that file first — it is maintained and drift-gated; this one deliberately is not a copy.**

This stub exists because some agent harnesses look for `AGENTS.md` by convention. A
previous full-content version of this file rotted 21 minor versions behind the codebase
and actively misled agents (wrong UI architecture, wrong toolchain, wrong commands), so
it was replaced with this pointer (#1367). Do not add project facts here: anything
duplicated from `.claude/CLAUDE.md` will drift, and `tests/unit/test_docs_drift.py`
enforces that this file stays a stub.

Quick orientation, then go read the canonical file:

- **What this is**: DAZZLE — a DSL-first, PostgreSQL-only, server-rendered framework
  where `.dsl` files parse to a typed IR that the runtime executes directly (no codegen).
- **Project instructions**: [`.claude/CLAUDE.md`](.claude/CLAUDE.md) — architecture map,
  style rules, commands, MCP/CLI boundary, gotchas.
- **Decisions**: [`docs/adr/INDEX.md`](docs/adr/INDEX.md).
- **Current version**: see `pyproject.toml`.
