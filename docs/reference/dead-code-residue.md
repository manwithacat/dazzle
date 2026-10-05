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

## The families, and what retires each

| family | n | retires when |
|---|---|---|
| `superseded-runtime-path` | 16 | each entry is re-wired, or confirmed superseded by name — the leftovers of ADR-0023 (Jinja2 → typed Fragments), ADR-0038's four-layer split, and the tenant-hierarchy work |
| `qa-and-testing-helpers` | 10 | the UX contract suite stops referencing them, or they fold into the runner that does |
| `error-and-report-helpers` | 8 | the callers are gone and no dynamic use remains — error constructors and introspection helpers |
| `agent-and-loop-legacy` | 7 | the legacy agent entrypoints are deleted in favour of the current loop |
| `semantics-and-kb-residue` | 5 | the user-profile / session surface settles (`_session_to_dict` is the largest single item) |
| `doc-generation-residue` | 5 | the docs generator is wired again, or the surface is dropped |
| `cli-parity-helpers` | 3 | `cli/project.py` absorbs the last caller, or the entry has zero callers and retires outright — the taxonomy has no column for "no caller left", which the fresh benchmark run hit |
| `optional-extra-plumbing` | 4 | **the wiring lands, or the capability is formally dropped** — see below |
| `domain-brief-and-llm-legacy` | 3 | the pitch asset path is confirmed dead or re-wired |

`optional-extra-plumbing` (`create_kafka_bus`, `create_s3_file_service`,
`create_jwt_service`, `SMTPInboundAdapter`) is the family to worry about: these are
meant to be reachable when the matching extra is installed, and nothing
constructs them. That is either missing wiring — a bug report — or a dropped
feature, and the answer changes what the fix is.

## The trap when you go looking

`scim_provisioning.py::_member_ids` sits directly beside the live
`leftover_honest_scim_member_ids`, and the live one's docstring cites the dead
one by name as the historical culprit. Reading the code alone, the pair looks
like a helper and its caller. The ratchet is right about which is which; your eyes
are not, which is why the gate exists.
