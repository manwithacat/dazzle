# DD-001: #1617 residuals — poly_ref polish + STI/EAV (consumer-forced)

```yaml
id: DD-001
status: PARKED
issues: [1621, 1622]
adrs: [0027, 0042]
decided: 2026-07-17
decided_at_sha: 190d62e40
parent: 1617
```

## One-line intent

Phases 0–2 of representation substrate (#1617) shipped. **Do not** polish typed
`poly_ref` product surface (#1621) or add STI / classic EAV productization (#1622)
until a **named consumer** forces dual-lock residual or an interrogation failure
that the catalogue cannot answer with TPT / exclusive FKs / JSONB extension.

## Plan (what we already concluded)

### #1621 — Typed poly_ref polish (P3)

**Already true today (substrate):**

- Pattern id `rel.poly_ref`; decide routes to it after four-question fail
- Classify hard-fails hand-rolled `*_type` + `*_id` pairs (`hand_rolled_poly`)
- Framework `AuditEntry` poly skipped as residual (not a product dual-lock)
- ADR-0042 realizes ADR-0027’s pre-committed escape hatch for **scoped** poly
- `dazzle prove representation` / classify / decide are the agent tools

**What P3 is *not*:** re-opening untyped poly or dual-lock host folklore.

**What P3 becomes *when forced*:**

1. Inventory residual gaps from dual-lock (Comment / Attachment / Audit-shaped
   product entities — not framework AuditEntry)
2. Close **render** + **RBAC** + **integrity** holes without ADR-0027 loopholes
3. Keep hand-rolled pairs as hard classify fail
4. Acceptance:
   - Named consumer app uses `poly_ref` **without** host dual-lock
   - `representation prove` green on that app
   - Counter-prior still forbids untyped poly

### #1622 — STI / EAV-as-JSONB (P4)

**Already true today:**

- Catalogue discourages STI and classic EAV (`rel.sti` / `rel.eav` last resort)
- Prefer `subtype_of:` TPT, exclusive FKs, `rel.json_extension` (JSONB + GIN recipe #1619)
- Custom fields → JSONB projections, not EAV joins

**What P4 becomes *when forced*:**

1. **No** STI keyword or classic EAV by default
2. If forced: STI lint (“looks like STI — prefer TPT / exclusive FKs”)
3. Custom fields → JSONB projections only
4. Acceptance: written design or child issue only with named consumer;
   catalogue still marks STI/EAV discouraged

## Reopen when (consumer force)

Any **one** of these is enough to set `status: FORCED` and implement:

| Signal | How to verify |
|--------|----------------|
| **Named dual-lock consumer** | Product/example app documents host dual-lock for Comment/Attachment/Audit (or equivalent) *because* poly_ref cannot express render/RBAC yet |
| **Interrogation fails in writing** | Four-question write-up in the app stems/SPEC that rejects exclusive FKs, TPT, and JSONB extension for a shared-child case |
| **Pilot host fork risk** | Concrete PR or issue in a consumer repo that would otherwise invent `subject_type`+`subject_id` outside `poly_ref` |
| **STI/EAV only** | Named app proves TPT + exclusive FKs + JSONB extension are all insufficient; design child issue cites this DD |

**Not** force signals: “might be nice”, greenfield curiosity, or improve STALE map
noise without a consumer path.

### Force procedure

1. Name the consumer (repo path or issue URL) in this DD under **Trail**.
2. `status: FORCED` + date.
3. Comment on #1621 and/or #1622 with consumer + link to this file.
4. Implement smallest slice that clears acceptance; open children if needed.
5. `status: DONE` when prove + consumer dual-lock removed; close issues.

## Already shipped (do not re-litigate)

| Piece | Where |
|-------|--------|
| Exclusive FK verify + CHECK codegen | #1617 P1 / #1620 |
| Representation decide/classify/prove + MCP | #1617 P0–2 |
| JSONB extension pattern + GIN recipe | #1619 |
| Typed `poly_ref` + scope selector | ADR-0042 / #1448 |
| “No untyped poly” prior | ADR-0027 |
| Hatches ladder | `docs/reference/data-representation.md` |

## Explicitly out of scope until force

- Speculative multi-section poly hubs in examples without a real poly entity
- Reintroducing open polymorphic_ref keyword
- Classic EAV entity tables as a product default
- STI keyword as a first-class authoring path without lint/discouragement

## Trail

| Date | Event |
|------|--------|
| 2026-07-17 | #1617 umbrella closed; #1621 labeled future (parking comment); #1622 future |
| 2026-07-17 | Session review: still no named consumer — stay PARKED; v0.105.0 CI habits only |
| 2026-07-17 | **This DD** created so the plan survives comment rot |
