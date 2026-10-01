# Vendor bot identity

The weekly `update-vendors` cron opens a PR on `main`. This page covers the one
non-obvious requirement: **that PR must be authored by the same identity that
authored its commit**, and how to configure that.

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
weekly and would have recreated the condition on every release.

There is a second, unrelated blocker: workflows triggered by the Actions app
itself land in `action_required` (anti-recursion protection), and there is no
API to approve them. A maintainer-owned identity avoids both problems at once.

## Why a GitHub App rather than a PAT

An App **installation token expires after about an hour**, so it cannot be
stored as a long-lived secret. The workflow therefore mints one per run with
`actions/create-github-app-token`, using the App's private key. That is why the
App is the recommended shape and a PAT is only a fallback.

A classic PAT does not expire, which is simpler — but it is tied to a person.
If they leave, the cron breaks silently.

---

## Setup (one time)

### 1. Create the App

**Settings → Developer settings → Apps → New GitHub App**

| Field | Value |
|---|---|
| App name | `dazzle-vendor-bot` (or similar) |
| Homepage / URL | anything non-empty |
| Webhook | **Active: off** — the workflow does not receive webhooks |

**Repository permissions**

| Permission | Access |
|---|---|
| Contents | **Read and write** |
| Pull requests | **Read and write** |

**Account permissions** — none needed.

Click **Create GitHub App**. You will be shown a **private key** (`.pem`)
exactly once — download it now.

### 2. Install the App on this repository

Still on the App page → **Install App** → choose the owner (`manwithacat`) →
select **Only select repositories** → pick `dazzle` → **Install**.

The App's login, shown on the App page, is what you will use for
`VENDOR_ACTOR_NAME`. It looks like `dazzle-vendor-bot[bot]`, and its noreply
email is `<app-slug>[bot]@users.noreply.github.com`.

### 3. Store the four values

Repository → **Settings → Secrets and variables → Actions**.

**Variables** tab → *New repository variable* (three):

| Name | Value | Example |
|---|---|---|
| `VENDOR_BOT_APP_ID` | the numeric App ID from the App page | `1234567` |
| `VENDOR_ACTOR_NAME` | the App's login | `dazzle-vendor-bot[bot]` |
| `VENDOR_ACTOR_EMAIL` | its noreply email | `dazzle-vendor-bot[bot]@users.noreply.github.com` |

**Secrets** tab → *New repository secret* (one):

| Name | Value |
|---|---|
| `VENDOR_BOT_PRIVATE_KEY` | the full contents of the downloaded `.pem`, **including** the `-----BEGIN/END PRIVATE KEY-----` lines |

The actor identity is a *variable*, not a secret — it is public information, and
keeping it in variables makes it visible in workflow logs for debugging.

## What happens if this is not set

The workflow **fails loudly** with `::error::vendor bot App is not configured`
and names the missing item. It deliberately does not fall back to
`GITHUB_TOKEN`, because that fallback recreates the exact stuck-PR condition
this exists to prevent — a silent fallback is worse than a red cron.

## Verify

Trigger it manually:

```bash
gh workflow run update-vendors.yml --ref main
gh run list --workflow=update-vendors.yml --limit 1
```

If the App is misconfigured the run fails at *"Assert vendor bot App is
configured"* with the missing item named.

Once a vendor PR exists, confirm it is actually mergeable:

```bash
gh pr view <n> --json mergeStateStatus,author
gh api repos/manwithacat/dazzle/commits/<sha> \
  --jq '{author: .author.login, committer: .committer.login}'
```

`mergeStateStatus` should reach `CLEAN` rather than sitting at `BLOCKED`, and the
two logins should match the PR author.

## Fallback: a PAT

If you would rather not manage an App, a classic PAT owned by a maintainer works
as a drop-in — set `VENDOR_BOT_TOKEN` to it and switch the *Mint installation
token* step's `GH_TOKEN` to that secret. You still need
`VENDOR_ACTOR_NAME` / `VENDOR_ACTOR_EMAIL` set to your account login and noreply
email. Trade-off: the cron breaks if that person's access changes, and they
become the author of every vendor PR.
