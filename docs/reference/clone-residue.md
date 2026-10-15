# Clone Residue

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The reviewed inventory behind the clone ratchet: which duplicated function bodies are accepted residue, which family each belongs to, and what would retire it.

The gate is `tests/unit/test_clone_ratchet.py`. It refuses growth of duplicated
bodies across `src/` and refuses shrinkage of the accepted list. Every exact-body
cluster must also carry a family classification
(`tests/unit/fixtures/clone_families.json`), enforced by
`test_every_exact_cluster_is_classified`.

Fourteen families. Two are deliberate *shape*, not missed extraction:
`dataclass-and-store-boilerplate` (`__init__`, `__aenter__`, `asdict`) and
`per-class-constant-accessors` (only the body shape matches). Two are detector
artefacts: `ir-facade-accessors` and `consolidated-tool-wrappers` import a
*different* function under one local alias, and the exact-body serialiser drops
import names. `auth-domain-and-connection-helpers` is down to the org-context
select/switch pair; its enterprise-auth members went with ship AD (DD-013).

Fixed: the clock (one `dazzle.core.clock.utcnow()`, gated); flense ship AH: 35 of
76 exact and 19 of 62 structural clusters (parser keyword handlers, naming, cron,
SQL quoting, the state-machine twin, the lazy Postgres store).

Full page: `docs/reference/clone-residue.md`.
