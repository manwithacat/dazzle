# Dead-Code Residue

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The reviewed inventory behind the dead-definition ratchet: which unreferenced definitions are accepted residue, which family each belongs to, and what would retire it.

The gate is `tests/unit/test_dead_definition_ratchet.py`: it refuses growth of
unreferenced module-level definitions in `src/`, and refuses shrinkage of the
accepted list. Every accepted entry must also carry a family classification
(`tests/unit/fixtures/dead_definitions_families.json`), enforced by
`test_every_baselined_orphan_is_classified` — an inventory nobody has read is not
a review, so a new dead definition cannot be baselined silently.

Nine families, each a decision with a stated retire-when condition:
`optional-extra-plumbing`, `agent-and-loop-legacy`, `superseded-runtime-path`,
`qa-and-testing-helpers`, `error-and-report-helpers`, `semantics-and-kb-residue`,
`doc-generation-residue`, `cli-parity-helpers`, `domain-brief-and-llm-legacy`.

Two things to know before deleting anything the gate names:

1. **Check the finding is real.** Ten baselined entries turned out to be alive —
   the ratchet counted an import's local name but not the imported name, so
   `from m import x as y` read as unused. mypy is the backstop; run it.
2. **Nothing here is public API.** Zero entries appear in
   `docs/api-surface/public-helpers.txt` or `ir-types.txt`.

Full page: `docs/reference/dead-code-residue.md`.
