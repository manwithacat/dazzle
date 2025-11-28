# DNR-Back-GraphQL-Spec-v1

## Project: Dazzle Native Runtimes (DNR)
### Topic: GraphQL Backend Builder (Schema, Resolvers, and BFF Facade)

This document specifies how **DNR-Back** can generate and use a **GraphQL API** from `BackendSpec`, with a focus on:

- LLM-first implementation (an LLM coding agent as the primary implementor).
- A **multi-tenant SaaS** accountancy platform as a core use case.
- Heavy consumption of **external APIs** (HMRC, Xero, banking, etc.).
- An **internal BFF / facade** pattern to hide external complexity and expose a clean graph.

It also follows the three-phase adoption strategy:

1. Phase 1 – REST-first, transport-agnostic `BackendSpec`.
2. Phase 2 – Targeted GraphQL BFF/facade for specific UI & API aggregation use cases.
3. Phase 3 – Full GraphQL builder that can generate schema and resolvers from `BackendSpec`.

---

# 1. Goals and Non-Goals

## 1.1 Goals

1. Keep **BackendSpec transport-agnostic**:
   - GraphQL is a *skin*, not the core model.
2. Provide a **GraphQL builder** that can:
   - Generate a GraphQL schema from `BackendSpec`.
   - Generate resolver scaffolding wired to the Dazzle service layer.
3. Support a **multi-tenant SaaS** environment:
   - Strong tenant isolation.
   - Per-request context with tenant, user, roles.
4. Provide a pattern for an **internal BFF/facade**:
   - GraphQL server that:
     - wraps external REST APIs,
     - normalises them into a clean schema,
     - presents a unified graph to DNR-Web and other clients.
5. Be implementable by an **LLM coding agent** with minimal ambiguity:
   - Clear file structure.
   - Clear conventions.
   - Explicit prompts for the agent.

## 1.2 Non-Goals (v1)

1. Replace all REST usage with GraphQL.
2. Design a universal, one-size-fits-all GraphQL schema.
3. Handle every advanced GraphQL feature (subscriptions, live queries, federation, etc.) in v1.
4. Directly model database access in GraphQL:
   - GraphQL resolvers should call **services**, not ORM queries directly, where possible.

---

# 2. Relationship: BackendSpec ↔ GraphQL

`BackendSpec` remains the source of truth. The GraphQL builder is a *projection* of it.

## 2.1 BackendSpec Recap (Conceptual)

BackendSpec includes:

- `EntitySpec` – domain entities (Client, Invoice, Ledger, Task, etc.).
- `ServiceSpec` – operations (createInvoice, listClients, computeVat, etc.).
- `FieldSpec` / `SchemaSpec` – data shapes for inputs and outputs.
- `AuthSpec` (optional) – permissions, roles, and tenancy constraints.

## 2.2 Mapping to GraphQL Concepts

- `EntitySpec` → GraphQL `type` / `input`.
- `SchemaSpec` → GraphQL `input` / `type` / `scalar`.
- `ServiceSpec`:
  - `kind = "query"` → GraphQL `Query` field.
  - `kind = "mutation"` → GraphQL `Mutation` field.
- Multi-tenant and security constraints:
  - Expressed at the resolver level using context (see Section 4).

GraphQL is always **derived** from BackendSpec and can be regenerated.

---

# 3. Three-Phase Adoption Model

## 3.1 Phase 1 – REST-First, Transport-Agnostic BackendSpec

- Primary path:
  - `BackendSpec` → REST API via Django DRF (or similar).
  - OpenAPI generated and used by front-ends via Zod/TypeScript types.
- GraphQL is *not yet* part of the default path.
- Work for LLM agents:
  - Ensure `BackendSpec` is clean, typed, and expresses all domain entities and services independent of transport.

## 3.2 Phase 2 – Targeted GraphQL BFF / Facade

Introduce a **GraphQL BFF** (Backend-for-Frontend) for specific purposes:

- Act as a **facade** over:
  - HMRC APIs,
  - Xero / accounting APIs,
  - bank feeds,
  - Companies House,
  - internal services (REST or direct service layer calls).

Example use case:

- A “Client Overview” workspace needs a unified view of:
  - client profile (internal DB),
  - last 3 invoices (internal),
  - live VAT obligations (HMRC),
  - bank balances (external bank APIs).

GraphQL BFF exposes:

```graphql
type Query {
  clientOverview(clientId: ID!): ClientOverview!
}
```

DNR-Web calls this in one go. Behind the scenes, resolvers:

- call internal services,
- fan out to external APIs,
- stitch results, and
- return a single JSON payload.

This can be done **before** doing a full BackendSpec → GraphQL conversion.

## 3.3 Phase 3 – Full GraphQL Builder from BackendSpec

Once BackendSpec and the service layer are stable:

- Implement a **GraphQL builder** that:
  - reads BackendSpec,
  - generates a GraphQL schema (types, queries, mutations),
  - generates resolver scaffolding that delegates to services,
  - supports multi-tenancy and auth via shared context.

Then, GraphQL becomes:

- a first-class alternative to REST,
- a public or internal API for front-ends and integrators.

---

# 4. Multi-Tenant SaaS and Context

A central requirement is **multi-tenant isolation**.

## 4.1 Request Context

Every GraphQL request has a context object, for example:

```ts
type GraphQLContext = {
  tenantId: string;
  userId: string;
  roles: string[];
  requestId: string;
  ipAddress?: string;
  session?: Record<string, any>;
};
```

Resolvers **must not** accept tenantId as arguments from clients. Instead:

- tenantId is always taken from context (derived from auth token).
- service calls are always scoped using `tenantId`.

## 4.2 Resolver Contract for Tenancy

For LLM agents implementing resolvers:

- Every resolver that touches tenant data should follow a pattern:

```ts
async function resolveClient(
  parent: any,
  args: { id: string },
  ctx: GraphQLContext
) {
  return services.client.getClientById({
    tenantId: ctx.tenantId,
    clientId: args.id,
    userId: ctx.userId,
    roles: ctx.roles,
  });
}
```

- No resolver should accept or trust a `tenantId` argument.
- All `ServiceSpec` handlers should require `tenantId` explicitly.

---

# 5. Internal BFF / Facade Use Case

This is a core use case and should be highlighted.

## 5.1 Problem

The multi-tenant accountancy platform must integrate with:

- HMRC (multiple endpoints, OAuth flows, brittle error codes).
- Bank APIs (different banks, different schemas).
- External accountancy APIs (like Xero, QuickBooks, etc.).
- Historical systems (CSV imports, legacy REST).

Each has its own:

- authentication,
- rate limits,
- pagination,
- error semantics,
- data shapes.

Exposing this directly to front-ends leads to:

- complex, fragile clients,
- duplicated logic for error handling and retries,
- mixing business logic with glue code.

## 5.2 GraphQL BFF Solution

Introduce an **internal GraphQL facade**:

- A dedicated GraphQL server that:
  - connects to external APIs,
  - uses internal service layer for core entities,
  - defines a cohesive schema for accountancy workflows.

Example types:

```graphql
type Client {
  id: ID!
  name: String!
  vatProfile: VatProfile
  bankAccounts: [BankAccount!]!
  openInvoices(limit: Int = 10): [Invoice!]!
}

type VatProfile {
  registrationNumber: String
  currentObligations: [VatObligation!]!
}

type Query {
  client(id: ID!): Client
}
```

Behind `client(id: ID!)`:

- Resolver chains:
  - internal DB for `Client`,
  - HMRC API for `VatProfile.currentObligations`,
  - bank APIs for `bankAccounts`,
  - internal invoice service for `openInvoices`.

Frontends see a clean graph; the complexity is centralised.

## 5.3 Benefits

- **Reduced coupling**:
  - Frontends rely on a clean, versionable schema.
- **Centralised error handling**:
  - HTTP errors, auth failures, and weird API behaviours are normalised in resolvers.
- **Easier multi-tenancy**:
  - All calls are naturally scoped by `tenantId` in one place.
- **Better caching opportunities**:
  - GraphQL layer can cache stable parts of the graph.
- **Improved Dazzle integration**:
  - Dazzle-generated UISpec can assume a nice graph (Client, Ledger, Task) instead of raw provider-specific responses.

---

# 6. Schema Generation from BackendSpec (Phase 3)

For a full GraphQL builder, LLM agents should implement:

## 6.1 Type Mapping

From `SchemaSpec`:

- Primitive types:
  - `string` → `String`
  - `int` → `Int`
  - `float` → `Float`
  - `boolean` → `Boolean`
  - `id` → `ID`
- Arrays:
  - `array<T>` → `[T!]!` or `[T]` based on nullability conventions.
- Object types:
  - Named object schemas → GraphQL `type` and/or `input`.

From `EntitySpec`:

- Generate:
  - `type EntityName { ... }`
  - optionally `input EntityNameInput { ... }` for mutations.

## 6.2 Service Mapping

From `ServiceSpec`:

```ts
type ServiceSpec = {
  name: string;
  kind: "query" | "mutation" | "command";
  input?: SchemaSpec;
  output?: SchemaSpec;
  auth?: AuthSpec;
};
```

Mapping:

- `kind = "query"` → `type Query { name(args): OutputType }`
- `kind = "mutation"` → `type Mutation { name(args): OutputType }`
- `kind = "command"`:
  - treated as mutation that may return status or updated entities.

Arguments:

- Single input object:
  - Option 1: flat arguments (simple inputs).
  - Option 2: a single `input` arg of an input type (for complex shapes).

Recommendation:

- Prefer **single `input` argument** for non-trivial shapes:

```graphql
type Mutation {
  createInvoice(input: CreateInvoiceInput!): Invoice!
}
```

---

# 7. Resolver Generation Guidelines (for LLM Agents)

LLM coding agents should:

## 7.1 File Structure

For a typical Node/TypeScript GraphQL server (example):

- `schema.graphql` – generated schema.
- `src/resolvers/Query.ts`
- `src/resolvers/Mutation.ts`
- `src/resolvers/EntityName.ts` (for field-level resolvers when needed).
- `src/context.ts` – builds `GraphQLContext` from request.
- `src/services/*` – service layer (can be generated from BackendSpec or handwritten).

For Python (Strawberry/Ariadne/Graphene), a similar structure with modules.

## 7.2 Resolver Pattern

For each `ServiceSpec`:

1. Create a resolver function:
   - input from GraphQL arguments,
   - context from `GraphQLContext`.
2. Map args → service call:
   - include `tenantId` and `userId`.
3. Handle errors:
   - catch service errors,
   - map to GraphQL errors with appropriate messages.

Example (TS-like pseudocode):

```ts
const resolvers = {
  Query: {
    client: async (_parent, args, ctx) => {
      return services.client.getClient({
        tenantId: ctx.tenantId,
        clientId: args.id,
        userId: ctx.userId,
      });
    },
  },
  Mutation: {
    createInvoice: async (_parent, args, ctx) => {
      return services.invoice.createInvoice({
        tenantId: ctx.tenantId,
        userId: ctx.userId,
        input: args.input,
      });
    },
  },
};
```

LLM agents should always:

- handle `tenantId` via `ctx`,
- delegate domain logic to services (not embed it in resolvers),
- keep resolvers as thin as possible.

---

# 8. GraphQL vs REST in Dazzle

Dazzle should treat GraphQL as:

- a **transport skin** over `BackendSpec`, not the underlying model.
- a **powerful option** where:
  - the UI needs highly-composed data,
  - multiple sources need stitching,
  - you want a rich public API.

REST remains:

- excellent for simpler use cases,
- the easiest path for many external integrations,
- the default path in early phases.

GraphQL can coexist with:

- DRF-based REST endpoints,
- DNR-Back service layer,
- Dazzle-generated UISpec.

---

# 9. Summary for Implementation

For LLM coding agents:

1. **Phase 1 (current)**:
   - Focus on a robust `BackendSpec` + REST builder.
2. **Phase 2 (BFF/facade)**:
   - Implement a GraphQL server that:
     - exposes a hand-crafted (but spec-aware) schema,
     - wraps external APIs and internal services.
   - Make this the primary API for complex dashboards/workspaces.
3. **Phase 3 (full builder)**:
   - Implement a GraphQL builder that:
     - generates schema from BackendSpec,
     - generates resolvers that call service layer,
     - enforces multi-tenancy via `GraphQLContext`.

All GraphQL work must:

- avoid introducing tenant IDs in user-facing inputs,
- keep domain logic in services,
- keep `BackendSpec` free from GraphQL-specific concepts.

End of DNR-Back-GraphQL-Spec-v1.
