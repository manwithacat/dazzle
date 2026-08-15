# Improve oral history (surfaced)

Lessons the loop learned in practice that used to live only in cycle logs,
capability-map stamps, and operator memory. **Agents should read this** when
picking under residual=0 or when a dig “feels productive but empty.”

Doctrine source of truth remains
`docs/reference/interesting-saas-context.md` and playbooks under
`.claude/commands/improve/strategies/`. This file is the **compressed memory**.

---

## Hard-won facts (2026-07 → 2026-08)

1. **Residual 0 ≠ product done.** When felt residual hits 0, the loop invents
   dual-open / walk / gallery heat and humans feel stagnation while commits
   stay high. Force Goal B depth + stills, or label `harness_only`.

2. **Depth menu becomes fleet-fill monoculture.** Agents apply the same
   `depth_id` across every example with the same recipe (dual attention →
   empty_region prune → Team org desk → composition → headshot shelf). That
   is checklist completion, not interesting software.
   **Counter:** `scripts/interesting_product_portfolio.py` — ban same-depth
   and same-recipe streaks; prefer icon-app stacking.

3. **Stills beat walk green for Goal B.** Recapture hero PNGs same cycle.
   Walk PASS without still change is harness.

4. **Acceptance panels thrash.** Unclear / token limits re-panel the same app
   without product fix. Cap consecutive panels; rotate; seed PENDING with a
   product actuator, not “run panel again.”

5. **Smoke residual goes stale.** Under aggressive campaigns, suppress
   recurring smoke when residual is structure-only stale noise; still dig when
   gross fail/structure residual is real.

6. **Hyperpart shapes residual was high leverage.** Closing
   `scenario_missing` / planned DSL shapes gave agents a rational authoring
   language. Prefer **composed job verbs** (`display: conversation`) over
   three parallel L1 displays. Emitter first when gallery-only; then one
   example home (`scenario_underused`).

7. **require_mutation stops stamp thrash.** Map-only PASS and drained
   dual_lock / hyperpart_coherence queues are not ships. Skip drained queues.

8. **CI in_progress is not FAIL.** Hold product push; self-schedule poll;
   don’t stack Goal B on a red tip.

9. **LFS / empty-hero pointers.** Git LFS still stubs break empty-hero gates —
   untrack pointer stubs or skip them in residual. Recapture real PNGs.

10. **create_all missing columns.** DSL adds fields; SQLite/PG tables lag —
    `ensure_missing_entity_columns` (or equivalent) after create_all is a
    real product-blocker class, not a one-off.

11. **Peer / surprise prompts were underbuilt.** Four prompts in the playbook
    without peer packs → prose filler. Use `improve/peer_packs/*.toml`.

12. **Antagonist score freezes without human cadence.** Recapture packages
    without re-score leave fleet ~5.8 forever. Do not claim category lift.

13. **Capability-map USED stamps encourage thrash.** Sweep is inventory, not
    product progress. Honor top digs; don’t re-stamp hygiene as a ship.

14. **Densify ban is hard.** Isomorphic `*_ops` warehouse desks while
    `densify_allowed=0` is forbidden (#1637). Dig deeper elsewhere.

15. **Explore budget is for edges, not thrash.** Prefer framework non-hop,
    scenario underuse, or peer research when Goal B waves are saturated.

---

16. **Harness distill self-check.** After capability-sweep or self-audit, if the
    map is growing multi-paragraph cycle digests again or Goal B is re-documented
    in three places, stop and re-apply `docs/reference/agent-harness-distill.md`
    criteria — the loop must not re-inflate oral thrash.

17. **Self-audit sample is not `^improve: cycle`.** Modern ships are
    `feat/fix … (cycle N)`. Grepping only the legacy prefix empties the audit
    window while real improve commits sit on HEAD (AUD-011 / cycle 1890). Sample
    `(cycle N)` + `^improve:` + log-named SHAs.

18. **Self-audit cadence is hard preemption.** When ≥15 cycles since
    `lane: self-audit`, run it this cycle — do not arithmetic-defer with
    “next~N” seeds past the due point while CI-poll thrash burns cycles
    (1920→1949 was 29 late). Hand-audit if the workflow Sample agent stalls.

19. **Upgrade + novel recipe tag + floor pin is coat theatre.** After the
    first honest grain (`live_conversation`, one needs-reply ball), agents
    invented synonym recipes (`thankful_needs_reply_trail`, …) and unit
    pins that the slice exists. Saturate the cell and stop. Do not add the
    next AND. Machine: `scripts/goal_b_coat.py` freeze + portfolio family
    collapse. `/improve` picks `example-apps distill` when
    `coat_residual_total>0` (Goal C). Distill lowers FREEZE in the same ship.

20. **fieldtest media grain is two desks.** Issue triage already has critical
    vs high evidence; Device Fleet now has hardware identity (unit photos).
    Do not AND-filter either `photo_url` again — that is coat theatre.
    Peer pack: `improve/peer_packs/fieldtest_hub.toml`.

21. **Goal C subtract is not a prior Goal B lie.** Distill that removes a
    density recipe (`open_decisions`, SLA speech twins) does not REGRESSION
    the earlier interesting_product SHA if that ship’s receipt + pins were
    honest. Audit the distill commit for subtract-only. Do not re-add the
    slice.

22. **fieldtest conversation grain is chrome, not a second list.** After
    `live_conversation` exists, `note_kind=repro` labels the same trail
    (author suffix + danger). Do not add `repro_notes` as a sibling
    `display: conversation` — that is conversation_filter_slice coat
    theatre (oral #19) even if the tag evades the family regex.

23. **hr_records org grain is reporting seat, not another location board.**
    After office/remote + career tracks exist, Unassigned vs Top of House is
    the people-partner hole (who is missing from the tree). Do not AND-filter
    `work_location` again on Reporting. Location coat stays on My Team.

## What not to re-learn

| Anti-pattern | Instead |
|--------------|---------|
| Nth app triple-open as product | `harness_only` or depth menu |
| Same headshot shelf on every CRM | Portfolio ban recipe; different media expression or icon-only media |
| Re-panel until green | Fix product friction or PENDING with actuator |
| Invent residual forever | Accept residual=0; inject Goal B context |
| New example app to “fix depth” | Forbidden by depth menu |
| Metric tile proliferation | Real work rows / regions |

---

## Where the live memory still lives

| Surface | Role |
|---------|------|
| `dev_docs/improve-log.md` | Per-cycle narrative (often local) |
| `.claude/commands/improve/capability-map.md` | Registry table only (Last-exercised); lore not here |
| `.dazzle/improve-digs/*` | Dig receipts (depth_id in notes) |
| `git log --grep='Goal B'` | Tip history of depth waves |
| This file | Distilled rules agents must not rediscover |

When you learn a new durable rule in a dig, **add one bullet here** in the same
ship (or next self-audit). Do not leave it only in a cycle stamp.
