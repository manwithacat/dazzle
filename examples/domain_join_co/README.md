# Domain Join Co — worked example: verified-domain self-service join

A kayfabe app for the **verified-domain self-service join** flow (#1424): a
company proves it owns its email domain, then an employee whose *verified* work
email matches that domain self-joins the company workspace under a per-tenant
policy. The admin verifies the domain, sets the policy, approves join requests,
and posts announcements; joined members read the team's board.

> The full operator loop (create the domain connection → DNS-TXT verify → set the
> join policy → join → approve → land on the tenant host) is in
> **[`docs/reference/verified-domain-join.md`](../../docs/reference/verified-domain-join.md)**.

## DSL vs runtime — what lives where

The verified-domain machinery is deliberately **not** DSL. The split:

| Concern | Where |
|---|---|
| The workspace members join into (`tenant_host:` + `membership:`) | **DSL** — `dsl/domain.dsl` |
| Tenant-scoped data a join unlocks (`Announcement`, `current_tenant` scope) | **DSL** — `dsl/domain.dsl` |
| Per-persona onboarding overlays | **DSL** — `dsl/onboarding.dsl` |
| The domain connection (`type="domain"`), DNS-TXT verification | **runtime** — `dazzle auth` CLI / admin console |
| `domain_join_policy` (off / auto_join / admin_approval) | **runtime** — admin console |
| `restrict_membership_to_verified_domains` | **runtime** — admin console |
| The join-request approval queue | **runtime** — `/auth/join-requests` |

So this app is a `tenant_host:` + `membership:` workspace for the (runtime-driven)
join flow to land members into — nothing in the DSL "turns on" verified-domain
join; that's configured per the runbook.

## What it declares (`dsl/domain.dsl`)

- **`Workspace`** — the root tenant kind, resolved by host (`tenant_host:`,
  `domain: domainjoin.example`) and declaring `membership: roles: role`
  (ADR-0037: membership on the root kind). This is the verified-domain workspace
  a company joins under.
- **`Announcement`** — tenant-scoped data (`workspace: ref Workspace`) with a
  `workspace = current_tenant` scope on every operation. Joined members read it;
  the admin authors it. This is what membership *grants* — proof the join landed
  the member into exactly one workspace's row-fence.

Two personas: **`admin`** (Workspace Admin) and **`member`** (Team Member), each
with a terse onboarding guide in `dsl/onboarding.dsl`.

## Run it

```bash
cp .env.example .env          # edit DATABASE_URL / REDIS_URL
dazzle serve --local          # UI http://localhost:3000 · API http://localhost:8000/docs
```

Then follow **[the runbook](../../docs/reference/verified-domain-join.md)** to
create the domain connection, verify it via DNS-TXT, set the join policy, and walk
a verified-email employee through the join.

## How it's exercised

`dazzle validate` is clean; the per-persona guides clear the guide quality bar
(`tests/unit/test_example_guide_bar.py`) and the `dazzle ux verify --guides`
runtime oracle. The verified-domain join *mechanism* itself (admission gate,
fail-closed-on-`email_verified`, no enumeration oracle) is proven against real
Postgres in `tests/integration/test_domain_join_routing_pg.py`.
