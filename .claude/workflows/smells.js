export const meta = {
  name: "smells",
  description:
    "Two-phase code-smell scan of src/dazzle: regression checks + systemic pattern discovery, run as parallel finders",
  phases: [
    {
      title: "Scan",
      detail:
        "regression checks + 3 pattern-category finders + the decay-harness finder, in parallel",
    },
  ],
};

const REGRESSION_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    checks: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          id: { type: "string", description: "check id, e.g. 1.1, 1.5a" },
          check: { type: "string" },
          status: { type: "string", enum: ["PASS", "FAIL", "TRACK"] },
          details: { type: "string" },
        },
        required: ["id", "check", "status", "details"],
      },
    },
  },
  required: ["checks"],
};

const PATTERN_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    patterns: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          pattern: { type: "string" },
          category: { type: "string" },
          instances: { type: "integer" },
          root_cause: { type: "string" },
          canonical_fix: { type: "string" },
          done_criteria: { type: "string" },
          enforcement: { type: "string" },
        },
        required: [
          "pattern",
          "category",
          "instances",
          "root_cause",
          "canonical_fix",
          "done_criteria",
          "enforcement",
        ],
      },
    },
  },
  required: ["patterns"],
};

// Ground-truth structural decay, sourced from the live fitness harness (shipped
// v0.83.26) rather than re-derived by grep. The ratchet + import contracts already
// GATE new violations in CI; this finder reports the *baselined standing debt* those
// gates hold the line on, so the smells report tracks it each round.
const DECAY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    hotspots: {
      type: "array",
      description: "top churn×complexity files from `dazzle fitness code`",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          rank: { type: "integer" },
          file: { type: "string" },
          score: { type: "number" },
          churn: { type: "integer" },
          mi_rank: { type: "string", description: "A | B | C" },
        },
        required: ["rank", "file", "score", "churn", "mi_rank"],
      },
    },
    c_rank_files: {
      type: "array",
      description: "files at radon MI rank C in the committed baseline",
      items: { type: "string" },
    },
    high_cc_functions: {
      type: "array",
      description: "highest-cyclomatic-complexity functions in the baseline",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          file: { type: "string" },
          function: { type: "string" },
          cc: { type: "integer" },
        },
        required: ["file", "function", "cc"],
      },
    },
    ratchet_status: {
      type: "string",
      description: "`clean` or `<n> violations` from test_complexity_ratchet",
    },
    import_contracts: {
      type: "object",
      additionalProperties: false,
      properties: {
        status: { type: "string", description: "kept | broken" },
        allowlist_size: { type: "integer" },
        entries: { type: "array", items: { type: "string" } },
      },
      required: ["status", "allowlist_size", "entries"],
    },
    priority_targets: {
      type: "array",
      description:
        "files that are BOTH high-churn hotspots AND MI rank C — the refactor queue",
      items: { type: "string" },
    },
    notes: { type: "string" },
  },
  required: [
    "hotspots",
    "c_rank_files",
    "high_cc_functions",
    "ratchet_status",
    "import_contracts",
    "priority_targets",
    "notes",
  ],
};

const DECAY_PROMPT = `Report the framework's standing structural decay from the LIVE fitness harness (shipped v0.83.26) at /Volumes/SSD/Dazzle. Do NOT re-derive any of this by grep — read the harness outputs. Use \`.venv/bin/\` binaries.

1. **Hotspot queue** — run \`cd /Volumes/SSD/Dazzle && .venv/bin/dazzle fitness code\` (churn×complexity ranking; prints a markdown table to stdout). Return the top 10 rows as \`hotspots\` (rank, file, score, churn, mi_rank).
2. **C-rank set + high-CC functions** — read \`tests/unit/fixtures/complexity_baseline.json\` (the committed ratchet baseline: \`{path: {mi_rank, functions: {name: cc}}}\`). \`c_rank_files\` = every path with \`mi_rank == "C"\`. \`high_cc_functions\` = the 10 functions with the highest \`cc\` (file, function, cc).
3. **Ratchet status** — run \`.venv/bin/python -m pytest tests/unit/test_complexity_ratchet.py::test_current_tree_does_not_regress_against_baseline -q\`. \`ratchet_status\` = "clean" if it passes, else "<n> violations" with a one-line note.
4. **Import contracts** — run \`cd /Volumes/SSD/Dazzle && .venv/bin/lint-imports\` (status kept/broken). Read the \`[tool.importlinter]\` block in pyproject.toml: \`import_contracts.entries\` = the \`ignore_imports\` allow-list across all contracts, \`allowlist_size\` = its length. These are the documented load-bearing cross-layer edges (standing debt the contracts hold flat — the ratchet posture is that this list only ever SHRINKS).
5. **Priority targets** — \`priority_targets\` = files appearing in BOTH the top-12 hotspots AND \`c_rank_files\` (high-churn × low-maintainability = the genuine refactor queue, e.g. server.py / workspace.py / entity.py / store.py). These are where a refactor buys the most.

\`notes\`: one or two sentences — is decay holding flat, and which one file is the single best refactor target this round? Return the DECAY_SCHEMA object.`;

const SCOPE =
  "Focus on src/dazzle/ (the merged tree — back/, ui/, render/ all live under it since the #1055 package merge). Ignore tests/, examples/, and auto-generated files.";

const REGRESSION_PROMPT = `Run regression checks on the Dazzle codebase at /Volumes/SSD/Dazzle using Bash and Grep. For each check return status PASS, FAIL, or TRACK plus a one-line details string.

1.1 no-swallowed-exceptions — grep -rn "except Exception: pass" src/ --include="*.py", plus "except Exception:" on its own line followed by a bare pass. PASS=0 (except followed by logging is fine).
1.2 no-redundant-except-tuples — grep src/ for "except (ImportError, Exception)", "except (json.JSONDecodeError, Exception)", "except (JSONDecodeError, Exception)". PASS=0 across all three.
1.3 core-mcp-isolation — grep -rn "from dazzle\\.mcp" src/dazzle/core/. PASS=0. NOTE: layer isolation is now a LIVE gate — the import-linter \`core stays backend- and UI-agnostic\` contract (\`back\`/\`ui\`) subsumes a superset of this; this grep is the narrower mcp-specific echo. If \`from dazzle.mcp\` appears in core but \`lint-imports\` is green, it's an allow-listed edge — say so.
1.4 no-project-path-Any — grep -rn "project_path: Any" src/dazzle/mcp/server/handlers/. PASS=0.
1.5a no-silent-event-handlers — grep -rn "except" src/dazzle/back/events/ src/dazzle/back/channels/ --include="*.py" -A2 | grep -E "pass$|return$". PASS=0.
1.5b getattr-string-literals — count "getattr(" in src/. PASS if <200, else TRACK with the count.
1.6 complexity-creep (radon) — the crude line-count proxy is SUPERSEDED by the live complexity ratchet. Read \`tests/unit/fixtures/complexity_baseline.json\` and TRACK: count of MI-rank-C files + the single highest-CC function. The ratchet (\`tests/unit/test_complexity_ratchet.py\`) gates NEW CC>15 / MI-rank drops in CI, so this row is the *standing* baseline, not a discovery. (The decay-harness finder owns the full breakdown — keep this to the one-line count.)
1.7 god-files (radon) — same source: TRACK the count of files at MI rank C from the baseline (the god-class/god-module candidates radon flags by maintainability, not raw line count). Cross-ref the hotspot queue for which are also high-churn.
1.8 alpine-window-bindings (#795) — grep -rnE '@(pointer|mouse|key|resize|scroll|click|touch)[a-z]*\\.window' src/dazzle/ui/ --include="*.html". PASS=0; each hit is a latent listener-lifecycle bug.
1.9 import-contract-allowlist — run \`cd /Volumes/SSD/Dazzle && .venv/bin/lint-imports\`. PASS if it exits 0 (contracts kept); FAIL if broken (a new cross-layer import landed). Then TRACK the size of the \`ignore_imports\` allow-list in the \`[tool.importlinter]\` block of pyproject.toml — the documented load-bearing edges. The ratchet posture is that this list only ever shrinks; flag if it grew since last round.

Calibration: status is about PRODUCTION code. If EVERY hit for a check is in a tests/ fixture, or is a narrow intentional handler (a specific exception type that logs / re-raises / does cleanup), mark that check PASS and say so in details — reserve FAIL for genuine production violations. Use TRACK for the standing-debt counts (1.5b/1.6/1.7) and the allow-list size (1.9). 1.6/1.7 read the radon baseline — do NOT re-count lines by grep.

Return {checks: [{id, check, status, details}]}.`;

const PATTERN_CATS = [
  {
    key: "error-coupling",
    cats: "Error handling (silent failures, inconsistent exception strategy, missing retries on I/O) and Coupling (layer violations, circular imports, inappropriate intimacy, fan-in >8)",
  },
  {
    key: "dup-types",
    cats: "Duplication (near-duplicate blocks >10 lines, copy-paste across handlers) and Type safety (Any where a concrete type is known, # type: ignore masking a real issue)",
  },
  {
    key: "complexity-globals",
    cats: "Complexity (deeply nested 3+ level conditionals, god classes, tangled control flow) and Mutable globals (hidden singletons, module-level mutable state, thread-unsafe patterns)",
    seed: "Do NOT re-derive complexity by line count — the live fitness harness already owns that. Run `cd /Volumes/SSD/Dazzle && .venv/bin/dazzle fitness code` and read its top rows, then spend your JUDGMENT on those specific high-churn × MI-rank-C files (server.py / workspace.py / entity.py / store.py and peers): what is the actual structural smell driving the low maintainability — a god class, a dispatch dict that should be polymorphism, copy-paste branches, tangled state? Report the *named* smell + canonical fix, not the raw metric.",
  },
];

const patternPrompt = (pc) =>
  `Scan the Dazzle codebase at /Volumes/SSD/Dazzle for code-smell patterns in these categories: ${pc.cats}. ${SCOPE} ${pc.seed ? pc.seed + " " : ""}Only report patterns with >=2 instances. For each: name, category, instance count, root cause (why it recurs), canonical fix (the single correct way), done criteria (a grep command to verify), enforcement (how to prevent recurrence). Backward compatibility is NOT required here — flag compat shims / wrapper functions as smells in their own right. Return {patterns: [...]} (empty array if none).`;

phase("Scan");

const results = await parallel([
  () =>
    agent(REGRESSION_PROMPT, {
      label: "regressions",
      phase: "Scan",
      schema: REGRESSION_SCHEMA,
    }),
  ...PATTERN_CATS.map(
    (pc) => () =>
      agent(patternPrompt(pc), {
        label: `patterns:${pc.key}`,
        phase: "Scan",
        schema: PATTERN_SCHEMA,
      }),
  ),
  () =>
    agent(DECAY_PROMPT, {
      label: "decay-harness",
      phase: "Scan",
      schema: DECAY_SCHEMA,
    }),
]);

const reg = results[0];
const decay = results[results.length - 1] || null;
// patterns = the middle finders (between regressions and the decay finder)
const patterns = results
  .slice(1, -1)
  .filter(Boolean)
  .flatMap((x) => x.patterns);

return {
  regressions: reg ? reg.checks : [],
  patterns,
  decay,
  regressed: reg ? reg.checks.filter((c) => c.status === "FAIL").length : 0,
};
