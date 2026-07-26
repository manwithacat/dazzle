# Human QA runbook — example fleet (L4)

**Audience:** humans (and the operator who arms the fleet)
**When:** after L1–L3 agent floor is green (smoke structure=0, auto_seed=0)
**Doctrine:** [Agent QA ladder](agent-qa-ladder.md) — humans are **L4**, not inventory walkers

**Last machine floor (agent):** 2026-07-26 post-prep smoke-dig (`./scripts/prep_example_fleet_qa.sh --smoke`) — all 9 showcase apps `ok=True` / `auto_seed=0` / fail=0. Magic-link OK under `DAZZLE_QA_MODE=1`. Re-run smoke after any restart before trusting this sheet.

---

## 0. Operator prep (before humans arrive)

### 0.1 Arm the fleet

```bash
# From monorepo root — QA mode is required for Personas / magic-link
# Hub path (preferred if example hub is already running):
#   restart each app via hub UI or POST /_hub/stop/<app> then /_hub/start/<app>
#   (supervisor now sets DAZZLE_QA_MODE=1 when --test-mode)

# Direct path (reliable):
for app port in \
  simple_task 9100 \
  support_tickets 9101 \
  invoice_ops 9102 \
  contact_manager 9103 \
  ops_dashboard 9104 \
  project_tracker 9105 \
  design_studio 9106 \
  hr_records 9107 \
  fieldtest_hub 9108
do
  : # start each with DAZZLE_QA_MODE=1 DAZZLE_ENV=development
  #   dazzle serve --host 127.0.0.1 --port $port --test-mode
done
```

Or use the prep helper:

```bash
./scripts/prep_example_fleet_qa.sh   # restarts showcase + optional smoke
```

### 0.2 Green floor (agent)

```bash
# Mechanical L2.5 — do not invite humans on red auto_seed / structure
dazzle qa smoke-dig --all --no-coverage --max-clicks 12
# Expect: each showcase app ok=True, auto_seed=0, structure=0 in issue_codes
```

Spot-check magic-link:

```bash
dazzle qa login manager -u http://127.0.0.1:9100
# prints a one-shot URL; open it — should land authenticated
```

### 0.3 URLs humans use

| App | Local | Hub host (if TLS hub up) |
|-----|--------|---------------------------|
| simple_task | http://127.0.0.1:9100 | https://simple_task.dazzle.local/ |
| support_tickets | http://127.0.0.1:9101 | https://support_tickets.dazzle.local/ |
| invoice_ops | http://127.0.0.1:9102 | https://invoice_ops.dazzle.local/ |
| contact_manager | http://127.0.0.1:9103 | https://contact_manager.dazzle.local/ |
| ops_dashboard | http://127.0.0.1:9104 | https://ops_dashboard.dazzle.local/ |
| project_tracker | http://127.0.0.1:9105 | https://project_tracker.dazzle.local/ |
| design_studio | http://127.0.0.1:9106 | https://design_studio.dazzle.local/ |
| hr_records | http://127.0.0.1:9107 | https://hr_records.dazzle.local/ |
| fieldtest_hub | http://127.0.0.1:9108 | https://fieldtest_hub.dazzle.local/ |

**Login:** open the app → **Personas** panel on the landing page → “Log in as …”.
Emails are `{persona_id}@example.test`. Magic-link only (no passwords).

---

## 1. How to work (humans)

### Do

1. Pick **one app + one persona + one job** from the tables below.
2. Start from the **landing URL** after persona login (not a bookmarked deep link).
3. Prefer **clicks you can see** (journey rule) — not typing random `/app/...` URLs.
4. File findings with the template in §4.
5. Spend time on **confusion / job fit / empty states**, not re-counting RBAC 403s.

### Don’t

| Noise | Why ignore |
|-------|------------|
| 403 on system health, deploy history, platform admin | `rbac_expected` — not product bugs |
| Nested “card in card” / weird region chrome | Machine structure oracle owns this (recently fixed) |
| “Admin can see everything” | Separate admin persona jobs if needed |
| Empty queues after someone wiped the DB | Ask operator to re-seed (`demo reset-and-load`) |

---

## 2. Tier A — must feel good (~15 min each)

### 2.1 simple_task · **manager** · port 9100

| | |
|--|--|
| **Job** | As team lead, see open work and open one task without getting lost. |
| **Start** | Log in as **manager** → land on home |
| **Script** | 1) Is the home a useful desk (not a blank warehouse)? 2) Open Tasks. 3) Open one task detail. 4) Create a small task if create is obvious. |
| **Pass** | Detail opens; create doesn’t 500; you always know where you are |
| **Also try** | **member** — only own work, no accidental admin chrome |

### 2.2 support_tickets · **manager** · port 9101

| | |
|--|--|
| **Job** | Triage: see queue pressure and open a ticket to understand status. |
| **Start** | **manager** |
| **Script** | 1) Home / workspace — queues or metrics first? 2) Open a ticket from a queue or list. 3) Can you see status / assignee / next step? |
| **Pass** | One ticket hub in ≤3 clicks from home |
| **Also try** | **agent** — “my queue” clarity; **customer** — limited surface, no staff leaks |

### 2.3 invoice_ops · **approver** · port 9102

| | |
|--|--|
| **Job** | Approve or reject a submitted invoice with enough context (lines, amounts). |
| **Start** | **approver** |
| **Script** | 1) Finance / ops home. 2) Open an invoice that needs a person. 3) See line items + payment trail without 500s. 4) Don’t expect payment *create* as approver (finance-only). |
| **Pass** | Invoice hub loads; line item drill works; no “Something went wrong” on detail |
| **Also try** | **finance** — “New Payment Attempt” create form loads (200). **requester** — create invoice + lines. |

### 2.4 contact_manager · **user** · port 9103

| | |
|--|--|
| **Job** | Find a contact and open their hub. |
| **Start** | **user** |
| **Script** | 1) Home. 2) Search or browse contacts. 3) Open one contact. 4) Related companies/notes if present. |
| **Pass** | Search or list is obvious; detail is a hub, not a dead form |

### 2.5 project_tracker · **manager** · port 9105

| | |
|--|--|
| **Job** | From the board/queue, open a task and see project context. |
| **Start** | **manager** |
| **Script** | 1) Dashboard / open task queue. 2) Click a **queue row title** (not only list chrome). 3) Task detail loads (not 404). 4) Hop to project if linked. |
| **Pass** | Queue drill → task detail works (regression: was 404 without read scope) |
| **Also try** | **member** — only assigned work |

---

## 3. Tier B — showcase density (~10–15 min each)

### 3.1 ops_dashboard · **ops_engineer** · 9104

- Land on ops home: metrics + queues first?
- Open one alert/incident-style row; confirm drill isn’t empty.

### 3.2 design_studio · **designer** · 9106

- Portfolio / campaign desks feel job-shaped?
- Open asset or campaign detail; related files make sense?

### 3.3 hr_records · **hr_admin** · 9107

- Staff directory useful names?
- Department / role navigation honest (no fake org-chart claims)?
- Open one person hub.

### 3.4 fieldtest_hub · **manager** · 9108

- Fleet overview + device attention without Alpine residue?
- Open a non-active device / issue from queue.
- Optional: **tester** personal dashboard.

---

## 4. Finding template (copy into issue / chat)

```text
app:
persona:
url:
job_attempted:
expected:
actual:
severity: blocking | confusing | polish
category: bug | missing | confusion | story_gap | aesthetic | praise
ownership_guess: product | seed | rbac_expected | framework | unclear
blocks_pilot: yes | no
screenshot: (optional)
```

**Operator mapping**

| ownership_guess | Route |
|-----------------|--------|
| product | improve example-apps / issue |
| framework | framework-ux / hm-convergence |
| seed | re-seed; don’t file as bug |
| rbac_expected | drop |
| unclear | 5-min agent reproduce, then reclassify |

---

## 5. Session agenda (half day)

| Block | Time | Who | Activity |
|-------|------|-----|----------|
| 0 | 20m | Operator | Prep script + smoke-dig green |
| 1 | 90m | Human | Tier A (5 apps × ~15m) |
| 2 | 60m | Human | Tier B (4 apps) |
| 3 | 20m | Human | Narrow viewport pass on one Tier A app |
| 4 | 30m | Operator | Triage findings → issues / improve backlog |

---

## 6. Exit criteria (L4 complete for this pack)

- [ ] No **blocking** job failure without a filed finding
- [ ] No surprise **404/500** on primary queue/create/detail drills
- [ ] Findings are job-language, not structure/RBAC noise
- [ ] Polish parked separately from pilot blockers

---

## 7. Operator troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Magic-link / Personas 500 | `DAZZLE_QA_MODE` off | Restart serve with QA mode / hub after `c8992dfdb` supervisor |
| Empty queues | DB wiped / no seed | `dazzle demo reset-and-load` in app dir |
| 403 on admin chrome | Expected | Ignore |
| Nested chrome / layout double card | Should be fixed | File framework if still seen after hard refresh |
| Port in use | Stale serve | Kill listener on that port; restart |

---

## 8. Out of scope for this pack

- acme_billing, domain_join_co, llm_ticket_classifier (start only after Tier A/B green)
- Deep multi-day multi-tenant pilots
- Visual design-system pixel polish (unless blocking trust)

---

## Related

- [Agent QA ladder](agent-qa-ladder.md)
- ADR-0054 swap/identity (machine structure)
- `dazzle qa smoke-dig` — L2.5 density
- `scripts/prep_example_fleet_qa.sh` — arm + optional smoke
