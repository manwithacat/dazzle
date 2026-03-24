# Compliance Framework

Dazzle can automatically assess how well your DSL specification maps to recognised compliance frameworks. Because the DSL is a complete, machine-readable description of your application — its entities, access rules, personas, processes, stories, and data classifications — Dazzle can walk that specification and produce a per-control audit assessment without requiring you to write any additional documentation.

The result is an **AuditSpec**: a typed, JSON-serialisable document that lists every control in the target framework, the DSL evidence found (or not found) for it, and a tier rating indicating how complete that evidence is. You can query the AuditSpec through the CLI or via MCP.

---

## Supported Frameworks

| Framework | ID | Controls | Source |
|-----------|----|----------|--------|
| ISO/IEC 27001:2022 | `iso27001` | 93 (across 4 themes) | ISO/IEC JTC 1/SC 27 |
| SOC 2 Type II — Trust Services Criteria | `soc2` | 64 (across 5 criteria) | AICPA (2017, revised 2022) |

**ISO/IEC 27001:2022** organises its Annex A controls into four themes:
- **Organisational Controls** (A.5.x) — policies, roles, information handling, supplier relations
- **People Controls** (A.6.x) — screening, employment conditions, awareness, remote working
- **Physical Controls** (A.7.x) — physical security, equipment maintenance, clear-desk policy
- **Technological Controls** (A.8.x) — endpoint security, identity management, monitoring, cryptography

**SOC 2 TSC** maps to five Trust Services Criteria:
- **Security** — Common Criteria (CC1–CC9), the mandatory baseline
- **Availability** — system uptime and capacity
- **Confidentiality** — protection of confidential information
- **Processing Integrity** — complete, valid, accurate, timely processing
- **Privacy** — personal information lifecycle

Not every control is mappable to DSL constructs. Controls that have no `dsl_evidence` mapping in the framework YAML are marked `excluded` (tier 0). This is expected — organisational governance, physical security, and HR controls cannot be evidenced by a DSL specification.

---

## How It Works

The pipeline runs in three stages:

```
Framework YAML  ──┐
                  ├─→  compile_auditspec()  ──→  AuditSpec
DSL files  ──────┘
```

**Stage 1 — Taxonomy loading.** Dazzle reads the framework YAML from `src/dazzle/compliance/frameworks/<id>.yaml`. The YAML describes every control and lists which DSL constructs count as evidence for that control (the `dsl_evidence` list). The loader validates the structure and returns a `Taxonomy`.

**Stage 2 — Evidence extraction.** Dazzle parses your DSL files into an `AppSpec` IR (the same IR used by the runtime). The evidence extractor walks the IR and collects items for ten construct categories:

| Category | What is extracted |
|----------|--------------------|
| `classify` | Data classification directives on entities |
| `permit` | Access control rules (permit blocks) |
| `scope` | Row-filter scope rules |
| `visible` | Field visibility rules |
| `transitions` | State machine transition definitions |
| `process` | Named process definitions |
| `persona` | Persona/archetype definitions |
| `story` | User story definitions |
| `grant_schema` | Delegation rules (also satisfies `permit` evidence) |
| `llm_intent` | AI intent declarations (also satisfies `classify` evidence) |

Some categories are aliases. `grant_schema` satisfies `permit` evidence because delegation rules document access control policy. `llm_intent` satisfies `classify` evidence because AI intent configuration documents data handling governance. `workspace` satisfies `personas` evidence in the taxonomy lookup. The full mapping is in `src/dazzle/compliance/compiler.py` (`CONSTRUCT_TO_KEY`).

**Stage 3 — Compilation.** For each control, Dazzle checks whether the extracted evidence contains items matching any of that control's expected construct categories. A control with at least one match is `evidenced` (tier 1). A control with no match and at least one expected category is a `gap` (tier 3). A control with no expected categories at all is `excluded` (tier 0).

The output is written to `.dazzle/compliance/output/<framework>/auditspec.json`.

---

## CLI Commands

### `dazzle compliance compile`

Run the full pipeline and write the AuditSpec.

```bash
dazzle compliance compile
dazzle compliance compile --framework soc2
dazzle compliance compile --framework iso27001 --output /tmp/audit.json
```

Sample output:

```
Compliance: ISO/IEC 27001:2022
  Controls: 93
  Evidenced: 41
  Partial: 0
  Gaps: 21
  Excluded: 31
  Coverage: 44.1%

  Output: .dazzle/compliance/output/iso27001/auditspec.json
```

The `--output` flag writes an additional copy to the given path. The canonical output is always written to `.dazzle/compliance/output/<framework>/auditspec.json` regardless.

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--framework`, `-f` | `iso27001` | Framework ID: `iso27001` or `soc2` |
| `--output`, `-o` | *(none)* | Additional output path for auditspec JSON |

---

### `dazzle compliance evidence`

Show which DSL constructs were found in the current project, without running the full compile.

```bash
dazzle compliance evidence
```

Sample output:

```
DSL Evidence
  classify: 4 items
  permit: 12 items
  scope: 9 items
  visible: 3 items
  transitions: 7 items
  process: 5 items
  persona: 6 items
  story: 14 items
  grant_schema: 2 items
  llm_intent: 0 items
```

Zero-item categories are shown dimmed. Use this command before compiling to understand whether your DSL has the constructs needed for coverage — if `persona` is 0 items, any control that requires `persona` evidence will be a gap.

---

### `dazzle compliance gaps`

Compile and print only the controls with gaps or partial evidence.

```bash
dazzle compliance gaps
dazzle compliance gaps --framework soc2
dazzle compliance gaps --tier 3          # gaps only (no partials)
dazzle compliance gaps --tier 2,3        # gaps and partials (default)
```

Sample output:

```
Compliance Gaps (14 controls)
  A.5.7  Threat intelligence (tier 3)
  A.5.9  Inventory of information and other associated assets (tier 3)
  A.6.3  Information security awareness, education and training (tier 3)
  A.8.16 Monitoring activities (tier 3)
  ...
```

Gap lines are printed in red; partial lines in yellow. The `--tier` flag accepts a comma-separated list of tier numbers.

| Flag | Default | Description |
|------|---------|-------------|
| `--framework`, `-f` | `iso27001` | Framework ID |
| `--tier` | `2,3` | Tiers to display (2 = partial, 3 = gap) |

---

## MCP Operations

The `compliance` MCP tool provides the same pipeline operations for use inside Claude. All operations accept a `framework` argument defaulting to `iso27001`.

### `compile`

Returns the full AuditSpec JSON. Use this when you need control-level detail for a specific theme or set of controls.

```
compliance compile framework=soc2
```

### `evidence`

Returns the EvidenceMap JSON — the raw evidence extracted from the DSL before it is mapped to controls. Useful for understanding what Dazzle found before the compile step.

```
compliance evidence
```

### `gaps`

Returns only the `gap` and `partial` ControlResults. Faster than `compile` when you only need to know what is missing.

```
compliance gaps framework=iso27001
```

Returns:
```json
{
  "gaps": [
    {
      "control_id": "A.5.7",
      "control_name": "Threat intelligence",
      "theme_id": "organisational",
      "status": "gap",
      "tier": 3,
      "evidence": [],
      "gap_description": "",
      "action": ""
    }
  ],
  "count": 14
}
```

### `summary`

Returns only the `AuditSummary` counts. Useful for a quick health check.

```
compliance summary
```

Returns:
```json
{
  "total_controls": 93,
  "evidenced": 41,
  "partial": 0,
  "gaps": 21,
  "excluded": 31
}
```

### `review`

Returns a review-tracking structure for all tier 2 and tier 3 controls. Each entry has a `status` of `"draft"` (tier 2) or `"stub"` (tier 3) and a `resolved` flag. Intended for human-in-the-loop review workflows.

```
compliance review framework=iso27001
```

---

## Evidence Mapping Reference

The table below shows which DSL constructs satisfy which compliance control categories. A control lists one or more expected constructs in its `dsl_evidence` list; any matching evidence item marks the control as `evidenced`.

| DSL Construct | Taxonomy Category | What it evidences |
|---------------|-------------------|-------------------|
| `classify` on an entity field | `classify` | Data classification policy, information handling, GDPR-style data governance |
| `permit` block on an entity | `permit` | Access control policies, least-privilege, role-based access |
| `scope:` block on an entity | `scope` | Row-level data isolation, multi-tenancy, data minimisation |
| `visible:` on an entity | `visible` | Field-level visibility controls, need-to-know enforcement |
| `transitions:` / state machine | `transitions` | Lifecycle management, change management, audit trail |
| `process` definition | `process` | Documented operational procedures, workflow governance |
| `persona` / `archetype` | `persona` | Security roles, responsibilities, organisational structure |
| `story` definition | `story` | Control validation, acceptance criteria, test evidence |
| `grant_schema` | `permit` (alias) | Delegation policies, administrative access governance |
| `llm_intent` | `classify` (alias) | AI data handling governance, automated processing disclosure |
| `workspace` | `personas` (alias) | Role-specific interface boundaries, responsibility segregation |
| `scenarios` in stories | `stories` (alias) | Scenario-based control validation |

### Which frameworks use which constructs

**ISO 27001** makes heavy use of `classify`, `permit`, `scope`, `transitions`, `process`, `persona`, and `story`. The Technological Controls theme (A.8.x) also uses `visible` for field-level access controls.

**SOC 2** places significant weight on `permit`, `scope`, `persona`, and `story` for the Common Criteria (CC). The Availability and Processing Integrity criteria additionally use `process` and `transitions`. The Privacy criteria uses `classify` for personal data handling evidence.

---

## Understanding Results

### Status values

| Status | Tier | Meaning |
|--------|------|---------|
| `evidenced` | 1 | At least one DSL construct matching the control's expected evidence was found |
| `partial` | 2 | Reserved for future use — controls that are partially evidenced but incomplete |
| `gap` | 3 | The control has expected DSL evidence categories, but none were found in the project |
| `excluded` | 0 | The control has no DSL evidence mapping — it cannot be assessed from the specification alone |

### What "evidenced" means in practice

An `evidenced` status means the DSL specification contains constructs that *correspond to* the control objective. It does not mean the control is operationally satisfied. For example:

- ISO 27001 A.5.1 (Policies for information security) is evidenced by `classify` and `permit` blocks. This means your specification declares classification and access policies — but whether those policies are appropriate for your risk profile is a human judgment.
- ISO 27001 A.5.2 (Information security roles and responsibilities) is evidenced by `persona` definitions — but whether the personas map to the right organisational structure requires review.

The AuditSpec is evidence that your design intent is documented in machine-readable form. It is a starting point for an auditor conversation, not a substitute for one.

### What "excluded" means

Many framework controls are organisational, physical, or HR-level requirements that cannot be satisfied by an application specification. Examples:

- ISO 27001 A.5.5 (Contact with authorities) — no DSL construct can evidence this
- SOC 2 CC1.2 (Board independence and oversight) — this is a governance-level control

Excluded controls are expected. A well-specified application will typically show 25–40% excluded on ISO 27001 and a similar proportion on SOC 2.

### Coverage calculation

The CLI reports `Coverage` as `(evidenced + partial) / total_controls`. Excluded controls are counted in the denominator. Realistic coverage for a medium-complexity Dazzle application against ISO 27001 is 40–55%. Higher coverage requires more DSL constructs: richer classification directives, more detailed process definitions, and story-level test coverage.

---

## Adding Custom Frameworks

To assess against a framework not bundled with Dazzle, create a YAML file following the schema below and pass it directly to the CLI.

### Framework YAML schema

```yaml
framework:
  id: my_framework          # unique identifier, no spaces
  name: "My Framework v1"
  version: "1.0"
  jurisdiction: "internal"
  body: "My Org"

  themes:
    - id: security
      name: "Security Controls"
      controls:
        - id: "SEC-1"
          name: "Access Control Policy"
          objective: "Ensure all access is governed by a defined policy."
          attributes:
            control_type: [preventive]
          dsl_evidence:
            - construct: permit
              description: "permit blocks encode access control policy"
            - construct: scope
              description: "scope blocks enforce row-level isolation"

        - id: "SEC-2"
          name: "Role Definition"
          objective: "All users must be assigned to a defined role."
          dsl_evidence:
            - construct: persona
              description: "Persona definitions encode system roles"

        - id: "SEC-3"
          name: "Physical Security"
          objective: "Physical access to systems must be controlled."
          # No dsl_evidence → will be marked excluded
          dsl_evidence: []
```

### Valid construct values for `dsl_evidence`

The `construct` field must match one of the taxonomy categories the evidence extractor produces. Use one of:

```
classify   permit    scope       visible    transitions
process    persona   story       personas   stories
```

Note that `personas` and `stories` are the plural aliases used in some taxonomy files; both map to the `persona` and `story` evidence buckets respectively.

### Running with a custom taxonomy

```bash
dazzle compliance compile --framework my_framework \
  --taxonomy-path /path/to/my_framework.yaml
```

The `--taxonomy-path` flag overrides the bundled framework lookup. The `--framework` flag is still used as the identifier in the output path and AuditSpec `framework_id` field.

> The `--taxonomy-path` option is available on the `compile` command. The `gaps` command uses the same flag. The `evidence` command does not require a taxonomy — it only reads your DSL.

---

## Workflow

A typical compliance assessment workflow:

```bash
# 1. Check what evidence exists in your project
dazzle compliance evidence

# 2. Run the full compile against ISO 27001
dazzle compliance compile --framework iso27001

# 3. Review gaps — what DSL constructs are missing?
dazzle compliance gaps

# 4. Add missing constructs to your DSL (e.g. missing persona definitions,
#    unclassified entities, missing process documentation)

# 5. Recompile — coverage should improve
dazzle compliance compile

# 6. Run against SOC 2 as well
dazzle compliance compile --framework soc2
dazzle compliance gaps --framework soc2
```

The AuditSpec at `.dazzle/compliance/output/iso27001/auditspec.json` is a stable, reproducible artifact — given the same DSL files, the same AuditSpec is produced. Commit the AuditSpec alongside your DSL to provide a dated record of your compliance posture at each release.
