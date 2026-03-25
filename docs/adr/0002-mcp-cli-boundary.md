# ADR-0002: MCP/CLI Boundary

**Status:** Accepted
**Date:** 2026-03-13

## Context

Dazzle exposes two extensibility surfaces to AI agents and developers:

- **MCP tools** — callable from Claude Code mid-conversation via the Model Context Protocol
- **CLI commands** — shell commands invoked via `dazzle <group> <command>`

As the system grew, the boundary between these surfaces became ambiguous. Some operations were duplicated across both. Others were placed arbitrarily in one surface based on implementation convenience rather than design intent.

The key tension:

1. MCP tool calls **block the Claude Code conversation thread** while they execute. Long-running operations (LLM calls, file generation, database writes) inserted into MCP freeze the agent.
2. Anthropic guidance states MCP is intended for **context retrieval** — giving the model information, not doing work on its behalf.
3. Without a clear rule, contributors placed operations inconsistently, making the system hard to reason about.

## Decision

Apply a single boundary test to every operation:

> **"Can Claude continue thinking while this runs?"**
> - Yes → MCP tool
> - No → CLI command

This yields two clear categories:

**MCP tools** handle stateless knowledge and query operations:
- Read DSL structure, validate, inspect entities and surfaces
- Query the knowledge graph, semantics KB, inference engine
- Retrieve stories, rhythms, processes, test designs
- Report on policy, composition, sentinel findings
- All operations are reads with no side effects

**CLI commands** handle process operations:
- Generate files, emit DSL, write to disk
- Call LLMs (propose stories, evaluate rhythms, improve test coverage)
- Run database operations (reset, verify, backup)
- Execute E2E tests, fire webhooks, inject mock errors
- Anything with observable side effects

## Consequences

### Positive

- Agents experience no blocking on knowledge lookups — MCP calls are fast reads
- LLM-intensive operations run in CLI where latency is acceptable and expected
- Clear rule for contributors: side effect → CLI, no side effect → MCP
- MCP tool surface stays lean and auditable

### Negative

- Some workflows require alternating between MCP reads and CLI writes
- Tooling must be maintained in two places for related operations (e.g., `test_design` MCP read + `dazzle test-design propose` CLI write)

### Neutral

- Existing operations audited and reassigned where the boundary was violated
- CLAUDE.md documents the boundary test as canonical guidance

## Alternatives Considered

### 1. Monolithic MCP Server

Expose all operations — generation, LLM calls, file writes — as MCP tools.

**Rejected:** Blocks Claude Code during long-running operations. Violates Anthropic MCP intent. Produces unpredictable agent behaviour under latency.

### 2. All Operations as CLI Only

Remove MCP entirely; agents call `dazzle` commands for everything including reads.

**Rejected:** Eliminates fast in-context knowledge retrieval. Agents must parse CLI output rather than receiving structured data. Significantly degrades agent reasoning quality.

## Implementation

See `CLAUDE.md` — MCP/CLI Boundary section lists all 24 MCP tools and all CLI command groups with their current classification.
