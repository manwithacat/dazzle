# App stems (template notes)

Not a runnable example. Copy the pattern into an app’s `stems/` directory
(see `examples/simple_task/stems/` for a minimal worked app).

## What goes here

| File | Purpose |
|------|---------|
| `README.md` | This pointer + how this app relates to framework stems |
| `INDEX.md` | Catalogue of **this app’s** stems only |
| `<domain-stem>.md` | Compressed domain judgement (entities, personas, non-goals) |

## What does *not* go here

- Full SPEC / SPECIFICATION (keep as expressions; link from stems)
- Framework doctrine (live in monorepo `stems/`)
- Runbooks longer than a short reconstruct block

## Inherit

Framework: `stems/INDEX.md` at the Dazzle monorepo root (or installed package docs).
Design system: `packages/hatchi-maxchi/stems/` when UI work touches Hyperparts.
