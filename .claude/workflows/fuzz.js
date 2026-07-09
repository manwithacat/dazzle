export const meta = {
  name: "fuzz",
  description:
    "Cross-app static integration fuzz: one agent per example/fixture scrapes boot stderr + lint for runtime-bug signatures",
  phases: [{ title: "Sweep", detail: "one fuzz agent per app, in parallel" }],
};

const APP_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    app: { type: "string" },
    status: { type: "string", description: '"OK" or "<N> issues"' },
    bugs: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          severity: { type: "string", enum: ["HIGH", "MEDIUM", "LOW"] },
          signature: {
            type: "string",
            description: "terse bug signature, reused as the issue title",
          },
          detail: {
            type: "string",
            description: "one line, file:line if known",
          },
          evidence: { type: "string", description: "verbatim error output" },
        },
        required: ["severity", "signature", "detail", "evidence"],
      },
    },
    soft: {
      type: "array",
      items: { type: "string" },
      description: "informational lint suggestions, NOT bugs",
    },
  },
  required: ["app", "status", "bugs", "soft"],
};

// Main loop scouts `ls -d examples/*/ fixtures/*/` and passes app paths as args.
// Accept a JSON array, a JSON-encoded string, or a CSV/newline string — the
// Workflow tool sometimes stringifies list args.
function coerceList(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === "string" && v.trim()) {
    try {
      const p = JSON.parse(v);
      return Array.isArray(p) ? p : [];
    } catch {
      return v
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    }
  }
  return [];
}

const apps = coerceList(args);
if (!apps.length) {
  log(
    `No app paths resolved from args (type=${typeof args}). Pass a JSON array of app paths.`,
  );
  return { apps: [] };
}

const SOFT_ALLOWLIST =
  'NEVER report these as bugs (demote to soft): "entity X has permissions but no surfaces"; "no fitness.repr_fields"; "no command palette fragment"; "no timeline workspace region"; "5 fields in a single section"; "permit but no scope" on pra/shapes_validation fixtures; Sentinel BL-XX hints.';

const fuzzPrompt = (path) => {
  const name = path.split("/").filter(Boolean).pop();
  return `Fuzz the Dazzle app at ${path} (name: ${name}). Find INTEGRATION bugs that \`dazzle validate\` does NOT catch. Use Bash. Report ONLY real problems.

1. cd ${path} && dazzle validate 2>&1 | tail -5 — must pass.
2. cd ${path} && dazzle lint 2>&1 | grep -iE "ERROR|FAILED" | head -10 — flag errors only, ignore soft suggestions.
3. Boot-stderr scrape (high-yield): cd ${path} && timeout 8 dazzle serve 2>&1 | grep -iE "registered twice|duplicate|not a text-shaped|TypeError|Traceback|ImportError|ValueError|AttributeError|jinja2\\.exceptions|unresolved|UndefinedError" | head -15 — each matching line IS a bug.
4. Grep the DSL for uses of recently-shipped primitives (rich_text, x-optimistic, x-pull-to-refresh, x-swipe, x-flip, notification, search on, i18n.) and flag any broken-looking USAGE.

${SOFT_ALLOWLIST}

Return {app, status ("OK" or "<N> issues"), bugs:[{severity, signature, detail, evidence}], soft:[...]}. If a candidate matches the soft allowlist, put it in soft, not bugs.`;
};

phase("Sweep");

const results = await parallel(
  apps.map(
    (p) => () =>
      agent(fuzzPrompt(p), {
        label: `fuzz:${p.split("/").filter(Boolean).pop()}`,
        phase: "Sweep",
        agentType: "Explore",
        schema: APP_SCHEMA,
      }),
  ),
);

return { apps: results.filter(Boolean) };
