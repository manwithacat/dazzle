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

entity Project "Project":
  intent: "Tenant-scoped parent (injected tenant_id)"

  id: uuid pk
  name: str(100) required

entity Task "Task":
  intent: "Tenant-scoped child with an intra-tenant FK to Project"

  id: uuid pk
  title: str(100) required
  project: ref Project required

entity Member "Member":
  intent: "Tenant-scoped entity with an author-declared natural-key unique"

  id: uuid pk
  email: str(200) required unique
