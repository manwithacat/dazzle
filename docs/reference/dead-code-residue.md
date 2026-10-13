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

Six families, each a decision with a stated retire-when condition:
`agent-and-loop-legacy`, `qa-and-testing-helpers`, `semantics-and-kb-residue`,
`doc-generation-residue`, `cli-parity-helpers`, `error-and-report-helpers`. Three
more were retired on 2026-10-13: `superseded-runtime-path` and
`optional-extra-plumbing` in flense ship K (every entry deleted, because the wiring
had been absent for more than one release and no Deferred Decision covered it — the
S3 backend, the JWT factory and the device routes had live replacements or no
consumer), and `domain-brief-and-llm-legacy` in ship J (`llm/spec_analyzer` went
with the `analyze-spec` command).

Two things to know before deleting anything the gate names:

1. **Check the finding is real.** Ten baselined entries turned out to be alive —
   the ratchet counted an import's local name but not the imported name, so
   `from m import x as y` read as unused. mypy is the backstop; run it.
2. **Nothing here is public API.** Zero entries appear in
   `docs/api-surface/public-helpers.txt` or `ir-types.txt`.

## The families, and what retires each

| family | n | retires when |
|---|---|---|
| `agent-and-loop-legacy` | 5 | the legacy agent entrypoints are deleted in favour of the current loop |
| `qa-and-testing-helpers` | 4 | the RBAC proof and walk-pack code stop referencing them, or they fold into the runner that does |
| `semantics-and-kb-residue` | 3 | the MCP state / serializer surface settles |
| `doc-generation-residue` | 3 | the docs generator is wired again, or the surface is dropped |
| `cli-parity-helpers` | 2 | `cli/project.py` absorbs the last caller, or the entry has zero callers and retires outright — the taxonomy has no column for "no caller left", which the fresh benchmark run hit |
| `error-and-report-helpers` | 2 | the callers are gone and no dynamic use remains — error constructors and introspection helpers |

When an entry has had no caller for more than one release and no Deferred
Decision names it, delete it (and its row here) rather than re-classifying it:
that is how the three retired families went.

## The trap when you go looking

`scim_provisioning.py::_member_ids` sits directly beside the live
`leftover_honest_scim_member_ids`, and the live one's docstring cites the dead
one by name as the historical culprit. Reading the code alone, the pair looks
like a helper and its caller. The ratchet is right about which is which; your eyes
are not, which is why the gate exists.
