# feedback_widget: review posture, element anchors, server-stamped context, agent read path

Plan and contract for the work split across three worktrees (2026-10-25).
Consumer: AegisMark (`/Volumes/SSD/AegisMark`), spec
`docs/superpowers/specs/2026-10-25-native-review-widget.md` and the survey
`2026-10-25-review-widget-landscape.md` there. Decision taken by the
maintainer: **evolve `feedback_widget` / `FeedbackReport`**, no sibling
entity.

## 1. DSL and IR (part S)

```
feedback_widget: enabled
  shortcut: none                      # existing (#1842)
  categories: [bug, ux, copy, data, question, idea]   # now APPLIED (was parsed, unread)
  severities: [p1, p2, p3, note]                       # now APPLIED
  capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot, htmx_history]
  review:
    personas: [super_admin, trust_admin]  # who gets the review posture (required when review: is present)
    shortcut: alt+shift+r                  # default; `none` turns it off; a bare key is allowed (same grammar as `shortcut:`)
    screenshot: off                        # off (default) | optional — optional shows "Attach screenshot" where getDisplayMedia exists
```

`FeedbackWidgetSpec` gains `review: FeedbackReviewSpec | None` with
`personas: list[str]`, `shortcut: str = "alt+shift+r"`, `screenshot: str = "off"`.
The parser validates `screenshot` ∈ {off, optional}; the validator checks every
review persona is a declared persona. The first severity is the default when
the DSL declares severities; otherwise the framework default stays `minor`.

`FEEDBACK_REPORT_FIELDS` changes:
- `category` / `severity` enums are built from the spec's lists by the
  linker (`_build_feedback_report_entity(fw)`), defaults = framework lists.
- new: `anchor: json`, `context: json`, `surface: str(100)`,
  `review_session: str(40)`. Keep `annotation_data`, `page_snapshot`,
  `screenshot_data` (the screenshot stays a text data URL, capped 1.5 MB).
- `feedback_admin` surface: `page_size = 25`; columns gain `surface` and
  `severity` first; `review_session` shown.

Lint: `categories:` / `severities:` leave the `W_DECLARED_NOT_READ`
registry (they are read now). `review.personas` unknown persona → validate
error. Semantics KB (`mcp/semantics_kb/feedback.toml`) and the docs
(`docs/reference/runtime-capabilities.md`, `grammar.md`) describe the block.

## 2. Chrome and page (part S)

`app_chrome.resolve_app_chrome` emits, when the widget is mounted:
- `dz-feedback-shortcut` (existing), `dz-feedback-categories` (comma list),
  `dz-feedback-severities` (comma list), `dz-feedback-screenshot` (off|optional),
  `dz-feedback-review-shortcut` (the review chord or `none`).
`render/dispatch._feedback_identity_meta` additionally emits
`dz-feedback-review` = `1` when the signed-in user's role is one of
`review.personas` (normalised role names, the same normalisation as
`dz-user-role`), else absent.

`_render_shell` puts on `<body>`: `data-dz-surface` (ctx.view_name),
`data-dz-entity` (ctx.entity_ref), `data-dz-record` (the detail item id when
the page is a detail/edit of one record; else absent), `data-dz-workspace`
(ctx.workspace_name), `data-dz-persona` (normalised first role). Only when
authenticated. Empty values are omitted.

## 3. The client (part C) — `feedback-widget.js`, one file, no deps

Keeps every behaviour the existing node tests pin (#869 toast once, #1841
inert/aria/focus, #1842 shortcuts, idempotent mount, reattach after body
swap, no identity → no mount) and adds:

- **Isolation.** The widget's DOM lives in a `<dz-feedback>` host appended to
  `<body>` with an **open shadow root**; its stylesheet is a string in the JS
  (migrated from `packages/hatchi-maxchi/components/feedback-widget.css`,
  which is then removed from the HM sources and `scripts/build_dist.py`
  rerun). `:host` pins `font`, `font-size: 14px`, `line-height`, `color`,
  `direction`; units in px. The floating button stays visible and keyboard
  reachable exactly as before; `document.activeElement` semantics for the
  focus tests move to the shadow root's `activeElement`.
- **Report posture (everyone).** As today, but categories and severities come
  from the metas (`dz-feedback-categories` / `-severities`; labels =
  sentence-cased value, `p1` → `P1`), default severity = first listed.
- **Review posture** (`dz-feedback-review` meta = `1`): the review chord
  (`dz-feedback-review-shortcut`) or an "Point at it" button in the panel
  arms anchor mode: `pointermove` (passive) → `elementFromPoint` → outline
  box in the shadow root sized from `getBoundingClientRect()`, labelled with
  the anchor path; `Esc` disarms; capture-phase `click` with
  `preventDefault()` + `stopPropagation()` (htmx never sees it) opens the
  note card beside the box: textarea (autofocus, focus trapped), severity
  pills, category defaulting to the first category whose value is `ux` else
  the first, optional "Attach screenshot" (only when
  `dz-feedback-screenshot` = optional and `navigator.mediaDevices?.getDisplayMedia`
  exists). `Enter` submits, `Shift+Enter` newline, `Esc` cancels, focus
  returns to the clicked element. The bare-key rule from #1842 applies to
  the review chord too (ignored while focus owns the key).
- **Anchor record** (`anchor` JSON):
  ```
  {"dz_anchor": "surface/region/row-or-field/action" | null,
   "css": "<unique selector>", "text_quote": {"exact": "...", "prefix": "...", "suffix": "..."},
   "rect": {"x":0,"y":0,"w":0,"h":0}, "scroll": {"x":0,"y":0}, "viewport": [w,h],
   "tag": "button", "role": "button"}
  ```
  `dz_anchor` is derived by walking up from the element: `[data-dz-action]`
  → `.dz-form-field` (its `<label for>` / input name) → `[data-dz-row-id]`
  → `[data-dz-region-name]` → `body[data-dz-surface]`; joined with `/`,
  `null` when only the surface is known. `css` comes from a vendored,
  attributed copy of `@medv/finder` 4.0.2 (MIT) with the attribute
  predicate limited to `data-dz-*`, `name`, `id`, `data-test-id`,
  `timeoutMs: 200`; `text_quote` is up to 64 chars of trimmed `textContent`
  with 32-char prefix/suffix from the parent's text.
- **Context** (`context` JSON): `url, referrer, surface, entity, record,
  workspace, persona, viewport [w,h], dpr, ua, lang, color_scheme,
  review_session, htmx_history, console_errors`. `htmx_history` = last 10
  `{method, path, status, ms}` from `htmx:before:request` / `htmx:after:request`
  / `htmx:response:error` (no fetch patching); `console_errors` = ring
  buffer of 20 strings (≤ 500 chars) from `error`, `unhandledrejection` and
  `console.error`. No bodies, cookies or form values. `review_session`
  (per tab, `YYYY-MM-DD-xxxx`, sessionStorage) is also sent as its own field.
  `surface` is sent as its own field too.
- **Submission.** `POST /feedbackreports` JSON with header
  `Idempotency-Key: <uuid>` and field `idempotency_key` (same value), the
  anchor/context as objects, `page_url`, `page_title`, etc. The JSON stays
  under 60 KB (truncate `page_snapshot` first). Offline queue in
  localStorage keyed by the idempotency key; retried on the next load and on
  `visibilitychange`; a 2xx or a 200-replay marks sent; 4xx other than 409/429
  marks failed; 409 means in flight (retry later).
- **Pins** (review posture only): on boot and after `htmx:after:settle`,
  `GET /feedbackreports?page_url=<location.href without query>&status=new`
  (plus `triaged`) and render one numbered pin per report, re-anchored in
  the order `dz_anchor` → `css` → `text_quote` → `rect`; an unmatched anchor
  renders an **orphaned** pin at `rect` with the quote. A pin opens its note
  (read-only) with a Resolve button → `PUT /feedbackreports/<id>` `{status: "resolved"}`
  (the entity's transitions permit `new → triaged → resolved`; do both PUTs).
- **Screenshot** (optional policy): `getDisplayMedia({preferCurrentTab: true,
  selfBrowserSurface: 'include', surfaceSwitching: 'exclude', video: {...}})`
  from the click handler, hide the card, await two `requestAnimationFrame`s,
  draw one frame to a canvas, stop tracks, `image/webp` q 0.8, ≤ 1.5 MB →
  `screenshot_data` as a data URL; user can draw hide rectangles (black
  fill) before send. Feature-detected; never on mobile.
- **Size budget**: ≤ 12 kB gzipped (the file carries the stylesheet and the
  finder). Measure in a test (`gzip` of the file).
- Tests: extend `tests/unit/test_feedback_widget_client.py`'s fake DOM with
  `attachShadow`, `customElements.define`, `ShadowRoot` queries, and add
  cases for metas-driven categories, review arming, anchor derivation,
  context capture, idempotent replay and the queue; add a Playwright test
  (`pytest.importorskip("playwright.sync_api")`, skips without Chromium)
  that renders a small page, arms, clicks, types, submits, and asserts the
  intercepted POST and the pin.

## 4. Server (part S)

`POST /feedbackreports` (a dedicated handler mounted ahead of the generated
create route, or a hook on it — whichever is cleanest, with a test proving
precedence):
- stamps `reported_by` = session email and `persona` = normalised role
  (payload values ignored); anonymous → 401 as today;
- caps: `description` ≤ 4 000 chars, `anchor` + `context` + `page_snapshot`
  + `console_errors` ≤ 32 KB, `screenshot_data` ≤ 1.5 MB → 422 with a message;
- idempotency per IETF draft-ietf-httpapi-idempotency-key-header-07: the
  key from the `Idempotency-Key` header (fallback: the body field) is stored
  in `idempotency_key`; a replay returns the stored row with 200 and
  `Idempotent-Replayed: true`; a unique-violation race is caught and answered
  the same way (never a 500); a different payload under the same key → 422;
- per-user rate limit 30/min, 300/day in process memory → 429 with
  `Retry-After` (independent of the slowapi profile).
`GET /feedbackreports` must accept `page_url`, `surface`, `review_session`,
`status` (comma list) and `since` (ISO, `created_at >=`) filters. Check what
the generated list route already supports and add the rest.

## 5. MCP tool and CLI impl (part M)

`cli/feedback_impl.py`: the target is `DAZZLE_FEEDBACK_URL` when set (else
`.dazzle/runtime.json` as today) and auth is `DAZZLE_FEEDBACK_COOKIE`
(`name=value`, the session cookie) or `.dazzle/session.json`. `feedback_list`
gains `since`, `surface`, `review_session`, `page_url`, `status` (comma
list) and groups the result by `review_session` when present; `feedback_get`
returns `anchor` and `context` parsed; new `feedback_summarise` (open notes
grouped by `surface` then severity, counts and the newest three
descriptions). The MCP `feedback` tool (`tools_consolidated._tool_feedback`,
`handlers/feedback.py`) exposes the new filters and `summarise`; the KB
workflow mentions `review_session`. Tests with a fake httpx transport.

## 6. CHANGELOG (part S writes; others append their bullets)

Under `## [Unreleased]`: Added (review posture, anchors, context, pins,
screenshot policy; server-stamped identity, idempotency, caps, rate limit;
list filters; MCP filters + summarise + remote target), Fixed (categories /
severities applied; replayed key no longer 500; feedback_admin pager),
Agent Guidance (how to read review notes from a deployed app). Every bullet
"consumer-forced by aegismark". Version bump is the maintainer's.

## 7. Out of scope now

Replay recording; a file-store screenshot (`dazzle_files`); comments /
threads on a report; a per-user single-key override stored in preferences
(the chord default + `none` satisfies 2.1.4).
