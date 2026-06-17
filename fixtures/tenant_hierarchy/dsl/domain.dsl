module tenant_hierarchy.domain

# Worked example of the tenant-hierarchy + membership authoring pattern
# (ADR-0036 + ADR-0037). A three-level tenant tree — Region ▸ Trust ▸ School —
# plus a tenant-scoped data entity (Report). See README.md for the full pattern.

persona staff "Staff":
  capabilities: [read]

# ── Tenant kinds (each resolved by host; linked by `parent:`) ─────────────────

entity Region "Region":
  intent: "Root tenant kind — the RLS partition + hierarchy root. Members are declared here."
  id: uuid pk
  slug: slug required
  name: str(120) required
  role: str(40)
  tenant_host:
    domain: hierarchy.example
    slug_field: slug
    canonical_hosts: [localhost]   # apex / dev / health-check host → no tenant bound
    order: 1
  membership:
    roles: role            # ADR-0037: membership ONLY on the root kind

entity Trust "Trust":
  intent: "Mid tenant kind — resolved at trust.<host>; child of Region."
  id: uuid pk
  slug: slug required
  name: str(120) required
  region: ref Region required
  tenant_host:
    domain: hierarchy.example
    slug_field: slug
    canonical_hosts: [localhost]   # must match across all kinds on this domain
    parent: region         # hierarchy edge → Region
    order: 2

entity School "School":
  intent: "Leaf tenant kind — resolved at school.<host>; child of Trust."
  id: uuid pk
  slug: slug required
  name: str(120) required
  trust: ref Trust required
  tenant_host:
    domain: hierarchy.example
    slug_field: slug
    canonical_hosts: [localhost]   # must match across all kinds on this domain
    parent: trust          # hierarchy edge → Trust
    order: 3

# ── Tenant-scoped data ────────────────────────────────────────────────────────

entity Report "Report":
  intent: "Tenant-scoped data. One READ scope auto-selects aggregate-vs-single by host."
  id: uuid pk
  title: str(200) required
  school: ref School required
  permit:
    list: role(staff)
    read: role(staff)
    update: role(staff)
  scope:
    # ADR-0036: on LIST/READ the framework expands this to the self-or-ancestor
    # disjunction — single at a School host, aggregate at a Trust/Region host.
    # Both list AND read must be declared: the runtime resolves row scope per
    # operation, so a list endpoint with only a `read:` rule default-denies.
    list: school = current_tenant
      as: staff
    read: school = current_tenant
      as: staff
    # Writes stay single (aggregate hosts are read-only) — unexpanded leaf check.
    update: school = current_tenant
      as: staff

# A viewable list surface so the current_tenant scope is exercisable at an HTTP
# endpoint (aggregate at an ancestor host, single at a leaf host).
surface report_list "Reports":
  uses entity Report
  mode: list
  section main:
    field title "Title"

workspace ops "Operations":
  reports:
    source: Report
    display: list
