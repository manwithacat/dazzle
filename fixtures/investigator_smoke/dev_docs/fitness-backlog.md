# Fitness Backlog

Structured findings from the Agent-Led Fitness Methodology. Each row is
self-contained via `evidence_embedded` — durable after the underlying ledger
has expired.

| id | created | locus | axis | severity | persona | status | route | summary |
|----|---------|-------|------|----------|---------|--------|-------|---------|
| f_smoke_001 | 2026-04-14T00:00:00+00:00 | implementation | coverage | high | admin | PROPOSED | soft | fixtures/investigator_smoke/src/ui/form.html:4 error paragraph present but no aria-describedby wiring |

## Evidence envelopes

### f_smoke_001

```json
{
  "id": "f_smoke_001",
  "created": "2026-04-14T00:00:00+00:00",
  "run_id": "smoke-run",
  "cycle": null,
  "axis": "coverage",
  "locus": "implementation",
  "severity": "high",
  "persona": "admin",
  "capability_ref": "Form.submit",
  "expected": "error paragraph linked to control via aria-describedby",
  "observed": "fixtures/investigator_smoke/src/ui/form.html:4 error paragraph present but no aria-describedby wiring",
  "evidence_embedded": {
    "expected_ledger_step": {
      "step": 1,
      "description": "check describedby"
    },
    "diff_summary": [],
    "transcript_excerpt": [
      {
        "text": "fixtures/investigator_smoke/src/ui/form.html:4 error paragraph missing describedby link"
      }
    ]
  },
  "disambiguation": false,
  "low_confidence": false,
  "status": "PROPOSED",
  "route": "soft",
  "fix_commit": null,
  "alternative_fix": null
}
```
