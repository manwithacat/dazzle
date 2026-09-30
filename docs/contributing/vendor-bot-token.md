# Vendor bot identity

The weekly `update-vendors` cron opens a PR on `main`. This page covers the one
non-obvious requirement: **that PR must be authored by the same identity that
authored its commit.**

## Why this is not automatic

GitHub Actions' built-in `GITHUB_TOKEN` produces two *different* identities for
one PR:

| Role | Identity it gets |
|---|---|
| PR author | `app/github-actions` |
| Commit author (`git config` in the workflow) | `github-actions[bot]` |

Branch protection here sets `require_extra_approval_for_unattributed_changes`.
With the two identities differing, the required extra approval can **never** be
granted — a bot-authored PR cannot review itself. The result is a PR that is
permanently `BLOCKED` with every check green and nothing left to satisfy.

This is not theoretical: vendor PRs from 2026-09-21 sat in exactly that state
until 2026-09-29, when each had to be re-authored by hand. The cron still ran
weekly and would recreate the condition on every release.

There is a second, unrelated blocker: workflows triggered by the Actions app
itself land in `action_required` (anti-recursion protection), and there is no
API to approve them. A human-owned token avoids both problems at once.

## Setup (one time)

### 1. Create the identity

Either is fine:

- **A GitHub App** (preferred) installed on this repository only, owned by a
  maintainer, with these repository permissions:
  - `Contents`: Read and write
  - `Pull requests`: Read and write
- **A personal access token** belonging to a maintainer, with `contents:write`
  and `pull-requests:write`. Simpler, but it is tied to a person — if they
  leave, the cron breaks.

An App installation token **cannot report its own identity** (`GET /user` is
user-to-server only), which is why the commit identity is declared explicitly
in step 3 rather than discovered.

### 2. Store the token

Repository → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `VENDOR_BOT_TOKEN` | the App's installation token, or the PAT |

### 3. Declare the commit identity

Same screen, **Variables** tab → New repository variable:

| Name | Value | Example |
|---|---|---|
| `VENDOR_ACTOR_NAME` | the App's login (or your account login) | `my-org-vendor-bot[bot]` |
| `VENDOR_ACTOR_EMAIL` | its noreply email | `my-org-vendor-bot[bot]@users.noreply.github.com` |

These are variables, not secrets — the identity is public information, and
using variables keeps it visible in the workflow logs for debugging.

## What happens if this is not set

The workflow **fails loudly** with `::error::vendor bot is not configured` and
names the missing item. It deliberately does not fall back to `GITHUB_TOKEN`,
because that fallback recreates the exact stuck-PR condition this exists to
prevent — a silent fallback is worse than a red cron.

## Verifying a vendor PR is mergeable

```bash
gh pr view <n> --json mergeStateStatus,author
gh api repos/manwithacat/dazzle/commits/<sha> \
  --jq '{author: .author.login, committer: .committer.login}'
```

`mergeStateStatus` should reach `CLEAN` rather than sitting at `BLOCKED`, and
the two logins above should match the PR author.
