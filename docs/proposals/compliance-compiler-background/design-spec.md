# Compliance Compiler: DSL-Driven Audit Documentation Generation

**Date**: 2026-03-23
**Status**: Design approved, pending implementation planning
**Scope**: Full ISO 27001:2022 certification pack for a consumer app, generalised for Dazzle

## 1. Vision

Organisations using Dazzle DSL already declare their data model, access controls, processes, data classifications, workflows, and role structures. This metadata — when mapped against a compliance framework — constitutes the bulk of the evidence required for certification.

The Compliance Compiler extracts this evidence, identifies gaps, and drives an AI agent to produce formal audit documentation. The goal is to replace the manual document-building and domain investigation work typically performed by a human consultant or expensive GRC software subscription.

**First target**: ISO/IEC 27001:2022 (most relevant to UK schools purchasing SaaS).
**Future targets**: NIST CSF 2.0, SOC 2, Cyber Essentials Plus — each requiring only a new taxonomy file and document spec.

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Input Layer                           │
├──────────────────────┬──────────────────────────────────┤
│  Framework Taxonomy  │  Dazzle DSL                      │
│  (YAML per standard) │  (app.dsl + processes + stories) │
│  iso27001.yaml       │  112 classify, 53 permit/scope,  │
│  nistcsf2.yaml       │  88 transitions, 49 processes,   │
│  (future: soc2...)   │  20+ visible, 2 grant_schema     │
└──────────┬───────────┴──────────┬───────────────────────┘
           │                      │
           ▼                      ▼
┌─────────────────────────────────────────────────────────┐
│              AuditSpec Compiler (Dazzle MCP)            │
│  Walks DSL AST, applies taxonomy mappings,              │
│  produces per-control evidence/gap assessment           │
│  Output: auditspec.json (the IR)                        │
└──────────────────────┬──────────────────────────────────┘
                       │
           ┌───────────┼───────────────┐
           ▼           ▼               ▼
┌──────────────┐ ┌───────────┐ ┌─────────────────┐
│ DocumentSpec │ │ GraphSpec │ │ BrandSpec        │
│ (YAML)       │ │ (YAML)    │ │ (YAML)           │
│ audit-pack   │ │ deps,     │ │ logo, colours,   │
│ customer-stmt│ │ evidence, │ │ print layout,    │
│ gap-analysis │ │ app links │ │ doc control      │
└──────┬───────┘ └─────┬─────┘ └────────┬────────┘
       │               │                │
       ▼               ▼                ▼
┌─────────────────────────────────────────────────────────┐
│           AI Agent Coordinator (/audit skill)           │
│  Per-document agents, graph-aware context slicing,      │
│  cross-reference consistency pass                       │
│  Output: markdown per document                          │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Brand-Aware Renderer                       │
│  markdown → PDF (reportlab/weasyprint)                  │
│  Title pages, doc control, TOC, classification banners  │
│  Output: branded PDF pack                               │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Customer        Audit Pack     Gap Analysis
   Statement       (15-20 docs)   (action list)
```

### Pipeline split

- **Deterministic** (Dazzle MCP): taxonomy loading, DSL walking, evidence matching, AuditSpec generation
- **Creative** (AI agent): prose authoring, narrative construction, gap recommendations, cross-reference consistency
- **Mechanical** (renderer): markdown → branded PDF with doc control metadata

## 3. Framework Taxonomy

Each compliance standard is encoded as a YAML file in `.dazzle/compliance/frameworks/`. The taxonomy is complete — every control in the standard is represented, even those with no DSL evidence. This makes the taxonomy itself auditable: an auditor can inspect it and confirm full coverage of the standard.

### Format

```yaml
# .dazzle/compliance/frameworks/iso27001.yaml
framework:
  id: iso27001
  name: "ISO/IEC 27001:2022"
  jurisdiction: international
  body: "International Organization for Standardization"
  version: "2022"

  themes:
    - id: organisational
      name: "Organisational Controls"
      controls:
        - id: "A.5.1"
          name: "Policies for information security"
          objective: "To provide management direction and support for information security"
          attributes:
            control_type: [preventive]
            security_concepts: [identify]
            operational_capabilities: [governance]
          dsl_evidence:
            - construct: policies
              description: "Existence of policies: block with classify directives"
            - construct: permit
              description: "Role-based access rules on all entities"
            - construct: scope
              description: "Row-level filtering rules"

        - id: "A.5.2"
          name: "Information security roles and responsibilities"
          objective: "To establish a defined, approved and understood structure..."
          dsl_evidence:
            - construct: persona
              description: "Named personas with roles, goals, proficiency"
            - construct: workspace
              description: "Role-specific workspaces with access rules"
            - construct: grant_schema
              description: "Delegation structures with approval chains"

    - id: physical
      name: "Physical Controls"
      controls:
        - id: "A.7.4"
          name: "Physical security monitoring"
          objective: "..."
          dsl_evidence: []  # No DSL representation — flagged as gap
```

### Key properties

- **`dsl_evidence`** declares which DSL constructs provide evidence for each control. This is the mapping layer the compiler uses.
- Controls with `dsl_evidence: []` are automatically flagged as gaps requiring manual documentation.
- **`attributes`** capture ISO 27001:2022 control attributes (control type, security concepts, operational capabilities) for cross-referencing and filtering.
- The taxonomy file is the single source of truth for framework structure. Adding a new framework = adding a new YAML file.

### DSL construct vocabulary

The following DSL constructs are recognised as evidence sources:

| Construct | What it evidences |
|-----------|-------------------|
| `classify` | Data classification, asset identification, handling procedures |
| `permit` | Role-based access control, authorisation |
| `scope` | Row-level filtering, least-privilege, need-to-know |
| `visible` | Data minimisation, field-level access restriction |
| `transitions` | Workflow control, approval gates, separation of duties |
| `processes` | Operational procedures, SLAs, escalation paths |
| `grant_schema` | Privilege delegation, time-bounded access, approval chains |
| `persona` | Role definitions, responsibilities, proficiency |
| `workspace` | Role-specific interfaces, access boundaries |
| `llm_config` | AI governance, logging, PII redaction |
| `archetype` | Audit trail fields (created_by, updated_by, timestamps) |
| `scenarios` | End-to-end control flow validation |
| `stories` | Acceptance criteria, user journey documentation |

## 4. AuditSpec IR (Compiler Output)

The compiler walks the DSL AST, applies the taxonomy mappings, and produces a per-framework JSON document — the Intermediate Representation.

### Format

```json
{
  "auditspec_version": "1.0",
  "framework": "iso27001",
  "framework_version": "2022",
  "generated_at": "2026-03-23T14:30:00Z",
  "dsl_source": "dsl/app.dsl",
  "dsl_hash": "sha256:abc123...",

  "summary": {
    "total_controls": 93,
    "evidenced": 61,
    "partial": 18,
    "gaps": 14
  },

  "controls": [
    {
      "id": "A.5.1",
      "name": "Policies for information security",
      "theme": "organisational",
      "status": "evidenced",
      "evidence": [
        {
          "construct": "policies",
          "type": "classify",
          "count": 112,
          "summary": "112 classify directives across 7 categories",
          "refs": [
            {"entity": "User", "field": "email", "classification": "PII_DIRECT"},
            {"entity": "StudentProfile", "field": "date_of_birth", "classification": "PII_DIRECT"}
          ]
        },
        {
          "construct": "permit",
          "type": "access_control",
          "count": 53,
          "summary": "53 entities with role-based permit blocks",
          "refs": [
            {"entity": "MarkingResult", "roles": ["teacher", "head_of_department", "school_admin"]}
          ]
        }
      ],
      "gaps": [],
      "recommendations": []
    },
    {
      "id": "A.7.4",
      "name": "Physical security monitoring",
      "theme": "physical",
      "status": "gap",
      "evidence": [],
      "gaps": [
        {
          "description": "No DSL construct addresses physical security",
          "tier": 3,
          "action": "Document physical security controls for hosting infrastructure (Heroku/AWS)"
        }
      ],
      "recommendations": [
        "Reference Heroku SOC2 report and AWS ISO 27001 certification as inherited controls",
        "Document office/remote working physical security policy"
      ]
    }
  ]
}
```

### Status computation

- **`evidenced`**: all `dsl_evidence` entries in the taxonomy have matching DSL constructs with data
- **`partial`**: some evidence present, some gaps identified
- **`gap`**: no DSL evidence found (or `dsl_evidence: []` in taxonomy)

### Partial control example

A control with `status: partial` has both `evidence` and `gaps` populated:

```json
{
  "id": "A.8.3",
  "name": "Information access restriction",
  "theme": "technological",
  "status": "partial",
  "evidence": [
    {
      "construct": "scope",
      "type": "row_filtering",
      "count": 53,
      "summary": "All entities have scope blocks with row-level filtering"
    }
  ],
  "gaps": [
    {
      "description": "No network-level access restriction declared (IP allowlisting, VPN)",
      "tier": 2,
      "action": "Document network access controls"
    }
  ]
}
```

### Process and story evidence

Processes and stories are included as evidence types alongside DSL constructs:

```json
{
  "construct": "processes",
  "type": "process_definition",
  "count": 3,
  "summary": "3 processes with approval gates and SLA timeouts",
  "refs": [
    {
      "process": "marking_lifecycle",
      "file": ".dazzle/processes/assessment-core.json",
      "timeout_seconds": 2592000,
      "steps": 8,
      "has_approval_gate": true
    }
  ]
},
{
  "construct": "stories",
  "type": "acceptance_criteria",
  "count": 5,
  "summary": "5 stories with acceptance criteria covering this control",
  "refs": [
    {
      "story_id": "ST-020",
      "title": "Assessment Event created in draft",
      "criteria_count": 4
    }
  ]
}
```

### Operation-level permit detail

Permit evidence includes per-operation breakdown, not just role names:

```json
{
  "construct": "permit",
  "type": "access_control",
  "count": 53,
  "summary": "53 entities with role-based permit blocks",
  "refs": [
    {
      "entity": "MarkingResult",
      "operations": {
        "read": ["teacher", "head_of_department", "school_admin", "senior_leader"],
        "list": ["teacher", "head_of_department", "school_admin", "senior_leader"],
        "write": ["teacher", "head_of_department", "school_admin"],
        "delete": ["school_admin"]
      }
    }
  ]
}
```

### Gap tiers

- **Tier 1**: fully auto-generatable from DSL (evidence exists, just needs prose)
- **Tier 2**: templated with DSL evidence (partial evidence, human completes narrative via review workflow — see Section 6a)
- **Tier 3**: requires manual policy documentation (no DSL representation — see Section 6a)

### Reproducibility

`dsl_hash` ensures the AuditSpec is tied to a specific DSL version. If the DSL changes, regenerate. The compliance graph (Section 7) tracks which documents are stale.

## 5. Document Specification

The DocumentSpec layer declares what documents to produce from the AuditSpec. It separates "what evidence do we have" from "how should we present it."

### Audit pack (formal)

```yaml
# .dazzle/compliance/documents/iso27001-audit-pack.yaml
document_pack:
  id: iso27001_audit_pack
  name: "ISO 27001:2022 Certification Pack"
  framework: iso27001
  formality: formal

  documents:
    - id: isms_scope
      name: "ISMS Scope Statement"
      target_pages: 8
      sections:
        - title: "Organisation Overview"
          source: dsl_metadata
          tone: formal
        - title: "Scope of the ISMS"
          source: dsl_metadata
          include: [entities, domains, personas, workspaces]
        - title: "Interested Parties"
          source: personas
        - title: "Exclusions and Justifications"
          source: gaps
          filter: {tier: 3}

    - id: risk_assessment
      name: "Information Security Risk Assessment"
      sections:
        - title: "Risk Assessment Methodology"
          source: template
        - title: "Asset Register"
          source: auditspec
          controls: ["A.5.9", "A.5.10"]
          extract: classify
        - title: "Risk Register"
          source: auditspec
          controls: ["A.5.1", "A.5.2", "A.5.3"]
          extract: [classify, permit, scope, transitions]
          ai_instruction: >
            For each classified data category, assess risk based on
            access controls, state transitions, and data sensitivity tier.
            Use likelihood/impact matrix.

    - id: soa
      name: "Statement of Applicability"
      depends_on: [risk_assessment, access_control_policy, data_classification_policy]
      target_pages: 25
      layout: table
      sections:
        - title: "Statement of Applicability"
          source: auditspec
          controls: all
          columns:
            - control_id
            - control_name
            - applicable
            - justification
            - implementation_status
            - evidence_summary
            - responsible_role

    - id: access_control_policy
      name: "Access Control Policy"
      sections:
        - title: "Access Control Principles"
          source: template
          ai_instruction: "Write based on least-privilege, need-to-know principles evidenced by scope blocks"
        - title: "Role Definitions"
          source: personas
          controls: ["A.5.2", "A.5.15", "A.5.18"]
        - title: "Access Control Matrix"
          source: auditspec
          controls: ["A.5.15", "A.5.16", "A.5.17", "A.5.18"]
          extract: [permit, scope, visible, grant_schema]
          layout: matrix
        - title: "Privilege Management"
          source: auditspec
          controls: ["A.8.2"]
          extract: grant_schema

    - id: data_classification_policy
      name: "Data Classification and Handling Policy"
      sections:
        - title: "Classification Scheme"
          source: auditspec
          controls: ["A.5.12", "A.5.13"]
          extract: classify
          ai_instruction: "Map DSL categories to ISO classification tiers"
        - title: "Handling Procedures by Classification"
          source: auditspec
          extract: [classify, visible, scope]

    - id: gap_analysis
      name: "Gap Analysis and Remediation Plan"
      sections:
        - title: "Executive Summary"
          source: auditspec
          extract: summary
        - title: "Controls Requiring Action"
          source: auditspec
          filter: {status: [partial, gap]}
          layout: table
          columns: [control_id, control_name, status, gaps, recommended_actions, priority, owner]
        - title: "Remediation Timeline"
          source: gaps
          ai_instruction: "Prioritise by risk, group by theme, suggest realistic timeline"
```

### Customer statement (informal)

```yaml
# .dazzle/compliance/documents/iso27001-customer-statement.yaml
document_pack:
  id: iso27001_customer_statement
  name: "Information Security Compliance Statement"
  framework: iso27001
  formality: informal

  documents:
    - id: compliance_statement
      name: "a consumer app Information Security Statement"
      sections:
        - title: "Our Commitment to Information Security"
          source: template
          tone: customer_facing
        - title: "Data Protection Summary"
          source: auditspec
          extract: classify
          ai_instruction: "Summarise what data we hold, how it's classified, who can access it. Non-technical."
        - title: "Access Control Summary"
          source: auditspec
          extract: [permit, scope, visible]
          ai_instruction: "Explain role-based access in terms a school DPO would understand"
        - title: "Compliance Posture"
          source: auditspec
          extract: summary
          ai_instruction: "Present coverage stats positively but honestly. Highlight strengths."
        - title: "Certification Roadmap"
          source: gaps
          filter: {tier: [1, 2]}
          ai_instruction: "Brief timeline toward ISO 27001 certification"
```

### Key properties

- **`source`** — where the agent pulls data (see Source Types below)
- **`extract`** — which DSL construct types to focus on (must be from the construct vocabulary in Section 3, or `summary` for the AuditSpec summary block)
- **`controls`** — links sections to specific Annex A controls (or `all` for every control)
- **`ai_instruction`** — section-specific guidance for the frontier model
- **`formality`** and **`tone`** — guide the AI's register
- **`target_pages`** — expected page count for the section (guides AI output length)
- **Same AuditSpec, different document specs** — the compiler output is reused across packs

### Source types

| Source | Resolves to | Example use |
|--------|------------|-------------|
| `auditspec` | AuditSpec controls filtered by `controls` and `extract` fields | Risk register, SoA |
| `personas` | Full persona blocks from DSL (name, role, goals, proficiency, workspace) | ISMS scope, role definitions |
| `gaps` | AuditSpec controls filtered to `status: partial\|gap`, further filtered by `filter` | Gap analysis, remediation plan |
| `dsl_metadata` | App-level DSL metadata (name, description, entity count, domain summary) | Organisation overview |
| `template` | Markdown file from `.dazzle/compliance/templates/{section_slug}.md` — human-authored boilerplate that the AI agent uses as a starting point and enriches with DSL context | Risk methodology, security commitment |

### Template content strategy

Sections with `source: template` reference human-authored markdown files in `.dazzle/compliance/templates/`. These provide:
- Boilerplate that cannot be invented (e.g., risk assessment methodology choices)
- Organisational commitments and policy statements
- Framework-specific required language

The AI agent receives the template as a starting draft and enriches it with DSL evidence. Templates are versioned in git alongside the DSL. For v1, templates are authored manually; future iterations could auto-generate initial drafts from framework guidance.

## 6. AI Agent Architecture

### Per-document agents

Each document in the pack gets its own agent invocation with a focused context window:

```
Per-document agent receives:
├── System prompt: compliance specialist persona + ISO 27001 domain knowledge
├── DocumentSpec: the specific document being generated
├── AuditSpec (filtered): only controls relevant to this document
├── DSL source (filtered): only entities/policies/processes referenced by evidence
├── Brand identity: rendering instructions (tone, formality, org name)
└── Stories/processes: relevant user stories and process definitions for narrative
```

**Why per-document?** Context window management. The full AuditSpec + full DSL + all 93 controls would consume most of the window. Scoping each agent to one document keeps context focused and output quality high.

### Coordinator pipeline

```
DocumentSpec YAML
       │
       ▼
  Coordinator (Claude Code skill: /audit)
       │
       ├──► Agent: ISMS Scope ──► isms_scope.md
       ├──► Agent: Risk Assessment ──► risk_assessment.md
       ├──► Agent: Statement of Applicability ──► soa.md
       ├──► Agent: Access Control Policy ──► access_control_policy.md
       ├──► Agent: Data Classification ──► data_classification.md
       └──► Agent: Gap Analysis ──► gap_analysis.md
       │
       ▼
  Cross-reference consistency pass
       │
       ▼
  Brand-aware renderer (markdown → PDF)
```

### Coordinator responsibilities

1. Load DocumentSpec and AuditSpec
2. Use the compliance graph (Section 7) for build ordering — generate leaf documents first, root documents last
3. For each document, slice the AuditSpec to only relevant controls
4. Slice DSL source to only referenced entities/policies/processes
5. Dispatch parallel agents (respecting dependency ordering from graph)
6. Collect outputs, run cross-reference consistency pass
7. Trigger renderer

### Cross-reference pass

A final agent reads all generated documents together and checks:
- Consistent terminology (same role names, entity counts, statistics)
- No contradictions between documents
- Section cross-references resolve correctly
- Evidence citations match actual DSL constructs

### Evidence citation style

Agents cite DSL constructs by reference, not raw syntax:
> "Role-based access control restricts marking results to teachers, heads of department, and school administrators (DSL ref: MarkingResult.permit)"

Not:
> `permit: read: role(teacher) or role(head_of_department) or role(school_admin)`

### Deterministic citation validation

After each agent completes, a deterministic (non-AI) pass validates all `DSL ref:` citations in the output against the AuditSpec IR. Any citation that does not resolve to an actual evidence entry is flagged as a hallucination and removed or corrected before the cross-reference pass.

### Cross-reference failure strategy

If the cross-reference pass finds contradictions:
1. Identify the specific inconsistency (e.g., "access control policy says 7 roles, ISMS scope says 9 personas")
2. Determine the authoritative source (the AuditSpec IR is always ground truth)
3. Regenerate only the section(s) containing the error, with an additional `ai_instruction` noting the required correction
4. Maximum 2 regeneration attempts per document. If contradictions persist, flag for human review.

## 6a. Human-in-the-Loop Workflow

Tier 2 and tier 3 gaps require human input. The pipeline supports this via a review/contribution workflow:

### Workflow

1. **Initial generation**: the AI agent generates all sections it can, marking tier 2/3 sections with `<!-- HUMAN_INPUT_REQUIRED -->` markers
2. **Review artefact**: the coordinator produces a `review.yaml` file listing all sections requiring human input:

```yaml
# .dazzle/compliance/output/iso27001/review.yaml
pending_reviews:
  - document: risk_assessment
    section: "Risk Assessment Methodology"
    tier: 2
    status: draft  # AI has written a draft from template
    instruction: "Review and confirm risk methodology choices (qualitative vs quantitative, likelihood/impact scales)"
  - document: physical_security
    section: "Office Security Controls"
    tier: 3
    status: stub  # AI has written a stub with guidance
    instruction: "Document physical security measures for remote-first team"
```

3. **Human contribution**: the human edits the generated markdown files directly, removing `<!-- HUMAN_INPUT_REQUIRED -->` markers as they go
4. **Re-run**: the coordinator detects which sections have been human-reviewed (markers removed) and regenerates only dependent sections with the human content as additional context
5. **Completion**: when `review.yaml` shows all items resolved, the pack is ready for rendering

### Tier behaviour

- **Tier 1** (full evidence): AI generates autonomously, no human review needed
- **Tier 2** (partial evidence): AI generates a draft pre-filled with DSL evidence; human reviews and completes
- **Tier 3** (no DSL evidence): AI generates a stub with guidance on what to write; human authors the content

## 7. Compliance Graph

The compliance documentation forms a graph that mirrors and links into the application itself.

### Graph structure

```yaml
# .dazzle/compliance/graph.yaml
graph:
  nodes:
    - id: soa
      type: document
      depends_on: [risk_assessment, access_control_policy, data_classification_policy]
    - id: risk_assessment
      type: document
      depends_on: [asset_register]
    - id: access_control_policy
      type: document
      implements: ["A.5.15", "A.5.16", "A.5.17", "A.5.18"]

  edges:
    # Document → DSL construct links
    - from: access_control_policy/section/role_definitions
      to: dsl://personas/*
      relation: evidences
    - from: access_control_policy/section/access_matrix
      to: dsl://entities/*/permit
      relation: evidences
    - from: data_classification_policy/section/classification_scheme
      to: dsl://policies/classify/*
      relation: evidences

    # DSL construct → App surface links
    - from: dsl://entities/MarkingResult/permit
      to: app:///app/markingresult
      relation: renders_at
```

### Edge types

- **`depends_on`** — document references content from another (build ordering)
- **`evidences`** — section provides evidence for controls
- **`implements`** — DSL construct implements a control
- **`renders_at`** — control is visible at an app surface/URL

### Benefits

1. **Build ordering** — topological sort determines generation sequence
2. **Version coherence** — DSL changes invalidate only affected documents, not the entire pack
3. **Browsable compliance surface** — the documentation becomes a navigable workspace within the Dazzle app, with hyperlinks from compliance claims to live application surfaces
4. **Auditor navigation** — click from "Access Control Policy §3.2" → live access control matrix → actual UI the teacher sees

### Future: compliance workspace

```yaml
workspace compliance_hub:
  access: role(senior_leader) or role(school_admin) or role(trust_admin) or role(governor)
  regions:
    - compliance_overview    # Live dashboard: 93 controls, coverage, staleness
    - document_browser       # Navigable document tree with cross-references
    - gap_tracker            # Action items, assignable, trackable
    - audit_trail            # Generation history, DSL version linkage
```

## 8. Brand Identity Pack

Extends `themespec.yaml` into a unified source of truth for all visual output — web, print, and compliance documents.

### Format

```yaml
# brandspec.yaml
brand:
  identity:
    name: "a consumer app"
    legal_name: "a consumer app Ltd"
    company_number: "17099994"
    tagline: "AI-Powered Assessment Marking"

  assets:
    logo_primary: static/images/acme-logo.webp
    logo_mono: static/images/acme-logo-mono.webp
    favicon: static/images/favicon.ico

  colours:
    primary: "#1a365d"
    secondary: "#2b6cb0"
    accent: "#38a169"
    text: "#1a202c"
    muted: "#718096"

  typography:
    headings: {family: "Inter", weight: 600}
    body: {family: "Inter", weight: 400, size: "11pt"}
    mono: {family: "JetBrains Mono"}

  print:
    page_size: A4
    margins: {top: 25mm, bottom: 25mm, left: 30mm, right: 25mm}
    header:
      left: "{logo_mono}"
      right: "{document_title}"
      separator: true
    footer:
      left: "{legal_name} — Confidential"
      centre: "{document_id} v{version}"
      right: "Page {page} of {pages}"
    styles:
      title_page:
        logo_position: centre
        title_size: 24pt
        subtitle_size: 14pt
        includes: [document_id, version, date, classification]
      heading_1: {size: 16pt, colour: primary, spacing_before: 18pt}
      heading_2: {size: 13pt, colour: secondary, spacing_before: 12pt}
      heading_3: {size: 11pt, colour: text, weight: 600}
      table:
        header_bg: primary
        header_text: "#ffffff"
        stripe: "#f7fafc"
        border: muted
      classification_banner:
        text: "CONFIDENTIAL"
        colour: accent
        position: top_centre

  compliance:
    document_control:
      author: "Generated by a consumer app Compliance Pipeline"
      reviewer: ""
      approver: ""
      classification: "Confidential"
    revision_history: true    # auto-generated from git history
    distribution_list: true   # pulled from persona definitions
```

### Rendering pipeline

```
Generated markdown → Markdown parser → Brand-aware renderer → PDF
                                            │
                                            ├── Title page (logo, doc ID, version, classification)
                                            ├── Document control table (author, reviewer, revision history)
                                            ├── Table of contents (auto-generated)
                                            ├── Body (styled headings, tables, cross-references)
                                            └── Back matter (distribution list, glossary)
```

Uses weasyprint (CSS-driven HTML→PDF, reuses web theme patterns). Cross-references between documents become PDF hyperlinks.

### Dazzle generalisation

`brandspec.yaml` becomes a first-class Dazzle concept. Any Dazzle app defines its brand once; compliance documents, marketing site, pitch deck, and print materials all inherit from it.

## 9. Existing DSL Evidence (consumer Baseline)

A consumer app already declares substantial compliance-relevant metadata:

| DSL Construct | Count | ISO 27001 Relevance |
|---------------|-------|---------------------|
| `classify` directives | 112 | Asset register, data classification, handling procedures |
| `permit` blocks | 53 entities | Access control policy, authorisation matrix |
| `scope` blocks | 53 entities | Row-level filtering, least-privilege, need-to-know |
| `visible` directives | 20+ | Data minimisation, field-level access restriction |
| Transition guards | 88 | Workflow control, approval gates, separation of duties |
| Named processes | 49 | Operational procedures, SLAs, escalation paths |
| `grant_schema` | 2 | Privilege delegation, time-bounded access |
| Personas | 9 | Role definitions, responsibilities |
| Workspaces | 11 | Role-specific interfaces, access boundaries |
| LLM intents | 5 | AI governance, logging, PII redaction |
| Archetypes (audit) | 3 | Audit trail fields on 40+ entities |
| Scenarios | 27 | End-to-end control flow validation |
| Stories | 62 | Acceptance criteria, user journey documentation |

### Known gaps (no DSL representation)

- Data retention / lifecycle policies
- Incident response procedures and escalation SLAs
- Third-party processor tracking (AWS, Heroku, AI providers)
- Encryption and key management declarations
- Physical security controls
- Business continuity / disaster recovery (RTO/RPO)
- Employee screening and training

These will be flagged as tier 2 or tier 3 gaps in the AuditSpec, with recommendations for the AI agent to generate template documentation referencing inherited controls from cloud providers.

## 10. Output Directory Structure

```
.dazzle/compliance/
├── frameworks/
│   └── iso27001.yaml              # Framework taxonomy (all 93 controls)
├── documents/
│   ├── iso27001-audit-pack.yaml   # Formal audit document spec
│   └── iso27001-customer-statement.yaml
├── templates/
│   ├── risk_assessment_methodology.md
│   ├── security_commitment.md
│   └── access_control_principles.md
├── graph.yaml                     # Compliance graph (v2 — depends_on in DocumentSpec for v1)
└── output/
    └── iso27001/
        ├── auditspec.json         # Compiler IR output
        ├── review.yaml            # Human-in-the-loop tracker
        ├── markdown/
        │   ├── isms_scope.md
        │   ├── risk_assessment.md
        │   ├── soa.md
        │   ├── access_control_policy.md
        │   ├── data_classification_policy.md
        │   └── gap_analysis.md
        └── pdf/
            ├── Acme-ISMS-Scope-v1.0.pdf
            ├── Acme-Risk-Assessment-v1.0.pdf
            └── ...
```

Markdown files are version-controlled in git. PDF files are generated artefacts (gitignored). The `auditspec.json` is committed so that changes to compliance posture are visible in git diffs.

## 11. Implementation Approach

### Proof of concept

1. Author the ISO 27001:2022 framework taxonomy YAML (all 93 Annex A controls)
2. Build the AuditSpec compiler as a Python module in `pipeline/compliance/`
3. Author the document specs for audit pack and customer statement
4. Author initial human templates (risk methodology, security commitment, access control principles)
5. Build the `/audit` Claude Code skill as the coordinator
6. Build the brand-aware markdown → PDF renderer (weasyprint — CSS-driven, reuses web theme patterns)
7. Generate the full ISO 27001 pack for a consumer app
8. Complete human review for tier 2/3 gaps

### v1 simplifications

- **Graph**: use `depends_on` fields in DocumentSpec rather than a separate graph file. Build the full graph with `dsl://` and `app://` URIs when the compliance workspace becomes real.
- **Brand**: use a local `brandspec.yaml` in a consumer app. Propose Dazzle generalisation as a separate initiative.
- **Renderer**: commit to weasyprint (CSS-driven HTML→PDF). Produces higher-quality output than reportlab for document-style layouts, and CSS skills transfer from the web theme.

### Dazzle generalisation (future)

1. Propose `compliance_framework` as new DSL grammar to Dazzle
2. Propose `brandspec` as first-class Dazzle concept
3. Move compiler into Dazzle as `mcp__dazzle__compliance` MCP tool
4. Add compliance workspace as a standard Dazzle workspace type
5. Add NIST CSF 2.0, SOC 2, Cyber Essentials Plus taxonomy files

## 12. Success Criteria

1. **Customer statement**: a polished, branded PDF that a school DPO would find credible and reassuring
2. **Audit pack**: a complete ISO 27001 document set that a certification body would accept as a starting point for Stage 1 audit
3. **Gap analysis**: an actionable remediation plan with prioritised tasks, owners, and timelines
4. **Reproducibility**: regenerating the pack from a changed DSL produces an updated pack with only affected documents regenerated
5. **Framework portability**: adding NIST CSF 2.0 requires only a new taxonomy file and document spec, not code changes
