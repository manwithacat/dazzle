# Stem: Four-layer stack

## Claim

Runtime code is stratified **http → page → render → core**. Dependencies point
**down only**. Rendering is pure (no I/O); HTTP owns transport; page owns
orchestration; core owns IR and domain static structure.

## Reconstruct

- New feature: ask which layer owns it before choosing a file.
- Import linter / architecture tests enforce the stack.
- Typed fragments live in render; route handlers don’t reimplement HTML trees
  by ad-hoc string piles when a fragment path exists.

## Not this

- `core` importing `http`.
- Business rules only in page templates.
- “Just put it in the renderer” for transport concerns.

## Expressions

- ADR-0038 / ADR-0041 (renames and stack)
- `AGENTS.md` › Architecture table
- Import-linter / package layout under `src/dazzle/`
