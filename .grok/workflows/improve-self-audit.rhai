// Improve multi-agent strategy: self-audit
// Sample recent improve: commits → parallel adversarial reviewers → structured findings.
// Driver still owns: lock, REGRESSION/AUD row writes, improve-log, self-schedule.
// Playbook source: .claude/commands/improve/strategies/self_audit.md

let meta = #{
    name: "improve-self-audit",
    description: "Adversarial review of recent improve: commits vs log/backlog claims (parallel per commit)",
    when_to_use: "When /improve self-audit is due (≥15 cycles) or forced; multi-agent claim audit",
    phases: [
        #{ title: "Sample", detail: "window + up to 5 commits" },
        #{ title: "Review", detail: "one skeptic per commit (read-only)" },
        #{ title: "Synthesize", detail: "fail-closed report for the driver" },
    ],
};

let sample_schema = #{
    "type": "object",
    "required": ["window_start", "window_end", "commits"],
    "properties": #{
        "window_start": #{ "type": "string", "description": "exclusive start SHA or empty if last-15 window" },
        "window_end": #{ "type": "string", "description": "HEAD SHA" },
        "commits": #{
            "type": "array",
            "maxItems": 5,
            "items": #{
                "type": "object",
                "required": ["sha", "subject"],
                "properties": #{
                    "sha": #{ "type": "string" },
                    "subject": #{ "type": "string" },
                    "log_excerpt": #{ "type": "string" },
                    "backlog_notes": #{ "type": "string" },
                    "diffstat_lines": #{ "type": "integer" },
                },
            },
        },
        "notes": #{ "type": "string" },
    },
};

let verdict_schema = #{
    "type": "object",
    "required": ["sha", "verdict", "claim_ok", "evidence"],
    "properties": #{
        "sha": #{ "type": "string" },
        "verdict": #{ "type": "string", "description": "CLEAN or DISCREPANCY" },
        "claim_ok": #{ "type": "boolean" },
        "evidence": #{ "type": "string" },
        "discrepancy_kind": #{
            "type": "string",
            "description": "shipped_broken | bookkeeping | dig_contract | undeclared_scope | none",
        },
        "affected_lane": #{ "type": "string" },
        "suggested_action": #{
            "type": "string",
            "description": "none | REGRESSION | AUD row text",
        },
    },
};

let report_schema = #{
    "type": "object",
    "required": ["status", "summary", "window_start", "window_end", "verdicts", "discrepancy_count"],
    "properties": #{
        "status": #{ "type": "string", "description": "PASS if zero discrepancies, else FAIL" },
        "summary": #{ "type": "string" },
        "window_start": #{ "type": "string" },
        "window_end": #{ "type": "string" },
        "discrepancy_count": #{ "type": "integer" },
        "verdicts": #{ "type": "array", "items": #{ "type": "object" } },
        "apply_hints": #{ "type": "array", "items": #{ "type": "string" } },
        "budget_consumed": #{ "type": "integer" },
    },
};

// Optional: args.max_commits (1-5)
let max_commits = 5;
if args != () && args.max_commits != () {
    let mc = args.max_commits;
    // Prefer small integers only; ignore unusable values.
    if mc == 1 || mc == 2 || mc == 3 || mc == 4 || mc == 5 {
        max_commits = mc;
    }
}

// ── Sample ──────────────────────────────────────────────────────────────
phase("Sample");

let sample_prompt = "";
sample_prompt += "You are the SAMPLE stage of Dazzle /improve self-audit. Repo root is the current workspace.\n";
sample_prompt += "Use shell/git tools. Do NOT mutate the worktree (no stash/checkout/reset/merge).\n\n";
sample_prompt += "1. Find the last self-audit in dev_docs/improve-log.md (search for 'lane: self-audit').\n";
sample_prompt += "   Prefer an end SHA recorded there. Window = that SHA exclusive .. HEAD.\n";
sample_prompt += "   If none: window = last 15 commits that look improve-related (see step 2).\n";
sample_prompt += "2. List improve-relevant commits in the window (NOT only '^improve: cycle' — that is legacy and empty on modern tips):\n";
sample_prompt += "   git log --oneline <start>..HEAD\n";
sample_prompt += "   Include a commit if ANY of:\n";
sample_prompt += "     - subject contains '(cycle N)' / '(cycle NNNN)'  (primary style: feat/fix … (cycle 1889))\n";
sample_prompt += "     - subject matches '^improve:' (legacy)\n";
sample_prompt += "     - SHA is named in an improve-log Cycle entry for this window\n";
sample_prompt += "   Also: git log --oneline --grep '(cycle [0-9]' <start>..HEAD\n";
sample_prompt += "3. Sample at most ";
sample_prompt += max_commits.to_string();
sample_prompt += " commits: if ≤N take all; if more take largest diffstat plus any that moved DONE/VERIFIED.\n";
sample_prompt += "4. For each sampled commit, extract the matching improve-log.md cycle entry and any backlog\n";
sample_prompt += "   rows it touched (also grep dev_docs/improve-backlog-archive.md if needed).\n";
sample_prompt += "5. Return window_start, window_end (HEAD full SHA), commits[{sha,subject,log_excerpt,backlog_notes,diffstat_lines}].\n";
sample_prompt += "Empty commits is valid ONLY after git log shows zero (cycle N) and zero ^improve: and no log-named SHAs.\n";
sample_prompt += "If the window has feat/fix (cycle N) ships and you return empty commits, that is a SAMPLE BUG — re-run step 2.\n";

let sample = agent(sample_prompt, #{
    label: "sample-window",
    capability_mode: "execute",
    output_schema: sample_schema,
});

if sample == () || !sample.success || sample.output == () {
    pause("infra", "Sample stage failed — check git and dev_docs/improve-log.md access.");
}

let window_start = sample.output.window_start;
let window_end = sample.output.window_end;
let commits = sample.output.commits;
if commits == () { commits = []; }

if commits.len() == 0 {
    let empty_path = write_scratch_file("self-audit-report.md", "# Self-audit\n\nNo improve: commits in window.\n");
    complete(#{
        status: "PASS",
        summary: "No improve: commits to audit in window.",
        window_start: window_start,
        window_end: window_end,
        discrepancy_count: 0,
        verdicts: [],
        apply_hints: [],
        budget_consumed: 0,
        path: empty_path,
    });
}

log("Sampled " + commits.len().to_string() + " commits for self-audit");

// ── Review (parallel, read-only) ────────────────────────────────────────
phase("Review");

let jobs = [];
for c in commits {
    let sha = c.sha;
    let subject = if c.subject != () { c.subject } else { "" };
    let log_excerpt = if c.log_excerpt != () { c.log_excerpt } else { "" };
    let backlog_notes = if c.backlog_notes != () { c.backlog_notes } else { "" };

    let p = "";
    p += "You are an ADVERSARIAL self-audit reviewer for Dazzle /improve. Refute, do not summarise.\n";
    p += "HARD RULES — you MUST NOT mutate the shared worktree:\n";
    p += "  forbidden: git stash, checkout, reset, merge, stash pop, cherry-pick on the main tree.\n";
    p += "  allowed: git show <sha>, git log, git diff <sha>..HEAD, grep, read_file, run tests AS-IS on HEAD.\n";
    p += "  If you need a tree at <sha>, use isolated: git worktree add /tmp/audit-<sha> <sha> then remove it.\n\n";
    p += "Commit SHA: ";
    p += sha;
    p += "\nSubject: ";
    p += subject;
    p += "\n\nLog claim (from improve-log):\n";
    p += log_excerpt;
    p += "\n\nBacklog notes:\n";
    p += backlog_notes;
    p += "\n\nCheck:\n";
    p += "1. Claim ↔ diff: does git show ";
    p += sha;
    p += " actually do what the log says?\n";
    p += "2. Verification honesty: if tests/QA claimed, do named tests exist and pass NOW on HEAD?\n";
    p += "3. Transition justification: DONE/VERIFIED without lane QA steps?\n";
    p += "4. Scope honesty: undeclared drive-by files?\n";
    p += "5. Dig contracts: if lane example-apps story_walk or agent_acceptance_panel, require contract: lines\n";
    p += "   and/or python scripts/improve_dig_receipt.py check — DISCREPANCY if PASS claimed without evidence.\n\n";
    p += "Verdict CLEAN only with concrete inspection. DISCREPANCY needs reproducible evidence (command + output).\n";
    p += "Set discrepancy_kind: shipped_broken | bookkeeping | dig_contract | undeclared_scope | none.\n";
    p += "suggested_action: none | REGRESSION | short AUD row text. affected_lane if known.\n";
    p += "Return schema fields only. Empty evidence is invalid for DISCREPANCY.\n";

    jobs.push(#{
        prompt: p,
        label: "audit:" + sha.sub_string(0, 8),
        capability_mode: "read-only",
        output_schema: verdict_schema,
    });
}

let results = parallel(jobs);

// ── Synthesize ──────────────────────────────────────────────────────────
phase("Synthesize");

let verdicts = [];
let apply_hints = [];
let disc = 0;
let i = 0;
for r in results {
    let c = commits[i];
    let sha = c.sha;
    if r == () || !r.success || r.output == () {
        // Fail closed: unusable reviewer is not CLEAN
        disc += 1;
        let failed = #{
            sha: sha,
            verdict: "DISCREPANCY",
            claim_ok: false,
            evidence: "Reviewer slot failed or returned no usable output — treat as unverified.",
            discrepancy_kind: "bookkeeping",
            affected_lane: "",
            suggested_action: "Re-run audit for this commit; do not trust the cycle claim until re-checked.",
        };
        verdicts.push(failed);
        apply_hints.push("UNVERIFIED " + sha + " — reviewer failed");
    } else {
        let v = r.output;
        // Enforce sha match / fill
        if v.sha == () || v.sha == "" { v.sha = sha; }
        let is_disc = false;
        if v.verdict == "DISCREPANCY" { is_disc = true; }
        if v.claim_ok == false { is_disc = true; }
        // Fail closed: DISCREPANCY without evidence becomes explicit
        if is_disc {
            v.verdict = "DISCREPANCY";
            v.claim_ok = false;
            if v.evidence == () || v.evidence == "" {
                v.evidence = "DISCREPANCY claimed without evidence — synthesizer fail-closed note.";
            }
            disc += 1;
            if v.suggested_action != () && v.suggested_action != "" && v.suggested_action != "none" {
                apply_hints.push(sha + ": " + v.suggested_action);
            } else {
                apply_hints.push(sha + ": review DISCREPANCY in log");
            }
        } else {
            // Only accept CLEAN with non-empty evidence of inspection
            if v.evidence == () || v.evidence == "" {
                disc += 1;
                v.verdict = "DISCREPANCY";
                v.claim_ok = false;
                v.discrepancy_kind = "bookkeeping";
                v.evidence = "CLEAN without inspection evidence — fail closed.";
                apply_hints.push(sha + ": CLEAN rejected (no evidence)");
            } else {
                v.verdict = "CLEAN";
                v.claim_ok = true;
            }
        }
        verdicts.push(v);
    }
    i += 1;
}

let status = "PASS";
if disc > 0 { status = "FAIL"; }

let summary = status + ": " + disc.to_string() + "/" + verdicts.len().to_string() + " discrepancies; window " + window_start + ".." + window_end;

// Markdown report for the pager
let md = "";
md += "# Improve self-audit\n\n";
md += "**Status:** ";
md += status;
md += "\n**Window:** `";
md += window_start;
md += "` .. `";
md += window_end;
md += "`\n**Discrepancies:** ";
md += disc.to_string();
md += " / ";
md += verdicts.len().to_string();
md += "\n\n## Verdicts\n\n";
for v in verdicts {
    md += "### ";
    md += v.sha;
    md += " — ";
    md += v.verdict;
    md += "\n\n";
    md += v.evidence;
    md += "\n\n";
    if v.suggested_action != () && v.suggested_action != "" {
        md += "- suggested: ";
        md += v.suggested_action;
        md += "\n";
    }
    if v.affected_lane != () && v.affected_lane != "" {
        md += "- lane: ";
        md += v.affected_lane;
        md += "\n";
    }
    md += "\n";
}
if apply_hints.len() > 0 {
    md += "## Apply hints (driver)\n\n";
    for h in apply_hints {
        md += "- ";
        md += h;
        md += "\n";
    }
}
md += "\n## Driver next steps\n\n";
md += "1. For shipped_broken → mark backlog row REGRESSION in the affected lane section.\n";
md += "2. For bookkeeping → add AUD-NNN row to that lane.\n";
md += "3. Append improve-log entry `lane: self-audit` with window end SHA = ";
md += window_end;
md += ".\n";
md += "4. budget_consumed: 0. Do not fix inline.\n";

let report_path = write_scratch_file("self-audit-report.md", md);
log(summary);

// Optional apply agent when args.apply == true (still no product fixes — rows only)
if args != () && args.apply == true {
    let apply_prompt = "";
    apply_prompt += "Apply self-audit findings to Dazzle improve state. Do NOT fix product code.\n";
    apply_prompt += "Read scratch report path context from this run summary.\n";
    apply_prompt += "Window end SHA: ";
    apply_prompt += window_end;
    apply_prompt += "\nDiscrepancy count: ";
    apply_prompt += disc.to_string();
    apply_prompt += "\n\nFor each DISCREPANCY with suggested_action REGRESSION: edit dev_docs/improve-backlog.md\n";
    apply_prompt += "to set the affected row status to REGRESSION (lane section).\n";
    apply_prompt += "For bookkeeping: append an AUD-NNN row to the affected lane section.\n";
    apply_prompt += "Append a cycle entry to dev_docs/improve-log.md with lane: self-audit, window SHAs,\n";
    apply_prompt += "verdicts summary, end SHA. budget_consumed: 0. Do not commit unless args.commit is true.\n";
    apply_prompt += "Return a short text summary of files touched.\n";
    // Encode verdicts as JSON for the agent
    let encoded = json_encode(#{
        status: status,
        window_start: window_start,
        window_end: window_end,
        discrepancy_count: disc,
        verdicts: verdicts,
        apply_hints: apply_hints,
    });
    apply_prompt += "\nJSON payload:\n";
    apply_prompt += encoded;

    let ar = agent(apply_prompt, #{
        label: "apply-audit-rows",
        capability_mode: "read-write",
    });
    if ar != () && ar.success {
        log("Apply stage finished");
    } else {
        log("Apply stage failed or skipped output — driver must apply manually");
    }
}

complete(#{
    status: status,
    summary: summary,
    window_start: window_start,
    window_end: window_end,
    discrepancy_count: disc,
    verdicts: verdicts,
    apply_hints: apply_hints,
    budget_consumed: 0,
    path: report_path,
});
