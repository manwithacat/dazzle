// Improve multi-agent strategy: visual tier-2 review (judgment half)
// Assumes capture already produced a manifest (dazzle qa capture).
// Parallel per-app reviewers → structured findings for visual_tier2_ingest.
// Driver still owns: capture/boot, ingest, backlog, explore budget (+5), log.
// Playbook: .claude/commands/improve/strategies/visual_tier2_subagent.md

let meta = #{
    name: "improve-visual-review",
    description: "Parallel visual QA review of a dazzle qa capture manifest (one agent per app)",
    when_to_use: "After dazzle qa capture wrote a fleet manifest; example-apps visual_tier2 judgment step",
    phases: [
        #{ title: "Load", detail: "validate manifest + app list" },
        #{ title: "Review", detail: "one visual reviewer per app" },
        #{ title: "Merge", detail: "combined findings for ingest" },
    ],
};

let load_schema = #{
    "type": "object",
    "required": ["manifest_path", "apps", "screen_count"],
    "properties": #{
        "manifest_path": #{ "type": "string" },
        "apps": #{
            "type": "array",
            "maxItems": 12,
            "items": #{
                "type": "object",
                "required": ["app", "screen_count"],
                "properties": #{
                    "app": #{ "type": "string" },
                    "screen_count": #{ "type": "integer" },
                    "screenshot_paths": #{
                        "type": "array",
                        "maxItems": 30,
                        "items": #{ "type": "string" },
                    },
                },
            },
        },
        "screen_count": #{ "type": "integer" },
        "notes": #{ "type": "string" },
    },
};

let app_findings_schema = #{
    "type": "object",
    "required": ["app", "findings"],
    "properties": #{
        "app": #{ "type": "string" },
        "findings": #{
            "type": "array",
            "maxItems": 12,
            "items": #{
                "type": "object",
                "required": ["app", "category", "severity", "description", "location"],
                "properties": #{
                    "app": #{ "type": "string" },
                    "category": #{ "type": "string" },
                    "severity": #{ "type": "string", "description": "high | medium | low" },
                    "description": #{ "type": "string" },
                    "location": #{ "type": "string" },
                    "screenshot": #{ "type": "string" },
                },
            },
        },
    },
};

// Require args.manifest_path
let manifest_path = ();
if args != () { manifest_path = args.manifest_path; }
if manifest_path == () || manifest_path == "" {
    pause("verification", "Pass args.manifest_path — path to dazzle qa capture manifest.json");
}

// Cap apps for agent budget (leave headroom)
let max_apps = 6;
if args != () && args.max_apps != () {
    let ma = args.max_apps;
    if ma == 1 || ma == 2 || ma == 3 || ma == 4 || ma == 5 || ma == 6 {
        max_apps = ma;
    }
}

// ── Load ────────────────────────────────────────────────────────────────
phase("Load");

let load_p = "";
load_p += "Load and validate a Dazzle visual capture manifest. Use read_file / shell.\n";
load_p += "Manifest path: ";
load_p += manifest_path;
load_p += "\n\n1. Parse JSON. Expect apps[] with app name and screens (paths or screenshot fields).\n";
load_p += "2. Return apps[{app, screen_count, screenshot_paths}] capped at ";
load_p += max_apps.to_string();
load_p += " apps (prefer highest screen_count if over cap; log which were dropped in notes).\n";
load_p += "3. screen_count = total screens across returned apps.\n";
load_p += "4. Resolve screenshot paths to absolute paths when relative to repo or manifest dir.\n";
load_p += "Empty apps only if the manifest truly has zero screens after reading the file.\n";

let loaded = agent(load_p, #{
    label: "load-manifest",
    capability_mode: "execute",
    output_schema: load_schema,
});

if loaded == () || !loaded.success || loaded.output == () {
    pause("infra", "Failed to load manifest at args.manifest_path");
}

let apps = loaded.output.apps;
if apps == () { apps = []; }

if apps.len() == 0 || loaded.output.screen_count == 0 {
    let p = write_scratch_file("visual-findings.json", "[]");
    complete(#{
        status: "PASS",
        summary: "Manifest has zero screens — nothing to review.",
        findings: [],
        findings_path: p,
        apps_reviewed: 0,
        budget_consumed: 0,
    });
}

log("Visual review: " + apps.len().to_string() + " apps, screens=" + loaded.output.screen_count.to_string());

// ── Parallel per-app review ─────────────────────────────────────────────
phase("Review");

let jobs = [];
for a in apps {
    let app_name = a.app;
    let paths = if a.screenshot_paths != () { a.screenshot_paths } else { []; };
    let paths_json = json_encode(paths);

    let rp = "";
    rp += "You are a visual QA reviewer for one Dazzle example app. Read-only tools + read image files.\n";
    rp += "App: ";
    rp += app_name;
    rp += "\nScreenshot paths (JSON array):\n";
    rp += paths_json;
    rp += "\n\nFor EACH screenshot path that exists, use the read_file/image tool to view it.\n";
    rp += "Evaluate against Dazzle visual categories (typical):\n";
    rp += "  layout density, hierarchy, empty-state, form clarity, contrast, spacing, overflow,\n";
    rp += "  persona-home usefulness, navigation confusion, dead chrome, HM/dz consistency.\n";
    rp += "Do NOT invent screens you did not open. Empty findings is valid only after viewing all paths\n";
    rp += "(or noting missing files with one low finding about missing capture).\n";
    rp += "Max 12 findings for this app. severity high|medium|low.\n";
    rp += "location should be screen name or UI region. category short slug.\n";
    rp += "description concrete and actionable. screenshot = path used.\n";
    rp += "Return {app, findings:[{app,category,severity,description,location,screenshot}]}.\n";

    jobs.push(#{
        prompt: rp,
        label: "visual:" + app_name,
        capability_mode: "read-only",
        output_schema: app_findings_schema,
    });
}

let results = parallel(jobs);

// ── Merge ───────────────────────────────────────────────────────────────
phase("Merge");

let findings = [];
let apps_ok = 0;
let i = 0;
for r in results {
    let app_name = apps[i].app;
    if r != () && r.success && r.output != () && r.output.findings != () {
        apps_ok += 1;
        for f in r.output.findings {
            // Enforce app field
            if f.app == () || f.app == "" { f.app = app_name; }
            findings.push(f);
        }
    } else {
        log("Visual reviewer failed for app " + app_name + " — no findings from that slot");
    }
    i += 1;
}

// Sort-ish: push high first by building two lists (no sort in dialect)
let highs = [];
let rest = [];
for f in findings {
    if f.severity == "high" {
        highs.push(f);
    } else {
        rest.push(f);
    }
}
let ordered = [];
for f in highs { ordered.push(f); }
for f in rest { ordered.push(f); }
findings = ordered;

let findings_json = json_encode(findings);
let findings_path = write_scratch_file("visual-findings.json", findings_json);

let md = "";
md += "# Improve visual review\n\n";
md += "Manifest: `";
md += manifest_path;
md += "`\nApps reviewed OK: ";
md += apps_ok.to_string();
md += " / ";
md += apps.len().to_string();
md += "\nFindings: ";
md += findings.len().to_string();
md += "\n\n";
for f in findings {
    md += "- **[";
    md += f.severity;
    md += "]** ";
    md += f.app;
    md += " / ";
    md += f.category;
    md += " — ";
    md += f.description;
    md += " @ ";
    md += f.location;
    md += "\n";
}
md += "\n## Driver next steps\n\n";
md += "1. Write findings JSON to a durable path if needed (scratch: visual-findings.json).\n";
md += "2. Run visual_tier2_ingest.ingest_visual_findings(findings_path, manifest_path, backlog_path).\n";
md += "3. Log lane: example-apps visual_tier2; budget_consumed: 5.\n";
md += "4. Drain PENDING visual_quality rows before re-sweeping.\n";

let report_path = write_scratch_file("visual-review-report.md", md);

let summary = "visual-review findings=" + findings.len().to_string()
    + " apps_ok=" + apps_ok.to_string() + "/" + apps.len().to_string();
log(summary);

complete(#{
    status: "PASS",
    summary: summary,
    findings: findings,
    findings_path: findings_path,
    report_path: report_path,
    manifest_path: manifest_path,
    apps_reviewed: apps_ok,
    budget_consumed: 5,
});
