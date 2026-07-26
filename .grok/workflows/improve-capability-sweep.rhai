// Improve multi-agent strategy: capability-sweep
// Re-derive capability inventory, reconcile improve/capability-map.md, report actionable digs.
// Driver still owns: lock, map stamps (unless args.apply), improve-log, self-schedule.
// Cadence: ≥20 cycles or /improve capability-sweep

let meta = #{
    name: "improve-capability-sweep",
    description: "Capability coverage sweep: inventory + parallel class digs (UNOWNED / COGNITION / HYGIENE)",
    when_to_use: "When /improve capability-sweep is due or forced; multi-agent coverage reconciliation",
    phases: [
        #{ title: "Inventory", detail: "CLI + MCP + skills vs capability-map" },
        #{ title: "Digs", detail: "parallel COGNITION / HYGIENE / UNOWNED recommenders" },
        #{ title: "Report", detail: "actionable digs for the driver" },
    ],
};

let inventory_schema = #{
    "type": "object",
    "required": ["map_path", "current_cycle_hint", "unowned", "cognition_stale", "hygiene_stale", "notes"],
    "properties": #{
        "map_path": #{ "type": "string" },
        "current_cycle_hint": #{ "type": "integer" },
        "unowned": #{
            "type": "array",
            "maxItems": 20,
            "items": #{
                "type": "object",
                "required": ["capability", "surface"],
                "properties": #{
                    "capability": #{ "type": "string" },
                    "surface": #{ "type": "string" },
                    "reason": #{ "type": "string" },
                },
            },
        },
        "cognition_stale": #{
            "type": "array",
            "maxItems": 20,
            "items": #{
                "type": "object",
                "required": ["capability", "lag"],
                "properties": #{
                    "capability": #{ "type": "string" },
                    "lag": #{ "type": "integer" },
                    "owning_lane": #{ "type": "string" },
                    "epistemic_note": #{ "type": "string" },
                },
            },
        },
        "hygiene_stale": #{
            "type": "array",
            "maxItems": 20,
            "items": #{
                "type": "object",
                "required": ["capability", "lag"],
                "properties": #{
                    "capability": #{ "type": "string" },
                    "lag": #{ "type": "integer" },
                    "owning_lane": #{ "type": "string" },
                },
            },
        },
        "new_surfaces": #{
            "type": "array",
            "maxItems": 20,
            "items": #{ "type": "string" },
        },
        "notes": #{ "type": "string" },
    },
};

let dig_schema = #{
    "type": "object",
    "required": ["klass", "recommendations"],
    "properties": #{
        "klass": #{ "type": "string", "description": "COGNITION | HYGIENE | UNOWNED" },
        "recommendations": #{
            "type": "array",
            "maxItems": 5,
            "items": #{
                "type": "object",
                "required": ["capability", "lane", "why", "force_hint"],
                "properties": #{
                    "capability": #{ "type": "string" },
                    "lane": #{ "type": "string" },
                    "why": #{ "type": "string" },
                    "force_hint": #{ "type": "string", "description": "e.g. example-apps product_maturity" },
                },
            },
        },
    },
};

// ── Inventory ───────────────────────────────────────────────────────────
phase("Inventory");

let inv_prompt = "";
inv_prompt += "You are the INVENTORY stage of Dazzle /improve capability-sweep.\n";
inv_prompt += "Repo root is the current workspace. Use execute tools. Prefer read-only except updating\n";
inv_prompt += "nothing yet (apply is a later optional step).\n\n";
inv_prompt += "1. Read .claude/commands/improve/capability-map.md (registry table + Class vocabulary).\n";
inv_prompt += "2. Re-derive inventory surfaces:\n";
inv_prompt += "   - dazzle --help (and notable subcommands: qa, demo, domain, fitness, validate, …)\n";
inv_prompt += "   - MCP tool table in .claude/CLAUDE.md if present\n";
inv_prompt += "   - .claude/skills and .claude/commands trees; .agents/skills\n";
inv_prompt += "3. Read tail of dev_docs/improve-log.md for latest cycle number (current_cycle_hint).\n";
inv_prompt += "4. Reconcile map:\n";
inv_prompt += "   - Surfaces built but missing from map → new_surfaces + unowned candidates\n";
inv_prompt += "   - Map rows Status UNOWNED → unowned[]\n";
inv_prompt += "   - USED/STALE with lag = current - last-exercised ≥ 20 → STALE-effective\n";
inv_prompt += "   - Split STALE-effective by Class into cognition_stale vs hygiene_stale\n";
inv_prompt += "   - DRIVER/EXEMPT classes are not dig targets; skip metered vision as dig targets\n";
inv_prompt += "     (note subscription substitutes only).\n";
inv_prompt += "5. Cap each list at 20. notes = one paragraph on coverage health.\n";
inv_prompt += "Return the inventory schema. Do not invent capabilities you did not observe.\n";

let inv = agent(inv_prompt, #{
    label: "capability-inventory",
    capability_mode: "execute",
    output_schema: inventory_schema,
});

if inv == () || !inv.success || inv.output == () {
    pause("infra", "Inventory stage failed — check capability-map.md and dazzle CLI.");
}

let unowned = inv.output.unowned;
let cognition_stale = inv.output.cognition_stale;
let hygiene_stale = inv.output.hygiene_stale;
if unowned == () { unowned = []; }
if cognition_stale == () { cognition_stale = []; }
if hygiene_stale == () { hygiene_stale = []; }

log("Inventory: UNOWNED=" + unowned.len().to_string()
    + " COGNITION_STALE=" + cognition_stale.len().to_string()
    + " HYGIENE_STALE=" + hygiene_stale.len().to_string());

// ── Parallel dig recommenders ───────────────────────────────────────────
phase("Digs");

let inv_json = json_encode(inv.output);

let dig_jobs = [];

let cog_p = "";
cog_p += "Recommend up to 5 next COGNITION digs for /improve directed explore.\n";
cog_p += "Read-only. Prefer residual/risk, domain, demo_world, product_quality, qa trial, persona-home\n";
cog_p += "over pure re-touch. Never recommend metered taste-panel/component-vision/property-vision\n";
cog_p += "on paid path — prefer hm_visual_smoke / gallery substitutes if vision-related.\n";
cog_p += "Do not recommend WI densify when densify is a hard stop — prefer acceptance panel / trials.\n";
cog_p += "Inventory JSON:\n";
cog_p += inv_json;
cog_p += "\nReturn klass=COGNITION and ranked recommendations with force_hint for the driver.\n";
cog_p += "Empty recommendations only if cognition_stale and related residual are truly empty after reading the JSON.\n";

dig_jobs.push(#{
    prompt: cog_p,
    label: "digs:cognition",
    capability_mode: "read-only",
    output_schema: dig_schema,
});

let hyg_p = "";
hyg_p += "Recommend up to 5 next HYGIENE digs (cheap CLI re-touch) for /improve.\n";
hyg_p += "Read-only. Prefer validate/lint/prove/coverage/sentinel/MCP re-exercise that share a lane.\n";
hyg_p += "Inventory JSON:\n";
hyg_p += inv_json;
hyg_p += "\nReturn klass=HYGIENE and recommendations with force_hint. Empty list only if hygiene_stale is empty.\n";

dig_jobs.push(#{
    prompt: hyg_p,
    label: "digs:hygiene",
    capability_mode: "read-only",
    output_schema: dig_schema,
});

let own_p = "";
own_p += "Recommend up to 5 actions for UNOWNED capabilities (strongest coverage gap).\n";
own_p += "Read-only. Each recommendation should name an owning lane to assign and a first exercise.\n";
own_p += "Inventory JSON:\n";
own_p += inv_json;
own_p += "\nReturn klass=UNOWNED. Empty list only if unowned is empty.\n";

dig_jobs.push(#{
    prompt: own_p,
    label: "digs:unowned",
    capability_mode: "read-only",
    output_schema: dig_schema,
});

let dig_results = parallel(dig_jobs);

let recommendations = [];
let classes_ok = 0;
for r in dig_results {
    if r != () && r.success && r.output != () && r.output.recommendations != () {
        classes_ok += 1;
        for rec in r.output.recommendations {
            recommendations.push(#{
                klass: r.output.klass,
                capability: rec.capability,
                lane: rec.lane,
                why: rec.why,
                force_hint: rec.force_hint,
            });
        }
    }
}

// Advisory panel may fail open, but log holes
if classes_ok < 3 {
    log("Dig panel partial: " + classes_ok.to_string() + "/3 recommenders returned usable output");
}

// ── Report ──────────────────────────────────────────────────────────────
phase("Report");

let u_n = unowned.len();
let c_n = cognition_stale.len();
let h_n = hygiene_stale.len();

let status = "PASS";
// Sweep itself always "completes"; FAIL only if inventory empty nonsense
if inv.output.notes == () {
    status = "FAIL";
}

let summary = "capability-sweep UNOWNED=" + u_n.to_string()
    + " COGNITION_STALE=" + c_n.to_string()
    + " HYGIENE_STALE=" + h_n.to_string()
    + " recommendations=" + recommendations.len().to_string();

let md = "";
md += "# Improve capability-sweep\n\n";
md += "**";
md += summary;
md += "**\n\n";
if inv.output.notes != () {
    md += inv.output.notes;
    md += "\n\n";
}
md += "## Counts\n\n";
md += "| Class | Count |\n|------|------:|\n";
md += "| UNOWNED | ";
md += u_n.to_string();
md += " |\n| COGNITION_STALE | ";
md += c_n.to_string();
md += " |\n| HYGIENE_STALE | ";
md += h_n.to_string();
md += " |\n\n";

md += "## Recommendations (driver pick order: UNOWNED → COGNITION → HYGIENE)\n\n";
for rec in recommendations {
    md += "- **[";
    md += rec.klass;
    md += "]** ";
    md += rec.capability;
    md += " → lane `";
    md += rec.lane;
    md += "` — ";
    md += rec.why;
    md += " (`/improve ";
    md += rec.force_hint;
    md += "`)\n";
}
md += "\n## Driver next steps\n\n";
md += "1. Log `lane: capability-sweep` with the three counts (not a raw STALE total alone).\n";
md += "2. Update capability-map.md for new_surfaces / UNOWNED flags if inventory found drift.\n";
md += "3. budget_consumed: 0 (sweep is coverage maintenance, not explore dig).\n";
md += "4. Next product cycle may pick the top recommendation unless preemption applies.\n";

let report_path = write_scratch_file("capability-sweep-report.md", md);
log(summary);

if args != () && args.apply == true {
    let apply_p = "";
    apply_p += "Update .claude/commands/improve/capability-map.md from this inventory if needed:\n";
    apply_p += "- Add new_surfaces as UNOWNED rows with best-guess Class and owning lane.\n";
    apply_p += "- Flip Status labels that inventory shows are wrong (do not invent last-exercised).\n";
    apply_p += "Append improve-log.md entry lane: capability-sweep with counts. Do not commit unless args.commit.\n";
    apply_p += "Inventory JSON:\n";
    apply_p += inv_json;
    let ar = agent(apply_p, #{
        label: "apply-capability-map",
        capability_mode: "read-write",
    });
    if ar != () && ar.success { log("Map apply finished"); }
}

complete(#{
    status: status,
    summary: summary,
    unowned_count: u_n,
    cognition_stale_count: c_n,
    hygiene_stale_count: h_n,
    unowned: unowned,
    cognition_stale: cognition_stale,
    hygiene_stale: hygiene_stale,
    recommendations: recommendations,
    budget_consumed: 0,
    path: report_path,
});
