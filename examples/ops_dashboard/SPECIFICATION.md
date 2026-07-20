# Operations Dashboard — Specification

## Executive summary

Operations Dashboard is a real-time monitoring and incident-response product. It tracks the operational health of backend services — each monitored System moves through healthy, degraded, critical, and offline states — and records every time-bound incident as an Alert against the System it occurred on, until an engineer acknowledges it. A PagerDuty integration connects the product to the team's external alerting service.

It is built for two kinds of user: Operations Engineers, who watch system health in real time and respond quickly to alerts from a purpose-built Command Center, and Administrators, who manage the monitored estate itself.

Two guarantees stand out. First, every role's permissions, for every kind of record and operation, are declared as machine-readable policy that compiles on demand into an auditable access matrix — permission review is something you run and diff, not something you eyeball — and the row-visibility rules can additionally be submitted to an SMT solver for formal verification. Second, access-controlled records are automatically filtered to what each user is permitted to see, by a rule declared once in the model and applied to every query the product runs.

## What it does

The product manages three kinds of thing:

- **Systems** — the backend services being watched. Each System exists to have its operational health and response characteristics monitored, and carries a live status that moves between healthy, degraded, critical, and offline.
- **Alerts** — time-bound operational incidents. Every Alert is tied to the System it was raised on, and stays open until it is acknowledged.
- **Integrations** — the product's connections to outside services, such as PagerDuty.

Around these, the product provides the full working surface: engineers can browse all Systems, drill into a System's detail, register and edit Systems, raise Alerts, browse and inspect Alerts, and acknowledge an Alert in a single step.

## Who uses it

**Operations Engineers** are the product's primary users. Their stated goals are to monitor system health in real time and to respond quickly to alerts. They work in two places: the Command Center and the Incident Review workspace. Engineers can see every System and every Alert, raise new Alerts, and update Alerts (for example, acknowledging them) — but registering, editing, or removing Systems is reserved for Administrators.

**Administrators** manage the monitored estate. They hold the create, edit, and delete rights over Systems, Alerts, and Integrations, alongside the same visibility engineers have.

## Where work happens

**Command Center** is the heart of the product: real-time operations monitoring and incident response, built for the Operations Engineer. It presents the estate from every useful angle — a live list, timeline, queue, and task inbox of Alerts; Systems as a kanban board, grid, lists, and a metrics panel; and a rich analytical layer over Alerts including bar charts, an insight summary, a comparison view, a cross-tabulated breakdown, a heatmap, line, area, and sparkline trends, and a day timeline. Systems get their own statistical views — histogram, radar, box plot, bullet and bar-track gauges, profile cards, and a cohort strip.

**Incident Review** serves the same engineers for side-by-side pairs in change-management review: Alert metrics beside an Alert list, System metrics, and a confirm-action panel for the Integration connection.

**Incident Response** is a guided, step-by-step experience that walks a responder through three stages: triage, investigate, and acknowledge.

## How work flows through it

A System's health is a journey through four states: healthy → degraded → critical → offline. Engineers move Systems between these states as conditions change — degrading a healthy System, escalating to critical, and restoring it to healthy — with a timestamp recorded at every change.

Ten authored scenarios pin the product's flows down. A representative sample:

- When an Operations Engineer views all system health statuses at a glance, every System appears grouped by status, with critical and offline Systems visually distinguished.
- When an Operations Engineer changes a System from healthy to degraded, its status becomes degraded and the timestamp of the change is recorded.
- When an Operations Engineer acknowledges an alert with one click, the Alert's status becomes acknowledged and the Alert records who acknowledged it.
- When an Operations Engineer views alerts grouped by severity, they appear sorted with critical and high severity above medium and low, most recent first.
- When an Operations Engineer drills into a degraded system, they see the System's detail with its open Alerts and can transition its status from the detail page.
- When an Operations Engineer reviews recent deploy history, they see status-change timestamps per System and can correlate each status change with its triggering Alerts.

## Automation & controls

The product connects to **PagerDuty**, an integration with the team's external alerting service.

## The technical foundation

These guarantees hold because the product is built on Dazzle, and each one can be independently verified by running a single command.

**Security.** Access-controlled records are filtered to what each user is permitted to see. The rule is declared once in the model and applied automatically to every query the product runs, instead of being re-implemented — and re-checked — on each screen (verify: `dazzle rbac report`). Every role's permissions, for every kind of record and operation, are declared as machine-readable policy; they compile on demand into an auditable access matrix, and the row-visibility rules can additionally be submitted to an SMT solver for formal verification (verify: `dazzle rbac prove`).

**Data & reliability.** All data is stored in PostgreSQL — a mature, widely-trusted relational database. There is no bespoke or experimental datastore to operate, secure, or reason about (verify: `dazzle db status`). In production, every change to the data model is applied through versioned, reversible migrations; the live schema is never edited by hand, so upgrades are repeatable and fully auditable (verify: `dazzle db status`).

**Architecture.** The interface is rendered on the server and progressively enhanced. There is no heavy single-page JavaScript application to maintain, which keeps the product fast, accessible, and simple to operate (verify: `dazzle validate`).

<!-- dazzle-spec-brief: sha256:ee42c7ee092e9ab1e618e84b0449a4d76b3cd4769217c704ba67f4cf0f502fb0 -->
