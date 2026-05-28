export const meta = {
  name: "xproject",
  description:
    "Cross-project read-only quality scan: one agent per Dazzle-based sibling project, fanned out in parallel",
  phases: [{ title: "Scan", detail: "one read-only scan agent per project" }],
};

const PROJECT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    project: { type: "string" },
    path: { type: "string" },
    entities: { type: "integer" },
    surfaces: { type: "integer" },
    health: {
      type: "integer",
      description: "0-100, or -1 if pulse unavailable",
    },
    findings: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          severity: { type: "string", enum: ["critical", "warning", "info"] },
          source: {
            type: "string",
            description: "validate | lint | sentinel | pulse | discovery",
          },
          description: { type: "string" },
        },
        required: ["severity", "source", "description"],
      },
    },
  },
  required: ["project", "path", "entities", "surfaces", "health", "findings"],
};

// Main loop scouts `ls /Volumes/SSD/*/dazzle.toml` and passes the project root paths as args.
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

const projects = coerceList(args);
if (!projects.length) {
  log(
    `No project paths resolved from args (type=${typeof args}). Pass a JSON array of project roots.`,
  );
  return { projects: [] };
}

const scanPrompt = (path) =>
  `Scan the Dazzle-based project at ${path} for quality issues. Read-only — make NO changes.

1. Read ${path}/dazzle.toml (name, entity count, surface count).
2. cd ${path} && dazzle validate — if it fails, record ONE critical finding (source=validate) and skip the remaining steps.
3. cd ${path} && dazzle lint — record violations as warning (source=lint).
4. Select the project via the dazzle MCP (mcp__dazzle__select_project, reachable through ToolSearch) with this path.
5. mcp__dazzle__sentinel operation=scan — high/critical → warning, medium/low → info (source=sentinel).
6. mcp__dazzle__pulse operation=run — extract overall health + per-axis; axis <60 → warning, 60-79 → info (source=pulse). If pulse is unavailable, set health=-1.
7. mcp__dazzle__discovery operation=coherence — record gaps as warning (source=discovery).

Return {project, path, entities, surfaces, health, findings:[{severity, source, description}]} (findings=[] if clean).`;

phase("Scan");

const results = await parallel(
  projects.map(
    (p) => () =>
      agent(scanPrompt(p), {
        label: `scan:${p.split("/").filter(Boolean).pop()}`,
        phase: "Scan",
        schema: PROJECT_SCHEMA,
      }),
  ),
);

return { projects: results.filter(Boolean) };
