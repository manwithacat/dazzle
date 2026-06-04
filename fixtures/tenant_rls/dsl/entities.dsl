module tenant_rls.entities

# =============================================================================
# Tenant root. Not tenant-scoped (row visibility is the caller's own).
# Declares NO tenant_id — it IS the tenant.
# =============================================================================

entity Workspace "Workspace":
  archetype: tenant
  intent: "Tenant root for shared_schema isolation"

  id: uuid pk
  name: str(100) required

# =============================================================================
# Descendants. Deliberately do NOT hand-declare tenant_id — Phase A's linker
# injects the uniform `tenant_id ref Workspace required` discriminator, and the
# schema generator emits UNIQUE(tenant_id,id), composite intra-tenant FKs,
# tenant-scoped uniqueness, and a (tenant_id) index.
# =============================================================================

# Persona for the intra-tenant scope rules (Phase C). `worker` is the scoped
# persona whose per-user row visibility the generated per-verb RLS scope
# policies enforce *at the database*. There is deliberately NO unscoped (`all`)
# persona on Project: an `all` scope rule compiles to a Tautology (`true`) which,
# OR'd into the per-verb policy body, would make the policy permissive for every
# session (RLS cannot distinguish personas — only the app-layer permit/role gate
# can). Keeping every Project scope rule genuinely restrictive is what makes the
# DB-level intra-tenant proof non-vacuous.
persona worker "Worker":
  description: "Tenant member scoped to their own projects (+ public ones to list)"
  goals: "Manage own projects"
  proficiency: intermediate

# =============================================================================
# Intra-tenant SCOPED entity (Phase C). Project carries an `owner` FK to Member
# and per-verb `scope:` rules that filter by `current_user`, so within a single
# tenant the DB itself (via the generated per-verb RLS policies) enforces
# per-user row visibility — not just the app-layer scope filters.
#
# Deliberate shape (each clause is a Phase-C proof obligation):
#   - read  : owner = current_user                         (own rows only)
#   - list  : owner = current_user or visibility = public  (own + public →
#             proves the read/list → SELECT OR-union, companion §2.1)
#   - update: owner = current_user                         (own rows only)
#   - (no create scope, no delete scope) → INSERT/DELETE have no permissive
#     scope policy → those verbs are DENIED at the DB (companion §1.4 verb
#     coverage). create/delete are not in `permit:` either, so this is
#     consistent end-to-end.
#
# All predicates are NON-dotted (column-eq / current_user / enum literal) — no
# dotted-junction `via` bindings (those raise ValueError in policy mode).
# =============================================================================

entity Project "Project":
  intent: "Tenant-scoped, intra-tenant per-user scoped entity (injected tenant_id)"

  id: uuid pk
  name: str(100) required
  owner: ref Member required
  visibility: enum[private,public]=private

  permit:
    read: role(worker)
    list: role(worker)
    update: role(worker)

  scope:
    read: owner = current_user
      as: worker
    list: owner = current_user or visibility = public
      as: worker
    update: owner = current_user
      as: worker

entity Task "Task":
  intent: "Tenant-scoped child with an intra-tenant FK to Project"

  id: uuid pk
  title: str(100) required
  project: ref Project required

entity Member "Member":
  intent: "Tenant-scoped entity with an author-declared natural-key unique"

  id: uuid pk
  email: str(200) required unique
