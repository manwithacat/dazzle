# rbac_validation — NIST 800-162 ABAC probe

A medical-clinic domain (8 entities × 8 personas) used by `tests/unit/test_rbac_validation.py` to verify the framework's RBAC + scope semantics against the NIST SP 800-162 ABAC reference model.

This is a **framework-validation fixture**, not a user-facing example. It exists to stress the policy engine across the full role × entity × operation space. Don't use it as a teaching app — for that, see [`examples/`](../../examples/).

## What this fixture probes

| Surface area | How |
|--------------|-----|
| Role-based `permit:` rules | 8 roles, varied entity coverage from broad (`Patient`, `Appointment`) to narrow (`AuditLog: admin-only`) |
| Scope predicates with FK chains | `MedicalRecord.patient_id`, `Prescription.doctor_id`, etc. exercise the predicate algebra against the FK graph |
| Persona-action negative space | `intern` and `outsider`-equivalent personas have most operations explicitly denied — failures here catch over-permissive defaults |
| Audit-log integrity | `AuditLog` is admin-read-only by construction — confirms the framework rejects mutations from non-privileged roles |
| Static matrix vs runtime decisions | The static matrix derived from the DSL must match the runtime decisions logged by the policy engine |

## Design rules for extension

If you add to this fixture, do it deliberately:

1. **Add a new persona** when you want to probe a *role pattern* not yet covered (delegated authority, time-bounded grant, conditional approval). Don't add personas to model "more clinic staff" — that's domain drift.
2. **Add a new entity** when you want a *scope shape* not yet covered (deeper FK chain, junction-table EXISTS, negated NOT-EXISTS). Don't add entities to flesh out the clinic domain.
3. **Add a new permission rule** to exercise a *predicate form* — boolean combinations, FK-path traversals, literal-null filters. Each new rule should map to a NIST 800-162 check in the test file.
4. **Don't add UI** — no workspaces, no surfaces beyond what the test requires. This is a policy-engine probe, not an app.

If the entity/persona/rule doesn't map to a documented NIST check or a Dazzle predicate-algebra form, it doesn't belong here.

## What does NOT belong here

- Realistic medical-domain workflows (appointment scheduling, prescription refills, lab-result lifecycles) — those are app concerns.
- Real PII or HIPAA-shaped test data — fixture values are abstract on purpose.
- Story coverage, fidelity scoring, or UX contracts — separate test surfaces.
- Performance benchmarks — keep the fixture small enough that the test runs in under a second.

## Running the tests

```bash
pytest tests/unit/test_rbac_validation.py -v
```

Expected: ~22 tests, well under 1 second. If you add a fixture entity or persona, the test parametrisation should grow accordingly — a fixture change that doesn't move test counts is a signal that the new shape isn't being probed.

## See also

- `tests/unit/test_rbac_validation.py` — the NIST 800-162 check suite
- [`fixtures/shapes_validation`](../shapes_validation/) — the sibling fixture, probing tenant-scoped RBAC patterns
- `docs/reference/rbac-verification.md` — public-facing RBAC verification framework
- `src/dazzle/rbac/` — the matrix + audit + verifier implementation
- NIST SP 800-162: https://csrc.nist.gov/publications/detail/sp/800-162/final
