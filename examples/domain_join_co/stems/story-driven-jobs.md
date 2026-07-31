# Stem: Story-driven job home (domain_join_co)

## Claim

Verified-domain join demo still needs **job-shaped homes**: admin readiness
strip vs member announcement board — not a bare announcement list warehouse.

## Reconstruct

- admin default: `home` = announcement metrics + status_list (domain/policy) + feed;
  tenant_roots queue opens workspace hubs.
- member default: `announce` (Team Board) = board metrics + feed.
- admin `publish_desk` = draft queue (status=draft) vs live published cards.
- Workspace hub related announcements are a **pull queue** (title+status), not a table.
- Announcement list pipe dual open: **Announcement hub** (id) + **Workspace hub** (workspace FK).
- Announcement hub lifecycle strip includes status (draft/published/archived).
- Join-request queue stays in runtime auth admin — do not invent DSL for it here.

## Not this

- Home = only an announcement list with no join narrative.
- Every persona defaults to the same desk when jobs differ.
- Workspace hub related posts as a warehouse table.

## Expressions

- `dsl/domain.dsl` workspaces; `docs/reference/verified-domain-join.md`
- Product maturity: `scripts/example_product_maturity.py`
