# Developer Outreach Strategy

This page records the communication strategy behind the onboarding docs. It is
for maintainers writing README copy, MkDocs pages, examples, talks, issue
responses, or release notes.

Dazzle asks developers to trust an unfamiliar stack: a DSL is parsed into an
AppSpec IR, the runtime executes that IR directly, server-rendered fragments
produce the UI, PostgreSQL backs the data layer, and `permit:` / `scope:` rules
become both static and runtime authorization checks. That is a bigger ask than
"learn a new web framework." The docs need to treat trust as the first product
experience.

## The Primary Audience

The first serious evaluator is usually not a beginner. Assume a developer who
has built SaaS with React plus a backend framework, or with Django/Rails, and
who is comfortable with PostgreSQL, migrations, auth, and CI.

They are not blocked by syntax. They are blocked by these questions:

1. What exactly is the DSL replacing?
2. What is the intermediate representation, and can I inspect it?
3. What does the runtime do from that representation?
4. Where does authorization actually run?
5. What security and compliance claims are real, partial, or aspirational?
6. What happens when the generated/default behavior is not enough?
7. How do I debug this when it fails?

If a page answers only "how do I write the syntax?", it is reference material,
not onboarding.

## Communication Principles

### Show the Trust Boundary

Every onboarding path should expose at least one derived artifact:

```bash
dazzle validate
dazzle inspect project --entity Task
dazzle specs openapi -f json
dazzle rbac matrix --format table
```

The reader should see a causal chain: edit DSL -> validate -> inspect AppSpec
projection -> inspect API/RBAC output -> run the app.

### Use Evidence Before Claims

Avoid unsupported statements like "provable", "secure", or "compliant" unless
the page immediately names the mechanism and the limit. Prefer:

- "The RBAC matrix is statically derived from `permit:` and `scope:`."
- "`dazzle rbac verify` probes the running app and fails on divergence."
- "`dazzle compliance compile` maps DSL constructs to control evidence; it is
  not a certification."

The strongest pages should pair claims with commands and expected output.

### Admit the Maturity Model

Dazzle is still pre-1.0 and the process is novel. Hiding that increases risk
for serious evaluators. Public docs should distinguish:

| Label | Meaning |
|-------|---------|
| Stable | Public behavior is settled and heavily tested |
| Beta | Works end-to-end, but API or edge cases may still move |
| Alpha | Functional, incomplete, or thinly tested |
| Roadmap | Not implemented |

The security claims inventory is the canonical place for this rubric.

### Explain the Stack as a System

Do not list FastAPI, Pydantic, SQLAlchemy, Alembic, psycopg, HTMX, Alpine.js,
and fragments as trivia. Explain why each exists in the pipeline:

| Layer | What the reader needs to know |
|-------|-------------------------------|
| DSL parser | Converts author intent into a typed AppSpec |
| AppSpec IR | The single source read by runtime, specs, tests, MCP, and compliance |
| FastAPI | Exposes generated API and framework routes |
| Pydantic | Holds typed boundary and IR models |
| SQLAlchemy/Alembic | Manages schema/migration projection where used |
| psycopg/PostgreSQL | Executes scope-aware queries and persistence |
| Typed Fragments | Server-rendered UI primitives tied to semantic surfaces |
| HTMX/Alpine.js | Local interaction behavior without SPA state drift |
| RBAC verifier | Checks observed runtime behavior against declared policy |

The docs should make it clear that these are not independent moving parts. They
are projections of one model.

## Recommended Onboarding Path

1. **README:** state the thesis, the trust problem, and the fastest demo. Link
   immediately to skeptical evaluation before deep philosophy.
2. **MkDocs Start Here:** explain DSL -> IR -> runtime with an inspectable
   diagram and route skeptical readers to the evaluation guide.
3. **First App:** teach syntax, but add the inspect loop before serving.
4. **Evaluation Guide:** let a skeptical developer verify runtime, RBAC, and
   compliance claims in about 30 minutes.
5. **Security Claims:** maintain the maturity inventory and known gaps.
6. **Reference Docs:** answer exact syntax and mechanics after trust has been
   established.
7. **Architecture/Philosophy:** explain why Dazzle rejects common patterns,
   including SPA defaults, SQLite defaults, hidden singletons, and generated
   source trees.

## Outreach Content Map

### For a React + Backend Developer

Lead with what moves out of application code:

- entity definitions instead of ORM model drift
- surfaces/workspaces instead of route/component scattering
- `permit:` / `scope:` instead of policy code hidden in handlers
- server-rendered fragments instead of a client-side app state graph
- generated OpenAPI and RBAC matrix instead of manual documentation

Avoid implying that Dazzle is a React replacement. The better framing is:
"Dazzle removes a large class of SaaS plumbing when the app shape fits the DSL."

### For a Django/Rails Developer

Lead with what is familiar and what is stricter:

- entities, CRUD, migrations, auth, and admin-like surfaces are familiar
- the DSL is the maintained artifact, not scaffolding
- PostgreSQL is required, not a production-only target
- authorization is enumerable and verifiable, not policy methods in code
- custom code exists, but should sit behind typed service/fragment boundaries

Avoid "Rails killer" language. Dazzle is demanding because it buys analysis,
not because it wants to replace every web framework use case.

### For a Security or Compliance Evaluator

Lead with evidence:

- RBAC matrix output
- dynamic RBAC verifier behavior
- audit trail behavior and limits
- compliance control mapping and excluded controls
- maturity table and known gaps

Avoid polished claims without failure modes. Skeptical evaluators trust narrow
claims that include limits.

### For an Agent-Tooling Audience

Lead with agent cognition:

- the DSL compresses domain meaning into an inspectable graph
- MCP exposes stateless project reads
- CLI handles process/write operations
- counter-priors and ADRs steer agents away from recurring corpus pathologies

Avoid making the human developer feel secondary. The right message is:
"Agents author more safely because humans can inspect the same model."

## Documentation Anti-Patterns

- Long philosophy before the first verifiable command.
- Claims about security or compliance without commands, tests, and limits.
- Stale example copy that contradicts the actual DSL.
- Generated reference pages edited by hand instead of updating the source TOML.
- Acronyms introduced before the job they perform.
- Treating "AI-first" as a slogan instead of showing how MCP, IR, and tests
  make agent work inspectable.
- Hiding pre-1.0 churn. Clean breaks are a design choice; say so.

## Maintenance Rules

- When a command changes, update README, first-app, examples, and generated
  knowledge-base source together.
- When a security feature changes, update `security-claims.md` before changing
  marketing copy.
- Keep root `EVALUATION.md` / `SECURITY_CLAIMS.md` and their MkDocs copies in
  `docs/evaluation/` synchronized, with only link-path differences.
- When generated docs drift, patch `src/dazzle/mcp/semantics_kb/*.toml` or the
  tool registry source, then run `dazzle docs generate`.
- When an example app changes shape, update both the example README and the
  MkDocs example page.
- Keep the skeptical evaluation guide runnable in about 30 minutes.

## Current Improvement Backlog

1. Add a short "debugging the pipeline" guide that follows one broken DSL field
   from parse error to validation error to runtime behavior.
2. Add one annotated walkthrough of `AppSpec` inspection output.
3. Add a "custom code boundary" guide for services, fragments, and project
   layout.
4. Add a short comparison page for Django/Rails, React SPA, Supabase RLS, and
   Cedar/OpenFGA.
5. Turn the README thesis into a shorter public landing narrative and move the
   longer substrate argument to architecture/philosophy.
