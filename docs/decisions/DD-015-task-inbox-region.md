# DD-015: Multi-source task inbox region — parked until a consumer needs one landing list across entities

```yaml
id: DD-015
status: PARKED
issues: [1015, 1145, 1232, 1303]
adrs: [0057, 0010, 0023, 0053]
decided: 2026-10-16
decided_at_sha: a112b3d34f2ada0a52007a22386ba5354f9df1d1
parent: flense-programme
```

## One-line intent

`display: task_inbox` gathered rows from several entities into one
prioritised "what needs me" list: one typed task per row (`as_task`) or one
count chip per source (`count_as`), each source scoped by its own entity's
RBAC. AegisMark was its only consumer and dropped its last use in fb673bc8
(2026-10-16, "focused Teacher Workspace", WP7); no example, fixture or other
consumer declares it, and `dazzle coverage --consumers --fail-on-uncovered`
reported it uncovered. The operator cut it the same day (ADR-0057). The
HaTchi-MaXchi `task-inbox` Hyperpart (`contracts/task_inbox.py`,
`components/task-inbox.css`, gallery page) stays: HM is exempt and keeps
speculative Hyperparts.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`a112b3d34f2ada0a52007a22386ba5354f9df1d1`, the parent of the cut);
`git show a112b3d34:<path>` returns every file below.

**DSL and IR.** `task_inbox_config:` on a workspace region, parsed by
`WorkspaceParserMixin._parse_task_inbox_config_block` and its four helpers in
`core/dsl_parser_impl/workspace.py` (plus `_kw_task_inbox_config` in the
region keyword table):

```dsl
task_inbox_config:
  empty_state: "All caught up."
  order: [urgency, deadline]
  sources:
    - source: AssessmentEvent
      filter: state = "due_today"
      as_task:
        icon: register
        title: "Register {{ class.name }}"
        meta: "{{ period.label }}"
        via:
          student: student.profile
    - source: ManuscriptFeedback
      filter: state = "ready_for_review"
      count_as: "manuscripts ready to review"
```

IR in `core/ir/workspaces.py`: `TaskInboxConfig(sources, order, empty_state)`,
`TaskSource(source, filter, as_task, count_as)` with `as_task`/`count_as`
mutually exclusive (enforced at parse time), `TaskSourceTemplate(icon, title,
meta, via_joins)`; `WorkspaceRegion.task_inbox_config`;
`DisplayMode.TASK_INBOX`.

**Runtime.** `http/runtime/workspace_card_fetchers._fetch_task_inbox_items_per_source`
fans out one `repo.list` per source (`asyncio.gather`, 50 rows per source),
each with a per-source context so `_apply_workspace_scope_filters` evaluates
that entity's own `scope:` rules (default-deny when none match) and the
source `filter:` goes through `_extract_condition_filters` with the source's
FK target map (#1232, dotted left-hand paths). One failing source logs and
renders empty. `workspace_card_data._build_task_inbox_payload` turns rows into
items via `_items_from_template` (`{{ field.path }}` interpolation,
`via_joins` aliases resolved against FK-hydrated rows, #1145) and counts into
chips; urgency comes from the row's `urgency`/`severity`/`priority` mapped to
overdue / due / soon / later. Drill: the route builder stamped
`WorkspaceRegionContext.entity_detail_urls` (entity → detail URL, honouring
`drill: none` and `action:`), demoted request-time by
`gate_edit_path_drill_map_for_principal` (EDIT path → VIEW when UPDATE is
denied, cycle 1409).

**Render.** `TaskInboxItem` / `TaskInboxSummaryChip` / `TaskInboxRegion`
primitives, `_BuildersTimelineMixin._build_task_inbox`,
`_RenderDashboardMixin._emit_task_inbox_region` and the ingest seam copy
`TaskInbox` + `render_task_inbox` (dual-locked to HM
`contracts/task_inbox.py`; re-add its `CONTRACT_MODELS` row and move it out of
`DOM_ONLY_DEFERRED`). Drill anchors carried `data-dz-task-inbox-drill` plus the
`data-dz-open-*` discovery attrs (cycle 1617).

**Fix on restore, do not copy.** `order:` was parsed and stored but never
applied: items rendered in source-declaration order. A restore either sorts by
the declared keys or drops the clause; it must not ship a dead clause again.

**Counter-priors.** Do not resolve the fan-out with one SQL `UNION` across
entities: per-source RBAC scoping is the point. Do not let a template string
reach the DOM unescaped.

## Reopen when (consumer force)

1. **Named consumer** — a consumer workspace needs one landing list of due
   actions drawn from two or more entities, and one `queue` region per source
   (the replacement AegisMark chose) is rejected by its users or its
   assurance pack.
2. **Evidence** — the consumer's DSL or issue shows the per-source queues, or
   a hand-written route merging entities into one list.
3. **Acceptance** — one region lists items from two entities, each source
   scoped by its own `scope:` rules, with drill links that respect UPDATE.

## Already shipped (do not re-litigate)

- `queue`, `status_list`, `metrics` and `list` regions cover single-source
  work piles (`docs/guides/story-to-composition.md`).
- The HM `task-inbox` Hyperpart and its CSS stay in `packages/hatchi-maxchi/`.
- `{{ field.path | transform }}` card templates live on in `day_timeline`
  (`_interpolate_card_template`).

## Explicitly out of scope until force

- Cross-entity sort keys beyond `urgency` and one temporal field.
- Chip drill URLs (chips rendered without a link in the archived runtime).

## Trail

| Date | Event |
|------|--------|
| 2026-10-16 | AegisMark fb673bc8 dropped its last `display: task_inbox`; operator cut the mode; parked (this DD) |
