# Lane: framework-ux

Brings Dazzle's UX layer under ux-architect governance one component at a time, and verifies via agent-led QA against example apps. Adapted from former /ux-cycle.

## Targets

Dazzle framework's UI templates, contracts, fitness walks. **Not** example-app DSL — that's `example-apps` lane.

## State

- **Backlog section:** `## Lane: framework-ux` in `dev_docs/improve-backlog.md`
- **Component contracts:** `~/.claude/skills/ux-architect/components/<component>.md`
- **Gap docs:** `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md`
- **Run state:** `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/` (gitignored)

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `ux-component-shipped` | After QA PASS — payload `{component, outcome}` |
| Emit | `ux-regression` | A previously-DONE row went FAIL |
| Emit | `ux-gap-analysis` | Synthesis cycle wrote gap doc(s) — payload `{cycle, themes_count, theme_slugs}` |
| Emit | `ux-investigation-complete` | finding_investigation cycle ran — payload `{cycle, ex_id, outcome}` |
| Consume | `trial-friction` | Treat as candidate for SPECIFY (qualitative friction may need a contract) |
| Consume | `dazzle-updated` / `fix-deployed` | Mark affected backlog rows for re-verification |

## actionable_count

Rows in `## Lane: framework-ux` section with status ∈ {`REGRESSION`, `PENDING`, `IN_PROGRESS`, `READY_FOR_QA`} **OR** `qa: PENDING` **OR** `contract: DRAFT`.

## Force sub-strategies

| Arguments | Playbook |
|-----------|----------|
| `framework-ux hyperpart_presentation` | `improve/strategies/hyperpart_presentation.md` — role×host matrix + `present()`; residual `ref_as_repr` / `person_as_text` |

## Leftover-honesty classes (do not walk siblings)

**Commit contract (oral #127):** leftover-honest *token stay-put* is cadence-capped
(`python scripts/improve_commit_contract.py --status`). Subject names the
clerk-visible lie, not `leftover-honest <param>`. Body has `Before:` /
`After:` / `Live:`. Do not resume the 2237–2250 param walk.

- **Parse-invent** (widget companions) is saturated — oral #42.
- **Temporal echo** (`include_closed` / `as_of` on list/grid `hx-get`)
  is saturated — oral #67. Helper:
  `leftover_honest_temporal_query`. Do **not** ship another
  "must ride hx-get" sibling. If a new chrome control is added,
  call the helper in that control's ship.
- **Catalog leftover** (unknown picker id invents first sibling)
  is saturated — oral #69. Helper: `leftover_honest_catalog_id`.
- **Date-window leftover** (`date_from` / `date_to` invents empty)
  opened cycle 2186 (oral #70). Helper:
  `leftover_honest_iso_date`. Do **not** walk another bound site.
- **Entity-id leftover** (`?context_id=` / `?id=` invent empty)
  closed cycle 2189 (oral #71 one-ship close). Helper:
  `leftover_honest_entity_id`. Do **not** walk another entity-id
  query param.
- **Filter-enum fetch leftover** (`?filter_<enum>=junk` invents empty)
  closed cycle 2190 (oral #72). Fetch now reuses picker honesty
  (`compute_filter_columns_and_active`). Do **not** walk another
  `filter_<enum>` fetch site.
- **Workspace/REST leftover sort** (`?sort=zzz` invents empty)
  closed cycle 2191 (oral #73). Helper: `leftover_honest_sort` /
  `_parse_list_sort`. Do **not** walk another FastAPI sort site.
- **REST leftover filter[key]** (`?filter[zzz]=` invents empty)
  closed cycle 2193 (oral #74). Helper:
  `leftover_honest_list_filters` / `_parse_list_filters`. Do
  **not** walk another GET list `filter[key]` parse. Bulk echo
  stays fail-closed (mutation).
- **REST leftover filter VALUE** (`?filter[status]=zzz` invents
  empty) closed cycle 2194 (oral #75). Helper:
  `_parse_list_filter_enum_values` /
  `entity_enum_filter_options`. Do **not** walk another GET
  list filter-enum value site. Bulk echo stays fail-closed
  (mutation).
- **REST leftover filter[id] VALUE** (`?filter[id]=zzz` invents
  empty) closed cycle 2195 (oral #76). Helper:
  `leftover_honest_entity_id` / `entity_id_filter_fields`.
  Do **not** walk another GET list entity-id filter value
  site. Bulk echo stays fail-closed (mutation).
- **REST leftover filter date VALUE** (`?filter[created_at]=zzz`
  invents empty) closed cycle 2196 (oral #77). Helper:
  `leftover_honest_iso_date` / `entity_date_filter_fields`.
  Do **not** walk another GET list date / datetime filter
  value site. Bulk echo stays fail-closed (mutation).
- **REST leftover filter bool VALUE** (`?filter[is_active]=zzz`
  invents empty / inactive) closed cycle 2197 (oral #78).
  Helper: `leftover_honest_filter_bool` /
  `entity_bool_filter_fields`. Do **not** walk another GET
  list bool filter value site. Bulk echo stays fail-closed
  (mutation).
- **REST leftover filter int VALUE** (`?filter[amount]=zzz`
  invents empty / zero) closed cycle 2198 (oral #79).
  Helper: `leftover_honest_filter_int` /
  `entity_int_filter_fields`. Do **not** walk another GET
  list numeric filter value site. Bulk echo stays fail-closed
  (mutation).
- **REST leftover filter email VALUE** (`?filter[email]=zzz`
  invents empty) closed cycle 2199 (oral #80). Helper:
  `leftover_honest_filter_email` /
  `entity_email_filter_fields`. Do **not** walk another GET
  list email filter value site.
- **REST leftover filter url VALUE** (`?filter[preview_url]=zzz`
  invents empty) closed cycle 2200 (oral #81). Helper:
  `leftover_honest_filter_url` /
  `entity_url_filter_fields`. Do **not** walk another GET
  list url filter value site.
- **REST leftover filter slug VALUE** (`?filter[slug]=ab` /
  `?filter[slug]=ZZZ` invent empty) closed cycle 2201
  (oral #82). Helper: `leftover_honest_filter_slug` /
  `entity_slug_filter_fields` (reuses `validate_slug`).
  `zzz` / `ghost` are valid slugs and ride. Do **not** walk
  another GET list slug filter value site.
- **REST leftover filter file VALUE** (`?filter[file]=zzz`
  invents empty) closed cycle 2202 (oral #83). Helper:
  `leftover_honest_filter_file` / `entity_file_filter_fields`
  (reuses `leftover_honest_entity_id` +
  `leftover_honest_filter_url`). Do **not** walk another GET
  list file filter value site.
- **GET list leftover typed filter VALUES** closed cycle 2203
  (oral #85). Do **not** walk another GET list field kind.
- **Bulk leftover filter VALUE** (`filter[status]=zzz` on
  all-matching echo invents empty mutation) closed cycle 2206
  (oral #86). Helper: `leftover_honest_list_filters` on the
  echo. Unknown keys stay 422. Do **not** walk another bulk
  leftover filter kind.
- **Experience leftover event** (`?event=zzz` invents terminal
  completion) closed cycle 2207 (oral #87). Helper:
  `leftover_honest_experience_event`. Leftover stays put.
  Do **not** walk another experience `?event=` site.
- **Onboarding leftover guide/step** (`/api/onboarding/zzz/ghost`
  invents completed/dismissed rows) closed cycle 2208 (oral #88).
  Helper: `leftover_honest_onboarding_step`. Leftover stays put
  (404, no write). Do **not** walk another onboarding
  complete/dismiss site.
- **Membership leftover roles** (`roles=zzz` invents undeclared
  persona grants) closed cycle 2209 (oral #89). Helper:
  `leftover_honest_persona_roles`. Leftover omitted; all leftover
  stays put (400, no write). Do **not** walk another invite /
  members-roles leftover persona.
- **Consent leftover tokens** (`analytics=zzz` invents granted
  via `bool(nonempty)`) closed cycle 2210 (oral #90). Helper:
  `leftover_honest_consent_bool`. Leftover stays put (400, no
  cookie). Do **not** walk another consent coerce site.
- **Join-policy leftover tokens** (`domain_join_policy=zzz`
  invents `admin_approval`) closed cycle 2212 (oral #91).
  Helper: `leftover_honest_join_policy`. Leftover stays put
  (400, no write). Do **not** walk another join-policy
  coerce site.
- **2FA leftover mode** (`?mode=zzz` invents `totp`) closed
  cycle 2215 (oral #92). Helper: `leftover_honest_2fa_mode`.
  Leftover stays put (400, no invented totp). Do **not** walk
  another 2FA challenge/verify leftover mode.
- **Auth leftover error** (`?error=zzz` invents a clean page)
  closed cycle 2221 (oral #95). Helper:
  `leftover_honest_auth_error`. Leftover stays put (400, no
  invented clean form). Do **not** walk another `?error=`
  banner site.
- **Auth leftover next** (`?next=zzz` invents the default
  landing) closed cycle 2222 (oral #96). Helper:
  `leftover_honest_auth_next`. Leftover stays put (400, no
  invented clean form / landing). POST leftover next stays
  fail-closed to `/app`. Do **not** walk another `?next=`
  landing site.
- **Connections leftover new** (`?new=zzz` invents a clean
  list) closed cycle 2223 (oral #97). Helper:
  `leftover_honest_connection_new` (reuses
  `leftover_honest_auth_error`). Leftover stays put (400, no
  invented chooser / form). Do **not** walk another `?new=`
  form-opener site.
- **Auth leftover urlsafe token** (`?token=zzz` / `?session=zzz`
  invents reset / 2FA form theater) closed cycle 2224 (oral #98).
  Helper: `leftover_honest_auth_token`. Leftover stays put
  (400, no invented form). Do **not** walk another urlsafe
  token echo site.
- **SCIM leftover filter** (`?filter=zzz` invents the unfiltered
  Groups/Users list) closed cycle 2227 (oral #99). Helper:
  `leftover_honest_scim_eq_value`. Leftover stays put (400
  `invalidFilter`). Do **not** walk another SCIM `?filter=`
  list site.
- **SCIM leftover active** (`active: "zzz"` invents inactive
  via `bool(None)`; leftover PATCH invents a 200 no-op)
  closed cycle 2228 (oral #100). Helper:
  `leftover_honest_scim_active`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM `active`
  body site.
- **SCIM leftover members** (`members: "zzz"` invents a wipe /
  empty group) closed cycle 2229 (oral #101). Helper:
  `leftover_honest_scim_member_ids`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM `members`
  body site.
- **SCIM leftover userName / emails** (`userName: "zzz"` /
  `emails: "zzz"` invents a 500 crash or a provision attempt)
  closed cycle 2230 (oral #102). Helper:
  `leftover_honest_scim_username`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM `userName`
  / `emails` body site.
- **SCIM leftover Operations** (`Operations: "zzz"` invents a
  500 crash on Users PATCH / a 200 no-op on Groups PATCH)
  closed cycle 2231 (oral #103). Helper:
  `leftover_honest_scim_operations`. Leftover stays put (400
  `invalidSyntax`). Do **not** walk another SCIM PATCH
  `Operations` site.
- **SCIM leftover displayName** (`displayName: ["zzz"]` invents
  a group persist; leftover PATCH invents a `str()` rename)
  closed cycle 2232 (oral #104). Helper:
  `leftover_honest_scim_display_name`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM `displayName`
  body site.
- **Auth leftover email** (`email=zzz` invents `/login/sent` /
  `/forgot-password/sent` / invite persist / host-pinned IdP)
  closed cycle 2233 (oral #105). Helper:
  `leftover_honest_auth_email` / `leftover_auth_email_or_400`.
  Leftover stays put (400). Do **not** walk another identity-
  email site.
- **Org leftover membership_id** (`membership_id=zzz` invents
  `303 /auth/select-org?error=invalid_org`) closed cycle 2237
  (oral #107). Helper: `leftover_honest_membership_id` /
  `leftover_membership_or_400`. Leftover stays put (400).
  Do **not** walk another select/switch-org leftover
  membership_id site.
- **2FA leftover code** (`code=zzz` invents
  `303 /2fa/challenge?error=invalid_code`) closed cycle 2238
  (oral #108). Helper: `leftover_honest_2fa_code` /
  `leftover_2fa_code_or_400`. Leftover stays put (400).
  Do **not** walk another 2FA verify/setup leftover code.
- **Auth leftover consume token** (`/auth/magic/zzz` invents
  `303 /auth/login?error=invalid_magic_link`; leftover reset
  invents `?error=invalid`; leftover verify-email invents
  `verified=error`; leftover accept-invite invents the
  invalid-or-used page) closed cycle 2239 (oral #109). Helper:
  `leftover_honest_auth_token`. Leftover stays put (400).
  Do **not** walk another magic / reset / verify / invite
  consume site.
- **SSO leftover connection id** (`?connection=zzz` invents
  `303 /login?error=sso_no_connection`; leftover metadata
  invents app-level XML) closed cycle 2240 (oral #110).
  Helper: `leftover_honest_connection_id`. Leftover stays put (400).
  Do **not** walk another enterprise/SAML leftover
  `?connection=` site.
- **SCIM leftover externalId** (`externalId: ["zzz"]` invents a
  500 / persist; leftover PATCH invents a 200 no-op) closed
  cycle 2241 (oral #111). Helper:
  `leftover_honest_scim_external_id`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM `externalId`
  body site.
- **SSO leftover provider** (`/auth/sso/zzz` invents
  `303 /login?error=sso_provider_unknown`) closed cycle 2242
  (oral #112). Helper: `leftover_honest_sso_provider`.
  Leftover stays put (400).
  Do **not** walk another leftover `/auth/sso/{provider}` slug.
- **OAuth leftover code** (`?code=zzz` / `?state=zzz` invents
  `303 /login?error=sso_failed`) closed cycle 2243
  (oral #113). Helper: `leftover_honest_oauth_code`.
  Leftover stays put (400).
  Do **not** walk another leftover `?code=` / `?state=`
  callback site.
- **SCIM leftover schemas** (`schemas: "zzz"` invents a
  provision; leftover PATCH invents a 200 no-op / write)
  closed cycle 2244 (oral #114). Helper:
  `leftover_honest_scim_schemas`. Leftover stays put (400
  `invalidSyntax`). Do **not** walk another SCIM `schemas`
  envelope site.
- **SCIM leftover User.groups** (`groups: "zzz"` invents a
  500 / provision; leftover PATCH invents a 200 no-op)
  closed cycle 2245 (oral #115). Helper:
  `leftover_honest_scim_groups`. Leftover stays put (400
  `invalidValue`). Do **not** walk another SCIM User
  `groups` body site.
- **SCIM leftover PatchOp op** (`op: "zzz"` invents a 200
  no-op) closed cycle 2246 (oral #116). Helper:
  `leftover_honest_scim_patch_op`. Leftover stays put (400
  `invalidSyntax`). Do **not** walk another SCIM PATCH
  leftover `op` site.
- **Search leftover entity** (`?entity=zzz` invents the
  unfiltered fleet) closed cycle 2247 (oral #117). Helper:
  `leftover_honest_search_entity` (reuses
  `leftover_honest_auth_error`). Leftover stays put (400).
  Do **not** walk another leftover `?entity=` fleet-restrict.
- **Fragment leftover source** (`?source=zzz` invents 200
  empty-result theater) closed cycle 2248 (oral #118). Helper:
  `leftover_honest_fragment_source` (reuses
  `leftover_honest_auth_error`). Leftover stays put (400).
  Do **not** walk another leftover `?source=` empty-result
  theater site.
- **Connection leftover group_map** (`group_map=zzz` invents a
  persist) closed cycle 2249 (oral #119). Helper:
  `leftover_honest_group_map`. Leftover stays put (400, no
  write). Do **not** walk another leftover `group_map`
  persist site.
- **File leftover entity** (`?entity=zzz` invents a file-metadata
  persist; leftover GET invents an empty list) closed cycle 2250
  (oral #120). Helper: `leftover_honest_file_entity` (reuses
  `leftover_honest_auth_error`). Leftover stays put (400, no
  write). Do **not** walk another leftover file `?entity=`
  persist site.
- **CSV money / dict invent** (`?format=csv` ships `1200` pence
  as pounds / `str(dict)` chrome) closed cycle 2253 (oral #122).
  Helper: `_csv_cell` + `format_cell`. Leftover currency junk
  stays put. Do **not** walk another leftover-token stay-put
  as the default mutation (oral #121).
- **Timeago future-as-just-now** (queue/card/kanban `type=date`
  invents `just now` for tomorrow) closed cycle 2254 (oral
  #123). Helper: `_timeago_filter` + format_cell `_relative`.
  Do **not** walk another leftover-token stay-put or CSV
  money/dict clone (oral #121/#122).
- **Timeago naive-UTC elapsed** (datetime vs wall ``now()`` invents
  extra age) closed cycle 2255 (oral #124).
- **Workspace today unbound** (`due_date < today` dropped — past-due
  queues / KPIs / attention invent unbounded / whole-book / on-time)
  closed cycle 2256 (oral #125). Helper: `evaluate_date_expr`. Do
  **not** walk another leftover-token stay-put, CSV money clone, or
  timeago (oral #121–#124).
- **CSV datetime naive-UTC** (`?format=csv` dumps `2026-08-18 14:30:00`
  as wall time) closed cycle 2257 (oral #126). Helper: `_csv_cell` +
  `format_cell` date/datetime. Leftover junk stays put. Do **not**
  walk another leftover-token stay-put, CSV money clone, timeago, or
  workspace-today (oral #121–#125).
- **Related file_list uploader-as-title** (first two entity columns
  titled the FK, not ``filename``) closed cycle 2271 (oral #139).
  Helper: `related_file_name_and_meta` / `format_byte_size`. Leftover
  ``zzz`` filenames stay put. Do **not** walk remaining file_list
  identity siblings.
- **Related queue sequence-as-title** (first column ``attempt_number``
  titled ``1``, hid ``card_declined``) closed cycle 2272 (oral #140).
  Helper: `related_queue_title_and_meta` / `is_sequence_title_key`.
  Leftover ``zzz`` reasons stay put. Do **not** walk remaining
  attempt/count/quantity title siblings.
- **Related salary reason-as-title** (DSL ``amount`` missed
  ``amount_minor``, titled ``annual_review``) closed cycle 2273
  (oral #141). Helper: `_related_proj_index` / bare ``reason``
  chrome. Leftover ``zzz`` stays put. Do **not** walk remaining
  related money-projection or generic-reason title siblings.
- **Conversation clock month-fragment** (friendly
  ``16 Jul 2026 15:30`` titled ``Jul 2``) closed cycle 2274
  (oral #142). Helper: `conversation_time_label`. Leftover
  ``zzz`` stays put. Do **not** walk remaining clock-slice
  siblings.
- **Timeline datetime rail skipped** (``logged_at`` typed
  ``datetime`` hid when) closed cycle 2275 (oral #143).
  Helper: `_timeline_when_col_key`. Leftover ``zzz`` stays
  put. Do **not** walk remaining date-vs-datetime rail
  siblings.
- **Funnel/progress snake_case stages** (``in_progress`` as
  the chip) closed cycle 2276 (oral #144). Helper:
  `clerk_stage_label`. Leftover ``zzz`` stays put. Do **not**
  walk remaining conversion-chip siblings.
- **Workspace bool FilterBar true/false** (Favorite dumped
  ``true``) closed cycle 2278 (oral #146). Helper:
  `bool_filter_options`. Query values stay ``true``/``false``.
  Leftover ``zzz`` stays put. Do **not** walk remaining bool
  filter-label siblings.
- **Workspace enum FilterBar snake_case** (``in_progress`` as
  the option) closed cycle 2279 (oral #147). Helper:
  `enum_filter_options`. Query values stay schema tokens.
  Leftover ``zzz`` stays put. Do **not** walk remaining enum
  filter-label siblings.
- **Stacked area legend snake_case** (``in_progress`` /
  ``critical`` as the series name) closed cycle 2280
  (oral #148). Helper: `_clerk_series_dim_label` /
  `clerk_stage_label`. FK ``_label`` rides. Leftover
  ``zzz`` stays put. Do **not** walk remaining chart
  legend/axis token siblings.
- **Comparison whole-count 12.00** (ranked ``12.0`` dumped
  ``12.00``) closed cycle 2285 (oral #153). Helper:
  `_fmt_num`. Leftover ``zzz`` labels stay put. Do **not**
  walk remaining two-decimal count siblings.
- **Measure unit suffix dropped** (``response_time_ms`` dumped
  ``340`` while bar_track already said ``340ms``) closed cycle
  2286 (oral #154). Helper: `clerk_measure_display` /
  `clerk_measure_suffix`. Leftover ``zzz`` stays put. Do
  **not** walk remaining ``*_ms`` / ``*_seconds`` sites.
- **Percent-points rate dumped unitless** (``error_rate`` dumped
  ``2.40``) closed cycle 2288 (oral #155). Helper:
  `clerk_percent_points_display`. Leftover ``zzz`` stays put.
  Do **not** walk remaining percent-points cells.
- **Queue datetime storage ISO** (``triggered_at`` dumped
  ``2026-05-18 14:30:00+00:00`` on meta while date columns
  already timeago) closed cycle 2290 (oral #156). Helper:
  `_QUEUE_WHEN_COL_TYPES` + `_timeago_filter`. Leftover
  ``zzz`` stays put. Do **not** walk remaining queue
  datetime siblings.
- **Entity-card schema dump** (halo/flags dumped
  ``acknowledged_by`` / ``active``) closed cycle 2291
  (oral #157). Helper: `clerk_entity_card_field_label` /
  `clerk_entity_card_field_display`. Leftover ``zzz`` stays
  put. Do **not** walk remaining halo/flags schema-key
  siblings.
- **Entity-card stamps omitted chrono** (history dropped when
  `fields` empty while `triggered_at` existed) closed cycle
  2293 (oral #159). Helper: `clerk_stamp_chrono_fields`.
  Leftover ``zzz`` stays put. Do **not** walk remaining
  stamps field-list siblings.
- **Tree group_by scalar flat list** (`batch_number` treated as
  a parent FK so every device was a root) closed cycle 2297
  (oral #163). Helper: `compute_tree` grouping folders.
  Parent-ref trees stay nested. Leftover ``zzz`` stays a
  group label. Do **not** restyle remaining ops_dashboard
  widget formatters (oral #150–#162) or walk leftover-token
  stay-put.
- **Tabbed list group_by empty tabs** (``group_by: status``
  dumped "No tabs" because only multi-source ``source_tabs``
  were wired) closed cycle 2298 (oral #164). Helper:
  `compute_tabbed_slices`. Leftover ``zzz`` stays a tab.
  Multi-source shells still own source_tabs. Do **not**
  restyle remaining tree group_by siblings (oral #163) or
  remaining ops_dashboard widget formatters.
- **Progress group_by empty stages** (``group_by: status``
  dumped "No progress" because only authored ``stages:``
  were wired) closed cycle 2299 (oral #165). Helper:
  `infer_progress_stages`. Leftover ``zzz`` stays a chip.
  Authored ``stages:`` still win. Do **not** restyle remaining
  tabbed_list/tree group_by siblings or remaining ops_dashboard
  widget formatters.
- **Diagram empty ER** (``display: diagram`` dumped
  "No entity relationships" because the HTTP typed path never
  forwarded AppSpec Mermaid) closed cycle 2300 (oral #166).
  Helper: `compute_diagram_data`. Leftover ``zzz`` is not an
  entity. Do **not** restyle remaining progress/tabbed_list/tree
  group_by siblings or remaining ops_dashboard widget formatters.
- **Map empty pins** (``display: map`` dumped empty chrome because
  MAP was missing from ``_TYPED_REGION_DISPLAYS``) closed cycle
  2301 (oral #167). Helper: list family + `_apply_conversation_list_ctx`.
  Leftover ``zzz`` stays a pin. Do **not** restyle remaining
  diagram ER siblings.
- **Accordion empty FAQ** (``display: accordion`` dumped empty
  chrome because ACCORDION was missing from the typed HTTP
  whitelist) closed cycle 2302 (oral #168). Helper: list family
  + bodyless allowlist. Leftover ``zzz`` stays a panel.
  Same-ship close of remaining sourceless hyperpart emitters
  (carousel / progress_bar). Do **not** walk remaining map pin
  siblings or remaining whitelist dumps one-per-cycle.
- **Kanban FK group_by empty board** (``group_by: assigned_to``
  dumped empty people columns) closed cycle 2303 (oral #169).
- **Workspace file UUID cell** (timeline/queue dumped storage
  UUID) closed cycle 2304 (oral #170). Helper:
  `clerk_file_cell_display`. Leftover ``zzz`` stays put.
- **List/queue tags comma blob** closed cycle 2305 (oral #171).
  Helper: `clerk_tags_cell_html`. Leftover ``zzz`` stays a chip.
- **List/queue rating bare integer** (``4`` while the form is a
  1–5 slider) closed cycle 2306 (oral #172). Helper:
  `clerk_rating_cell_html` / `clerk_rating_display`. Leftover
  ``zzz`` stays put. Do **not** map generic ``*_score``.
- **List/queue email/phone dead text** (mailbox / ``+44 20 7946
  0936`` as truncated strings while SPEC asks for tappable
  channels) closed cycle 2307 (oral #173). Helper:
  `clerk_email_cell_html` / `clerk_phone_cell_html`. Leftover
  ``zzz`` stays put. Do **not** map generic URL fields.
- **List/queue temperature unitless decimal** closed cycle 2308
  (oral #174). Helper: `clerk_temperature_display`. Leftover
  ``zzz`` stays put. Do **not** map generic decimals or remaining
  ``duration_minutes`` measure cells (oral #154).
- **List/queue INT cents raw pence** closed cycle 2309 (oral
  #175). Helper: `is_money_field_name` + INT → currency. Leftover
  ``zzz`` stays put. Do **not** map decimal majors.
- **List/queue IBAN ungrouped blob** closed cycle 2310 (oral
  #176). Helper: `clerk_iban_display`. Leftover ``zzz`` stays
  put. Do **not** group remaining sort codes / account numbers.
- **Audit-history ISO / snake_case dump** closed cycle 2313
  (oral #179). Helper: `clerk_audit_*`. Leftover ``zzz`` stays
  put. Do **not** join remaining actor UUIDs or restyle remaining
  money/IBAN before/after values. Do **not** restyle remaining
  group_by-empty / typed list-cell dumps (oral #163–#178).
- **Conversation channel schema-token dump** closed cycle 2315
  (oral #181). Helper: `conversation_channel_label` /
  `clerk_stage_label`. Leftover ``zzz`` stays put. Do **not**
  restyle remaining bubble bodies or remaining ops_dashboard
  widget formatters. Workspace + related emit sites closed in
  one ship.
- **List find-by schema-key dump** closed cycle 2316 (oral
  #182). Helper: `clerk_list_search_field_label`. Leftover
  ``zzz`` stays put. Do **not** restyle remaining FTS snippet
  bodies or JSON API keys. Empty invents no chrome.
- **Related-tab FK schema-key dump** closed cycle 2317 (oral
  #183). Helper: `clerk_related_tab_fk_label`. Leftover
  ``zzz`` stays put. Do **not** restyle remaining open-via hop
  labels or remaining list find-by chrome siblings. Empty
  invents no suffix.
- **Carousel chip schema-token dump** closed cycle 2318 (oral
  #184). Helper: ``clerk_carousel_chip_label``. Leftover
  ``zzz`` stays put. Do **not** restyle remaining open-via hop
  labels or remaining related-tab FK siblings.
- **Bar-chart bool True/False** closed cycle 2319 (oral #185).
  Helper: ``clerk_stage_label`` true/false strings + bar-chart
  emit. Leftover ``zzz`` stays put. Do **not** restyle remaining
  chart legend snake_case siblings (oral #148) or remaining
  carousel chip siblings.
- Presentation MCP STALE (1554) is still a valid mutation.
  Not Goal B coat.
- Field note: `improve/leftover-honesty-ethnography.md`.

**Probe / MCP (presentation residual from product_quality or presentation tool):**

```bash
dazzle demo quality -p examples --json
# MCP: product_quality(score) · presentation(cognition|opportunities|residual)
# Force when presentation residual > 0: /improve framework-ux hyperpart_presentation
```

## Playbook

### 1. OBSERVE

Pick highest-priority row from the lane's section using this order:
1. Any `REGRESSION` row (highest)
2. `PENDING` rows where `contract: MISSING` and `impl: PENDING` (new work)
3. `PENDING` rows where `contract: DRAFT` (in-progress work)
4. `DONE` rows where `qa: PENDING` (verification)
5. `VERIFIED` rows (lowest — re-verification)

If no rows match → run **explore phase** (Step 6 below).

Mark selected row `IN_PROGRESS`, update `last_cycle`, increment `attempts`. If `attempts > 3` → mark `BLOCKED`, pick next row.

### 2. SPECIFY (only if contract is MISSING or DRAFT)

Invoke the `ux-architect` skill. Save contract to `~/.claude/skills/ux-architect/components/<component>.md` per the contract template at `~/.claude/skills/ux-architect/templates/component-contract.md`. Update row's `contract` to `DONE`.

Skip if contract is already `DONE`.

### 3. REFACTOR (only if impl is PENDING or PARTIAL)

Apply contract to Dazzle code. Typical files:
- `src/dazzle/render/fragment/...` (the typed Fragment substrate — THE universal render path per ADR-0049) + `src/dazzle/page/runtime/static/css/` (`dz.css`, `dz-tones.css`, `dz-widgets.css`, `dazzle-layer.css`) — Fragment renderers + the HM semantic `dz-*` class / design-token layer (no Jinja2 since #1042/ADR-0023)
- `src/dazzle/page/runtime/static/js/dz-utils.js` + `.../js/islands/` — HM delegated vanilla controllers (haptics, toast, row-action, island controllers) aligning with the contract's state grammar (Alpine REMOVED in Tier F4e — never author `x-*` attributes)
- Backend endpoints for new server APIs
- `src/dazzle/page/converters/template_compiler.py` — new context fields

Follow the ratified UI invariants (AGENTS.md "UI Invariants" + `docs/reference/taste.md`): the HM Hyperpart idiom — delegated document-level vanilla controllers, state in the DOM (attributes/`.checked`/`aria-*`), server-owned rendering; semantic `dz-*` classes; `[data-dz-variant]`/`[data-dz-size]` for buttons. Never author `x-data`/`@click`/`x-show` (the morph path strips Alpine-applied classes).

Update row's `impl` to `DONE`.

### 4. QA

Two-phase against the row's `canonical` example plus one rotating sample from `applies`.

**Phase A — HTTP contracts (fast):**
```bash
cd examples/<canonical> && dazzle ux verify --contracts
```
If fails → mark `qa: FAIL`, note failures, skip Phase B.

**Phase B — Fitness-engine contract walk (slow, only if Phase A passed AND contract has quality gates):**

Routes through the fitness engine. `ModeRunner` owns subprocess lifecycle:

```python
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import run_fitness_strategy
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

example_root = Path("/Volumes/SSD/Dazzle/examples/<canonical>")
contract_path = Path.home() / ".claude/skills/ux-architect/components/<component>.md"

async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=example_root,
    personas=["admin", "agent", "customer"],   # or None for anonymous components
    db_policy="preserve",
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        example_root=example_root,
        component_contract_path=contract_path,
        personas=["admin", "agent", "customer"],
    )
```

The fitness engine's Pass 1 parses the contract and calls `walk_contract` — one ledger step per quality gate.

`outcome.degraded` rules:
- `False` → `qa: PASS`
- `True` with at least one persona → `qa: FAIL`
- Strategy raises (subprocess never started) → `qa: BLOCKED`

`outcome.findings_count` is **NOT** used for qa pass/fail (cycle 156 fix). It's Pass 2a story_drift / spec_stale / lifecycle observations from the example app's overall spec/story coherence — orthogonal to whether the widget contract walked correctly.

### 5. REPORT (lane-internal — driver also writes a top-level entry)

1. Update row in lane backlog section with new status, contract/impl/qa, notes (include git SHA of any commits this cycle).
2. If QA passed → move to `DONE`. If was already `DONE` and re-verified → `VERIFIED`.
3. Return outcome to driver: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit, budget_consumed: 0}`

### 6. EXPLORE (when no actionable rows in Step 1)

Choose one of seven sub-strategies based on accumulated state. Pick by judgment, not strict rotation.

#### Sub-strategy: missing_contracts

Scan for recurring UX patterns lacking a contract. Proposal-heavy. Use when (a) recently-touched template family may contain uncontracted components, or (b) >3 cycles since last `missing_contracts`.

Substrate: dispatches a subagent (subagent-dispatch; judgment work runs at the session tier per model-tiering; on Claude Code: a `general-purpose` Task-tool agent with no `model` override) using the playbook in `improve/strategies/explore-subagent.md`. Findings go to per-run findings.json then ingested into the lane backlog as `PROP-NNN` proposals.

#### Sub-strategy: edge_cases

Probe friction, broken-state recovery, empty/error handling, dead-end navigation, affordance mismatches. Observation-heavy. Use when (a) persona/app axis hasn't been probed yet, or (b) recent framework fix needs cross-app regression evidence.

Same subagent substrate as `missing_contracts`. Findings go to lane backlog as `EX-NNN` observations.

#### Sub-strategy: contract_audit

**No browser, no subagent.** Pick a known-templated-but-ungoverned component and formalise it in one cycle:
1. HTTP-reproduce current rendering via `dazzle serve`
2. Grep every call site
3. Build contract at `~/.claude/skills/ux-architect/components/<name>.md` with quality gates mirroring canonical shape
4. Fix any drift across every call site in one commit (design-token migration, DaisyUI removal, canonical class markers, ARIA hooks)
5. Regression tests for each quality gate
6. Cross-app verification

Use when a templated component has cross-cutting drift that will snowball if not consolidated.

#### Sub-strategy: framework_gap_analysis

**No browser, no subagent — pure reasoning cycle.** Read accumulated EX-NNN observations since last analysis, group by defect-class, identify themes where 2+ observations point at the same gap. Write `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md` per:

- **Problem statement** — generalisable defect class, framework-first not app-first
- **Evidence** — EX-NNN rows + GitHub issues, one-line each
- **Root cause hypothesis** — file paths if identifiable
- **Fix sketch** — concrete proposal that addresses all contributing observations
- **Blast radius** — affected apps/personas
- **Open questions** — what needs verification before fix is safe

Use when 3+ cross-cycle observations point at same theme, OR you want to consolidate evidence before escalating to a GitHub issue, OR >7 cycles since last analysis.

Counts against shared explore budget.

#### Sub-strategy: finding_investigation

**No subagent, but you may use your own tools to reproduce and root-cause.** Pick one OPEN EX-NNN row (prefer severity=concerning, prefer cross-cycle reinforcement):

1. Reproduce the defect locally — boot relevant example app, isolate conditions
2. Trace to framework code (Grep/Read), starting from symptom's most-likely call site
3. Either file a GitHub issue with code-level evidence OR propose a fix directly if small
4. Update EX row's status: `OPEN` → `FILED→#NNN` / `FIXED_LOCALLY` / `VERIFIED_FALSE_POSITIVE`

Counts against shared explore budget.

**HEURISTIC 1 (mandatory): Try the real thing first.** Before writing fix code OR committing to a gap doc's framework infrastructure, reproduce the defect end-to-end at the lowest layer that can exhibit it. Track record: 4 of last 6 investigations had the hypothesised framework fix turn out to be unnecessary or wrong.

**HEURISTIC 2: Helper-audit propagation.** When fixing a single-source-of-truth helper miss, grep for other call sites before writing the fix.

**HEURISTIC 3: Cross-app verification.** Any framework-layer fix must be verified against all 5 example apps before commit.

**HEURISTIC 4: Defaults propagation audit.** When a canonical intent declaration exists, trace it from declaration through resolver to every consumer. Missing propagation is its own defect class.

#### Sub-strategy: api_surface_audit

**No subagent — pure reasoning cycle.** Walk one of the five committed API-surface baselines (DSL constructs, IR types, MCP tools, public helpers, runtime URLs) top-to-bottom asking "is this what we'd design today?". Files findings as `API-NNN` proposals into the framework-ux backlog. Closes the loop on #961 cycle 6 (1.0-prep walkthrough as a recurring exercise).

Use when:
- Last `api_surface_audit` cycle was ≥7 cycles ago
- A `dazzle-updated` signal fired since last audit
- Approaching 1.0 — flip from opportunistic to mandatory weekly cadence

Skip if:
- ≥3 unresolved `API-NNN` rows already open (consolidate before adding more)

Detailed playbook: `improve/strategies/api_surface_audit.md`. Counts against shared explore budget.

#### Sub-strategy: quality_intelligence_sweep

**No subagent — deterministic capability sweep.** Exercises the framework-ux-owned
quality-intelligence capabilities the loop otherwise leaves idle (wired from
`.claude/commands/improve/capability-map.md`, Phase 4). Run against the fleet / a rotating sample:

```bash
dazzle qa taste-panel                 # blind fleet-vs-dialect aesthetic parity (baseline: dev_docs/taste/)
dazzle fitness investigate --top 1    # highest-priority churn×complexity cluster → .dazzle/fitness-proposals/
dazzle fitness vitality               # connectedness / dead-code signal
dazzle sentinel scan                  # DSL sentinel findings (distinct from `sentinel mutate`)
dazzle composition audit              # cross-surface composition/style coherence
```

File real findings as `EX-NNN`/`API-NNN` rows (or a GitHub issue if framework-level).
`taste-panel` regressions vs the baseline are the highest-signal — the blind aesthetic
gate that shipped v0.87→v0.98 and had no lane exercising it. Stamp `last-exercised` for
each capability run in `.claude/commands/improve/capability-map.md`.

Use when: `dazzle-updated` fired since last sweep (new release → re-check aesthetic +
vitality), OR the driver's capability-coverage rule picked framework-ux to exercise a
`STALE`/`UNOWNED` capability, OR ≥7 cycles since last sweep. Counts against shared budget.

### Sub-strategy choosing

When EXPLORE is entered:
1. Scan recent cycle outcomes (last 5 in `improve-log.md`) and OPEN EX row counts by severity
2. List candidates with one-line reason each
3. Pick one and record the choice in the cycle log entry
4. Proceed with that strategy's playbook

Prefer diverse cycles over mechanical rotation. Three `edge_cases` runs in a row is fine if signal keeps converging on interesting framework themes; two back-to-back `framework_gap_analysis` cycles is fine if first surfaced a promising theme.

## Hard rules

- **One row or one strategy per cycle.** Don't chain.
- **Per-phase stagnation check.** If SPECIFY/REFACTOR/QA makes no progress for 3 minutes, abort and mark `BLOCKED`.
- **Never modify rows in DONE/VERIFIED state directly** — let the cycle move them naturally via QA.

## Subagent substrate (for missing_contracts and edge_cases)

EXPLORE runs as a host-harness subagent (subagent-dispatch), NOT as a `DazzleAgent` on the direct SDK. Cognitive work bills to the harness subscription; browser work happens via stateless Playwright helper subprocess.

Detailed playbook: `improve/strategies/explore-subagent.md`. Numbered steps for: init run state directory, boot example app via runner script, poll for readiness, log in as persona, build mission prompt, dispatch the subagent, read findings, tear down runner, ingest results.
