"""``dazzle spec`` — narrative-spec ↔ DSL drift commands (#1106, Proposal 1).

Distinct from ``dazzle specs`` (with the trailing s, which generates API
specifications). This subcommand group operates on the *product spec* —
the human-readable ``spec/*.md`` / ``SPEC.md`` content that describes
what the app is supposed to be — and reports drift against the actual
DSL state.

The first command in the group is ``status``: a read-only drift report
that lists entities present in the DSL but unmentioned in the spec,
plus candidate entity names present in the spec but absent from the
DSL. ``sync`` (Proposal 2) and a commit-guard (Proposal 3) live in
follow-up PRs.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import typer

from dazzle.core import ir
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.spec_loader import load_spec
from dazzle.core.strings import to_api_plural
from dazzle.spec_narrative import SpecBrief, brief_fingerprint, build_brief

logger = logging.getLogger(__name__)

spec_app = typer.Typer(
    help="Compare narrative product spec against DSL state — drift detection.",
    no_args_is_help=True,
)


# Entities the framework injects on every project (admin dashboard, AI job
# tracking, feedback widget). They aren't user-modelled domain entities and
# shouldn't surface as drift just because a project's spec doesn't document
# them. Kept in sync with `src/dazzle/core/admin_builder.py`. Override the
# filter with ``--include-framework-entities``.
_FRAMEWORK_INJECTED_ENTITIES = frozenset(
    {
        "AIJob",
        "DeployHistory",
        "FeedbackReport",
        "OnboardingState",  # v0.71.1 — auto-injected when any `guide` is declared
        "SystemHealth",
        "SystemMetric",
    }
)


# Common English words that look like entity candidates but aren't.
# Conservative — anything that's plausibly a domain noun stays in.
_NON_ENTITY_TITLECASE = frozenset(
    {
        "App",
        "Application",
        "System",
        "Platform",
        "Service",
        "Overview",
        "Summary",
        "Introduction",
        "Background",
        "Note",
        "Notes",
        "Example",
        "Examples",
        "Features",
        "Requirements",
        "Section",
        "Part",
        "Chapter",
        "Appendix",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "Today",
        "Tomorrow",
        "Yesterday",
        "Week",
        "Month",
        "Year",
        "Day",
        "Hour",
        "Minute",
        "Second",
        "Now",
        "Then",
        "Next",
        "Previous",
        "First",
        "Last",
        "The",
        "This",
        "That",
        "These",
        "Those",
        "We",
        "They",
        "Our",
        "Your",
        "Its",
        "If",
        "Unless",
        "Whether",
        "Either",
        "Neither",
        # Document/auth/admin terms that are TitleCase but not domain entities
        "Admin",
        "Administrator",
        "Behavior",
        "Boolean",
        "True",
        "False",
        "Yes",
        "No",
        # State/lifecycle words that get TitleCased mid-sentence (avoid
        # flagging them as "missing entities" when they're really values)
        "Active",
        "Inactive",
        "Pending",
        "Approved",
        "Rejected",
        "Cancelled",
        "Canceled",
        "Completed",
        "Failed",
        "Succeeded",
        "Assigned",
        "Unassigned",
        "Open",
        "Closed",
        "Available",
        "Unavailable",
        "Ready",
        "Awaiting",
        # Common process/UI verbs that the regex captures as bare TitleCase
        "Assign",
        "Approve",
        "Reject",
        "Cancel",
        "Complete",
        "Submit",
        "Review",
        "Auto",
        "Manual",
        # Generic verbs/adjectives/prose words that look like entity names
        # but typically aren't. Anything ambiguous (could be a domain noun)
        # is left in so the report still flags it.
        "Access",
        "Action",
        "Attention",
        "Business",
        "Can",
        "Column",
        "Complexity",
        "Configure",
        "Control",
        "Controlled",
        "Create",
        "Current",
        "Currently",
        "Default",
        "Demo",
        "Demonstrated",
        "Display",
        "Do",
        "Done",
        "Each",
        "Enum",
        "Extended",
        "Field",
        "Formatted",
        "Full",
        "Goals",
        "Goal",
        "Has",
        "Have",
        "Helps",
        "Hide",
        "Identifier",
        "Identifiers",
        "Identity",
        "Initial",
        "Initially",
        "Internal",
        "Interaction",
        "Interactions",
        "Likely",
        "Make",
        "Map",
        "Mode",
        "Modes",
        "Never",
        "Number",
        "Optional",
        "Originally",
        "Permission",
        "Permissions",
        "Pre",
        "Process",
        "Property",
        "Public",
        "Quick",
        "Read",
        "Real",
        "Required",
        "Result",
        "Results",
        "Return",
        "Returns",
        "Run",
        "Runs",
        "Search",
        "Set",
        "Sets",
        "Show",
        "Shows",
        "Single",
        "Standard",
        "Start",
        "State",
        "States",
        "Status",
        "Step",
        "Steps",
        "Store",
        "String",
        "Strings",
        "Structure",
        "Sync",
        "Synchronisation",
        "Target",
        "Text",
        "Type",
        "Types",
        "Unique",
        "Up",
        "Update",
        "Updated",
        "Updates",
        "Use",
        "Used",
        "Uses",
        "Using",
        "Valid",
        "Value",
        "Values",
        "View",
        "Views",
        "Visible",
        "Want",
    }
)

_TITLECASE_TOKEN = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b")


# ---------------------------------------------------------------------------
# Domain-map parsing (#1106 Proposal 3 — strict guard)
# ---------------------------------------------------------------------------
#
# The Domain map is a markdown table under a ``## Domain map`` heading in
# ``SPEC.md`` (laid down by ``dazzle init`` since v0.70.46). The strict
# guard requires every DSL entity to appear as an entity name in some row
# of that table — substring matches in prose don't count.
#
# The "Entities" column is the second column by convention; cell values
# are comma-separated entity names. Whitespace and code-fences are stripped.


_DOMAIN_MAP_HEADING = re.compile(r"^##\s+Domain\s+map\s*$", re.IGNORECASE | re.MULTILINE)


def _extract_domain_map_entities(spec_text: str) -> set[str]:
    """Return the set of entity names listed in ``## Domain map`` rows.

    Scans for the ``## Domain map`` heading, then reads the following
    markdown table. The second column ("Entities") holds comma-separated
    entity names; the function strips whitespace, backticks, and the
    leading/trailing pipes.

    Returns an empty set when:
    - No ``## Domain map`` heading is found.
    - The heading exists but has no following table (e.g. placeholder row).
    - The table's second column is the literal placeholder
      ``(populated as you add entities — start in docs/specs/)``.
    """
    match = _DOMAIN_MAP_HEADING.search(spec_text)
    if not match:
        return set()

    # Walk lines after the heading; collect table rows (lines starting
    # with `|`) until we hit a non-table line or another heading.
    tail = spec_text[match.end() :]
    rows: list[list[str]] = []
    for raw in tail.splitlines():
        line = raw.rstrip()
        if line.startswith("##"):
            break
        if not line.startswith("|"):
            # Allow blank lines and the table-separator row to live before
            # the first data row, but bail out the moment we hit prose.
            if line.strip() == "" or set(line.strip()) <= {"-", "|", " ", ":"}:
                continue
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Skip header row (`Domain | Entities | Design doc`) and
        # alignment row (`---|---|---`).
        if cells and all(c == "" or set(c) <= {"-", ":"} for c in cells):
            continue
        rows.append(cells)

    entities: set[str] = set()
    for cells in rows:
        if len(cells) < 2:
            continue
        # Header row check: skip if the second column literally reads
        # ``Entities`` (case-insensitive).
        if cells[1].lower() == "entities":
            continue
        ent_cell = cells[1]
        # The init-scaffold placeholder is "(populated as you add ..."
        if ent_cell.startswith("(populated") or ent_cell.startswith("_(populated"):
            continue
        # Comma-separated entity names; strip surrounding code-fences/asterisks.
        for token in ent_cell.split(","):
            name = token.strip().strip("`*_ ")
            if name and re.match(r"^[A-Z][A-Za-z0-9_]*$", name):
                entities.add(name)
    return entities


@dataclass(frozen=True)
class _DriftReport:
    """One-shot result of comparing the spec to the DSL."""

    dsl_entities: list[str]
    spec_candidates: list[str]
    missing_from_spec: list[str]
    """DSL entities never mentioned (in any form) in the spec."""
    missing_from_dsl: list[str]
    """Capitalized nouns in spec that don't map to a DSL entity."""
    spec_present: bool
    # #1106 Prop 3 — strict guard fields
    domain_map_entities: list[str] = field(default_factory=list)
    """Entity names parsed from rows of ``## Domain map`` in SPEC.md."""
    missing_from_domain_map: list[str] = field(default_factory=list)
    """DSL entities NOT named in any Domain map table row.

    The strict guard fails on this list (when ``[spec] strict = true``).
    Substring mentions elsewhere in SPEC.md don't satisfy the check —
    the entity must be in a row of the Domain map table.
    """


def _extract_entity_candidates(spec_text: str) -> set[str]:
    """Pull plausible entity names from spec text.

    Conservative regex extraction:
    - CamelCase or TitleCase tokens (``Order``, ``OrderItem``)
    - Filter against ``_NON_ENTITY_TITLECASE``
    - Filter tokens that appear only in markdown headers (those are
      structural, not entity mentions)

    Returns the singular form (trailing ``s`` stripped) so we can
    compare directly against DSL entity names which are conventionally
    singular.
    """
    # Header tokens get demoted unless they also appear in body text.
    header_only: set[str] = set()
    body_text_parts: list[str] = []
    for line in spec_text.splitlines():
        if line.lstrip().startswith("#"):
            for tok in _TITLECASE_TOKEN.findall(line):
                header_only.add(tok)
        else:
            body_text_parts.append(line)
    body_text = "\n".join(body_text_parts)
    body_tokens = set(_TITLECASE_TOKEN.findall(body_text))

    candidates: set[str] = set()
    for tok in _TITLECASE_TOKEN.findall(spec_text):
        if tok in _NON_ENTITY_TITLECASE:
            continue
        # Header-only mentions don't count as real spec coverage.
        if tok in header_only and tok not in body_tokens:
            continue
        candidates.add(tok)
    return candidates


def _spec_mentions_entity(entity_name: str, spec_text_lower: str) -> bool:
    """Return True iff the entity appears in the spec under any of the
    common surface forms (singular, plural, hyphenated, snake, kebab).

    Match is case-insensitive against ``spec_text_lower`` (caller is
    responsible for lower-casing once).
    """
    lower = entity_name.lower()
    candidates = {
        lower,
        to_api_plural(entity_name).lower(),
        lower.replace("_", " "),
        lower.replace("_", "-"),
    }
    # Word-boundary check; ``re.search`` with ``\b`` avoids partial hits
    # like ``user`` matching ``username``.
    for form in candidates:
        if re.search(rf"\b{re.escape(form)}\b", spec_text_lower):
            return True
    return False


def _compute_drift(
    appspec: ir.AppSpec,
    spec_text: str,
    *,
    spec_present: bool,
    include_framework_entities: bool = False,
) -> _DriftReport:
    """Build the drift report. Pure function — easy to unit-test."""
    all_entities = [e.name for e in appspec.domain.entities]
    if include_framework_entities:
        dsl_entities = all_entities
    else:
        dsl_entities = [n for n in all_entities if n not in _FRAMEWORK_INJECTED_ENTITIES]
    spec_lower = spec_text.lower()

    missing_from_spec: list[str] = []
    for name in dsl_entities:
        if not _spec_mentions_entity(name, spec_lower):
            missing_from_spec.append(name)

    spec_candidates = _extract_entity_candidates(spec_text)
    # Expand DSL entity names with their plural forms so e.g. ``Orders``
    # in the spec maps to the DSL ``Order`` entity.
    dsl_forms_lower: set[str] = set()
    for name in dsl_entities:
        dsl_forms_lower.add(name.lower())
        dsl_forms_lower.add(to_api_plural(name).lower())
    missing_from_dsl = [c for c in sorted(spec_candidates) if c.lower() not in dsl_forms_lower]

    # #1106 Prop 3 — Domain-map row check (strict mode).
    domain_map_entities = _extract_domain_map_entities(spec_text)
    missing_from_domain_map = sorted(n for n in dsl_entities if n not in domain_map_entities)

    return _DriftReport(
        dsl_entities=sorted(dsl_entities),
        spec_candidates=sorted(spec_candidates),
        missing_from_spec=sorted(missing_from_spec),
        missing_from_dsl=missing_from_dsl,
        spec_present=spec_present,
        domain_map_entities=sorted(domain_map_entities),
        missing_from_domain_map=missing_from_domain_map,
    )


def _format_report(report: _DriftReport) -> str:
    """Human-readable rendering of the drift report."""
    lines: list[str] = []
    lines.append("dazzle spec status")
    lines.append("===================")
    lines.append(f"DSL entities: {len(report.dsl_entities)}")
    if report.spec_present:
        lines.append(f"Spec candidates: {len(report.spec_candidates)}")
    else:
        lines.append("Spec candidates: (no spec/ directory or SPEC.md found)")

    if not report.spec_present:
        lines.append("")
        lines.append(
            "No product spec found. Create spec/<topic>.md or SPEC.md to enable drift detection."
        )
        return "\n".join(lines)

    lines.append("")
    lines.append(f"Missing from spec ({len(report.missing_from_spec)}):")
    if report.missing_from_spec:
        for name in report.missing_from_spec:
            lines.append(f"  - {name}")
    else:
        lines.append("  (none — every DSL entity is mentioned in the spec)")

    lines.append("")
    lines.append(f"Missing from DSL — review candidates ({len(report.missing_from_dsl)}):")
    if report.missing_from_dsl:
        # Heuristic — cap at 30 to keep the report scannable. The full
        # list is available via the JSON output (Proposal 2 follow-up).
        preview_cap = 30
        for name in report.missing_from_dsl[:preview_cap]:
            lines.append(f"  - {name}")
        if len(report.missing_from_dsl) > preview_cap:
            lines.append(
                f"  ... +{len(report.missing_from_dsl) - preview_cap} more "
                "(extend the skip list in dazzle/cli/spec.py to silence "
                "false positives)"
            )
    else:
        lines.append(
            "  (none — every capitalised entity-shaped noun in the spec maps to a DSL entity)"
        )

    # #1106 Prop 3 — strict-mode Domain map check
    lines.append("")
    lines.append(
        f"Domain map entities ({len(report.domain_map_entities)} listed, "
        f"{len(report.missing_from_domain_map)} DSL entities not in any row):"
    )
    if report.missing_from_domain_map:
        for name in report.missing_from_domain_map:
            lines.append(f"  - {name}")
        lines.append(
            "  → Add each to a row of the `## Domain map` table in SPEC.md. "
            "Strict-mode (`[spec] strict = true` in dazzle.toml) fails when "
            "this list is non-empty."
        )
    else:
        lines.append("  (clean — every DSL entity appears in a Domain map row)")
    return "\n".join(lines)


@spec_app.command(name="status")
def spec_status(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory).",
    ),
    fail_on_drift: bool = typer.Option(
        False,
        "--fail-on-drift",
        help="Exit non-zero when any drift is reported. Use in CI gates.",
    ),
    fail_on_strict: bool = typer.Option(
        False,
        "--fail-on-strict",
        help=(
            "Strict guard (#1106 Prop 3). Exits non-zero when any DSL "
            "entity is missing from the `## Domain map` table in SPEC.md, "
            "OR when `[spec] strict = true` is set in dazzle.toml and "
            "the same condition holds. The /ship and /improve agent "
            "loops invoke this before commit so agents can't ship an "
            "undocumented entity. Substring mentions in prose don't "
            "satisfy this check — entity must appear in a table row."
        ),
    ),
    include_framework_entities: bool = typer.Option(
        False,
        "--include-framework-entities",
        help=(
            "Include framework-injected admin entities (AIJob, "
            "DeployHistory, FeedbackReport, SystemHealth, SystemMetric) "
            "in the drift check. Off by default — those entities exist "
            "on every Dazzle project and don't need spec coverage."
        ),
    ),
) -> None:
    """Report drift between the narrative spec and the DSL state.

    Two directions:

    - *Missing from spec* — DSL entities never mentioned (in any form)
      in ``spec/*.md`` / ``SPEC.md``. Suggests the spec is out of date
      relative to what the code actually models.

    - *Missing from DSL* — capitalised entity-shaped nouns in the spec
      that don't map to any DSL entity. Suggests the DSL is out of
      date relative to the documented intent. (Conservative — only
      flags TitleCase tokens that survive a curated false-positive
      filter, so prose like "the System" or "Friday" doesn't fire.)
    """
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        typer.echo(f"Error loading DSL: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    spec_content = load_spec(project_dir)
    report = _compute_drift(
        appspec,
        spec_content.content,
        spec_present=not spec_content.is_empty,
        include_framework_entities=include_framework_entities,
    )
    typer.echo(_format_report(report))

    if fail_on_drift and (report.missing_from_spec or report.missing_from_dsl):
        raise typer.Exit(code=1)

    # #1106 Prop 3 — strict guard. Activated by --fail-on-strict OR by
    # `[spec] strict = true` in the project's dazzle.toml. The agent
    # loop wiring in /ship + /improve uses the CLI flag form; humans
    # who set the manifest flag get the same enforcement on any direct
    # `dazzle spec status` invocation.
    strict_enabled = fail_on_strict or _manifest_strict_enabled(project_dir)
    if strict_enabled and report.missing_from_domain_map:
        typer.echo(
            f"\nSTRICT FAIL: {len(report.missing_from_domain_map)} DSL "
            "entity(ies) not in the Domain map table — add a row in "
            "SPEC.md before commit.",
            err=True,
        )
        raise typer.Exit(code=1)


def _manifest_strict_enabled(project_dir: Path) -> bool:
    """Return True iff ``[spec] strict = true`` in ``project_dir/dazzle.toml``.

    Silently returns False when the manifest is missing or unreadable —
    the manifest flag is an opt-in convenience; the CLI flag is the
    authoritative gate.
    """
    manifest_path = project_dir / "dazzle.toml"
    if not manifest_path.is_file():
        return False
    try:
        from dazzle.core.manifest import load_manifest

        manifest = load_manifest(manifest_path)
        return bool(getattr(manifest.spec, "strict", False))
    except Exception:
        logger.debug(
            "Failed to read [spec] strict from %s — treating as off",
            manifest_path,
            exc_info=True,
        )
        return False


@spec_app.command(name="brief")
def spec_brief(
    project_dir: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory).",
    ),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: 'json' (machine, for /spec-narrate) or 'text' (human preview).",
    ),
    fingerprint: bool = typer.Option(
        False,
        "--fingerprint",
        help="Print only the brief's content hash (the SPECIFICATION.md freshness anchor).",
    ),
) -> None:
    """Emit a deterministic spec brief: verified app facts + activated framework claims.

    Stage 1 of DSL → SPECIFICATION.md. The JSON output is the single source of
    truth for the ``/spec-narrate`` skill, which writes the prose document.
    """
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:  # noqa: BLE001 — surface any load failure to the user
        typer.echo(f"Error loading DSL: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    brief = build_brief(appspec)
    if fingerprint:
        typer.echo(brief_fingerprint(brief))
        return
    if output_format == "text":
        typer.echo(_format_brief_text(brief))
    else:
        typer.echo(brief.model_dump_json(indent=2))


def _format_brief_text(brief: SpecBrief) -> str:
    """Render a compact human-readable preview of the brief."""
    lines: list[str] = [f"SPEC BRIEF — {brief.app_title or brief.app_name}", ""]
    lines.append(f"Domain ({len(brief.domain)} entities):")
    for d in brief.domain:
        states = f" [{', '.join(d.lifecycle_states)}]" if d.lifecycle_states else ""
        lines.append(f"  - {d.title or d.name}{states}")
    lines.append("")
    lines.append(f"Actors ({len(brief.actors)}): " + ", ".join(a.label for a in brief.actors))
    lines.append("")
    lines.append("Activated framework claims:")
    for c in brief.activated_claims:
        lines.append(f"  - [{c.group}] {c.id} (verify: {c.evidence})")
    lines.append("")
    lines.append("Document sections:")
    for s in brief.skeleton:
        mark = "x" if s.populated else " "
        lines.append(f"  [{mark}] {s.section}")
    return "\n".join(lines)
