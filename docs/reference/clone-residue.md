# Clone Residue

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The reviewed inventory behind the clone ratchet: which duplicated function bodies are accepted residue, which family each belongs to, and what would retire it.

The gate is `tests/unit/test_clone_ratchet.py`. It refuses growth of duplicated
bodies across `src/` and refuses shrinkage of the accepted list. Every exact-body
cluster must also carry a family classification
(`tests/unit/fixtures/clone_families.json`), enforced by
`test_every_exact_cluster_is_classified`.

Twenty-one families. Two of them are deliberate *shape* rather than missed
extraction: `dataclass-and-store-boilerplate` (`__init__`, `__aenter__`,
`asdict`) and `per-class-constant-accessors` (each returns a different constant;
only the body shape matches). The rest name a retire-when condition, and three
of them name a specific pair still to extract with its paths — so the next pass
does not rediscover them.

Fixed in this pass: the clock. Fifteen modules defined their own
`datetime.now(UTC)` helper under four different names; they are now one
`dazzle.core.clock.utcnow()`, with a test that fails if a second definition
appears. A test that freezes time patches one name now, not fifteen.

Full page: `docs/reference/clone-residue.md`.
