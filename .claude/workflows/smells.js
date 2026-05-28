export const meta = {
  name: "smells",
  description:
    "Two-phase code-smell scan of src/dazzle: regression checks + systemic pattern discovery, run as parallel finders",
  phases: [
    {
      title: "Scan",
      detail: "regression checks + 3 pattern-category finders, in parallel",
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

const SCOPE =
  "Focus on src/dazzle/ (the merged tree — back/, ui/, render/ all live under it since #1056). Ignore tests/, examples/, and auto-generated files.";

const REGRESSION_PROMPT = `Run regression checks on the Dazzle codebase at /Volumes/SSD/Dazzle using Bash and Grep. For each check return status PASS, FAIL, or TRACK plus a one-line details string.

1.1 no-swallowed-exceptions — grep -rn "except Exception: pass" src/ --include="*.py", plus "except Exception:" on its own line followed by a bare pass. PASS=0 (except followed by logging is fine).
1.2 no-redundant-except-tuples — grep src/ for "except (ImportError, Exception)", "except (json.JSONDecodeError, Exception)", "except (JSONDecodeError, Exception)". PASS=0 across all three.
1.3 core-mcp-isolation — grep -rn "from dazzle\\.mcp" src/dazzle/core/. PASS=0.
1.4 no-project-path-Any — grep -rn "project_path: Any" src/dazzle/mcp/server/handlers/. PASS=0.
1.5a no-silent-event-handlers — grep -rn "except" src/dazzle/back/events/ src/dazzle/back/channels/ --include="*.py" -A2 | grep -E "pass$|return$". PASS=0.
1.5b getattr-string-literals — count "getattr(" in src/. PASS if <200, else TRACK with the count.
1.6 function-length — count functions >150 lines in src/; TRACK with count + top 5 longest (aspirational).
1.7 class-length — count classes >800 lines in src/; TRACK with any offenders (aspirational).
1.8 alpine-window-bindings (#795) — grep -rnE '@(pointer|mouse|key|resize|scroll|click|touch)[a-z]*\\.window' src/dazzle/ui/ --include="*.html". PASS=0; each hit is a latent listener-lifecycle bug.

Calibration: status is about PRODUCTION code. If EVERY hit for a check is in a tests/ fixture, or is a narrow intentional handler (a specific exception type that logs / re-raises / does cleanup), mark that check PASS and say so in details — reserve FAIL for genuine production violations. Use TRACK for the aspirational counts (1.5b/1.6/1.7).

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
    cats: "Complexity (functions >80 lines, deeply nested 3+ level conditionals, god classes) and Mutable globals (hidden singletons, module-level mutable state, thread-unsafe patterns)",
  },
];

const patternPrompt = (pc) =>
  `Scan the Dazzle codebase at /Volumes/SSD/Dazzle for code-smell patterns in these categories: ${pc.cats}. ${SCOPE} Only report patterns with >=2 instances. For each: name, category, instance count, root cause (why it recurs), canonical fix (the single correct way), done criteria (a grep command to verify), enforcement (how to prevent recurrence). Backward compatibility is NOT required here — flag compat shims / wrapper functions as smells in their own right. Return {patterns: [...]} (empty array if none).`;

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
]);

const reg = results[0];
const patterns = results
  .slice(1)
  .filter(Boolean)
  .flatMap((x) => x.patterns);

return {
  regressions: reg ? reg.checks : [],
  patterns,
  regressed: reg ? reg.checks.filter((c) => c.status === "FAIL").length : 0,
};
