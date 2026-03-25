# ADR-0006: Immutable Frozen IR

**Status:** Accepted
**Date:** 2026-02-01

## Context

The Dazzle IR (Intermediate Representation) is the in-memory object graph produced by the parser and consumed by the runtime, code generator, LSP server, MCP tools, and compliance pipeline. Multiple consumers read the same `AppSpec` simultaneously.

Early IR types were plain dataclasses or loosely-typed dicts. As the pipeline grew, two problems emerged:

1. **Silent mutation** — a consumer could modify an IR node and affect downstream consumers that expected the original value. Bugs of this kind are difficult to reproduce because they depend on pipeline execution order.
2. **Caching unsafety** — IR snapshots cannot be safely cached or hashed if their contents can change after creation.

The IR is also the primary data shape crossing every module boundary in the codebase, making it the highest-leverage place to enforce immutability.

## Decision

All IR types use **Pydantic v2** with `model_config = ConfigDict(frozen=True)`.

The parser → linker → runtime → codegen pipeline treats the IR as an **immutable snapshot**:

- The parser produces a frozen `AppSpec`.
- The linker resolves cross-references and returns a new frozen `AppSpec` — it never mutates the input.
- The runtime and codegen receive the frozen spec and read from it only.
- Any transformation that needs a modified IR creates a new model instance via `model.model_copy(update={...})`.

No IR node may be mutated after construction. Pydantic enforces this at runtime; mypy enforces it statically via the `frozen=True` config.

## Consequences

### Positive

- Consumers can safely hold references to IR nodes without defensive copying.
- IR instances are hashable and can be used as dict keys or cached with `functools.lru_cache`.
- Transformation pipeline is auditable: each stage produces a new object rather than mutating in place.
- Thread-safe by construction — parallel consumers of the same `AppSpec` need no locking.

### Negative

- Constructing modified IR (e.g. in tests or the linker) requires `model_copy(update={...})` rather than attribute assignment — slightly more verbose.
- Pydantic v2 `frozen=True` raises `ValidationError` on attempted mutation at runtime, which surfaces latent bugs as hard errors rather than silent corruption.

### Neutral

- All IR types live in `src/dazzle/core/ir/` and are imported by every pipeline stage.
- Non-IR internal models (e.g. agent transcript, MCP request/response) are not required to be frozen.

## Alternatives Considered

### 1. Mutable Dataclasses

Use `@dataclass` without restrictions, relying on developer discipline not to mutate.

**Rejected:** Discipline does not scale. Silent mutation bugs already occurred during early development.

### 2. Post-Parse Modifications

Allow a "mutable phase" before the IR is handed to consumers, then freeze.

**Rejected:** The boundary between mutable and immutable phases is hard to enforce and creates the same confusion as full mutability.

### 3. Live Mutable State Objects

Keep a shared mutable `AppSpec` that the runtime updates in response to DSL reloads.

**Rejected:** Requires locking, makes consumers stateful, and violates the single-responsibility principle. DSL reloads produce a new frozen `AppSpec` and replace the reference atomically.

## Implementation

IR types are defined in `src/dazzle/core/ir/`. The `ConfigDict(frozen=True)` config is set on the base IR model and inherited by all subtypes. The linker in `src/dazzle/core/linker.py` uses `model_copy` for all derivations.
