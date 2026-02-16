"""
DAZZLE Language Server implementation using pygls.

Provides IDE features by analyzing DAZZLE DSL files and using the DAZZLE IR.
"""

import logging
import re
from pathlib import Path
from typing import Any

from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    TEXT_DOCUMENT_HOVER,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionParams,
    DefinitionParams,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentSymbol,
    DocumentSymbolParams,
    Hover,
    HoverParams,
    InitializeParams,
    Location,
    MarkupContent,
    MarkupKind,
    Position,
    PublishDiagnosticsParams,
    Range,
    SymbolKind,
)
from pygls.lsp.server import LanguageServer

from dazzle.core import ir
from dazzle.core.errors import DazzleError, LinkError, ParseError, ValidationError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Custom LanguageServer subclass with workspace state
class DazzleLanguageServer(LanguageServer):
    """Language server with DAZZLE-specific state."""

    def __init__(self, name: str, version: str):
        super().__init__(name, version)
        self.workspace_root: Path | None = None
        self.appspec: ir.AppSpec | None = None


# Create server instance
server = DazzleLanguageServer("dazzle-lsp", "v0.4.0")


@server.feature(INITIALIZE)
def initialize(ls: DazzleLanguageServer, params: InitializeParams) -> Any:
    """Initialize the language server."""
    if params.root_uri:
        ls.workspace_root = Path(params.root_uri.replace("file://", ""))
        logger.info(f"Workspace root: {ls.workspace_root}")

        # Try to load the DAZZLE project
        try:
            _load_project(ls)
        except Exception as e:
            logger.error(f"Failed to load project: {e}")


def _find_project_root(start_path: Path) -> Path | None:
    """Find the nearest directory containing dazzle.toml, searching upward."""
    current = start_path if start_path.is_dir() else start_path.parent
    while current != current.parent:  # Stop at filesystem root
        if (current / "dazzle.toml").exists():
            return current
        current = current.parent
    return None


def _make_diagnostic(
    message: str,
    line: int = 0,
    col: int = 0,
    severity: DiagnosticSeverity = DiagnosticSeverity.Error,
    source: str = "dazzle",
) -> Diagnostic:
    """Create an LSP Diagnostic at the given location."""
    # LSP lines/cols are 0-indexed; our errors are 1-indexed
    lsp_line = max(0, line - 1)
    lsp_col = max(0, col - 1)
    return Diagnostic(
        range=Range(
            start=Position(line=lsp_line, character=lsp_col),
            end=Position(line=lsp_line, character=lsp_col + 1),
        ),
        message=message,
        severity=severity,
        source=source,
    )


def _diagnostics_from_error(error: DazzleError) -> dict[str, list[Diagnostic]]:
    """Extract diagnostics grouped by file URI from a DazzleError."""
    severity = DiagnosticSeverity.Error
    if isinstance(error, (LinkError, ValidationError)):
        severity = DiagnosticSeverity.Warning

    result: dict[str, list[Diagnostic]] = {}

    if error.context and error.context.file:
        uri = error.context.file.as_uri()
        diag = _make_diagnostic(
            message=error.message,
            line=error.context.line,
            col=error.context.column,
            severity=severity,
        )
        result.setdefault(uri, []).append(diag)
    else:
        # No file context — try to extract file:line from the message text
        # or attach to a fallback URI
        diag = _make_diagnostic(message=error.message, severity=severity)
        result.setdefault("__fallback__", []).append(diag)

    return result


def _publish_diagnostics(ls: DazzleLanguageServer, uri: str, diagnostics: list[Diagnostic]) -> None:
    """Publish diagnostics to the client for a single file."""
    ls.text_document_publish_diagnostics(PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics))


def _publish_file_diagnostics(
    ls: DazzleLanguageServer,
    file_diagnostics: dict[str, list[Diagnostic]],
    all_uris: set[str],
) -> None:
    """Publish diagnostics for all tracked files, clearing those without errors."""
    # Publish errors for files that have them
    for uri, diags in file_diagnostics.items():
        if uri == "__fallback__":
            continue
        all_uris.discard(uri)
        _publish_diagnostics(ls, uri, diags)

    # Clear diagnostics for files that parsed successfully
    for uri in all_uris:
        _publish_diagnostics(ls, uri, [])


def _load_project(ls: DazzleLanguageServer, file_path: Path | None = None) -> None:
    """Load DAZZLE project and build AppSpec.

    Args:
        ls: Language server instance
        file_path: Optional file path to search from (for finding project root)
    """
    # Try to find project root from file path first, then workspace root
    project_root = None
    if file_path:
        project_root = _find_project_root(file_path)
    if not project_root and ls.workspace_root:
        project_root = _find_project_root(ls.workspace_root)

    if not project_root:
        if ls.workspace_root:
            logger.warning(f"No dazzle.toml found in {ls.workspace_root} or parent directories")
        return

    manifest_path = project_root / "dazzle.toml"

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, mf)

        # Track all DSL file URIs so we can clear diagnostics on success
        all_uris = {f.resolve().as_uri() for f in dsl_files}

        modules = parse_modules(dsl_files)
        ls.appspec = build_appspec(modules, mf.project_root)
        logger.info(
            f"Loaded project from {project_root} with {len(ls.appspec.domain.entities)} entities"
        )

        # Publish link warnings if any
        warnings = ls.appspec.metadata.get("link_warnings", [])
        file_diagnostics: dict[str, list[Diagnostic]] = {}
        if warnings and file_path:
            uri = file_path.resolve().as_uri()
            for msg in warnings:
                diag = _make_diagnostic(
                    message=msg,
                    severity=DiagnosticSeverity.Information,
                )
                file_diagnostics.setdefault(uri, []).append(diag)

        # Clear diagnostics on all DSL files (project is valid)
        _publish_file_diagnostics(ls, file_diagnostics, all_uris)

    except (ParseError, LinkError, ValidationError) as e:
        logger.error(f"Project error: {e}")
        ls.appspec = None

        # Publish diagnostics for the error
        file_diagnostics = _diagnostics_from_error(e)

        # If the error has no file context, attach to the triggering file
        fallback_diags = file_diagnostics.pop("__fallback__", [])
        if fallback_diags and file_path:
            uri = file_path.resolve().as_uri()
            file_diagnostics.setdefault(uri, []).extend(fallback_diags)

        for uri, diags in file_diagnostics.items():
            _publish_diagnostics(ls, uri, diags)

    except Exception as e:
        logger.error(f"Error loading project: {e}")
        ls.appspec = None


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: DazzleLanguageServer, params: DidOpenTextDocumentParams) -> None:
    """Handle document open."""
    logger.info(f"Opened: {params.text_document.uri}")

    # If we don't have an appspec yet, try to load from this file's location
    if not ls.appspec:
        file_path = Path(params.text_document.uri.replace("file://", ""))
        _load_project(ls, file_path)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: DazzleLanguageServer, params: DidChangeTextDocumentParams) -> None:
    """Handle document change."""
    # Reload project on change
    try:
        file_path = Path(params.text_document.uri.replace("file://", ""))
        _load_project(ls, file_path)
    except Exception as e:
        logger.error(f"Error reloading project: {e}")


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: DazzleLanguageServer, params: DidSaveTextDocumentParams) -> None:
    """Handle document save."""
    logger.info(f"Saved: {params.text_document.uri}")
    # Reload project on save
    try:
        file_path = Path(params.text_document.uri.replace("file://", ""))
        _load_project(ls, file_path)
    except Exception as e:
        logger.error(f"Error reloading project: {e}")


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: DazzleLanguageServer, params: DidCloseTextDocumentParams) -> None:
    """Handle document close."""
    logger.info(f"Closed: {params.text_document.uri}")
    # Clear diagnostics for the closed file
    _publish_diagnostics(ls, params.text_document.uri, [])


def _build_name_index(appspec: ir.AppSpec) -> dict[str, tuple[str, Any]]:
    """Build a name → (construct_type, spec) index from AppSpec.

    This enables O(1) lookup for hover and completion across all construct types.
    """
    index: dict[str, tuple[str, Any]] = {}

    for entity in appspec.domain.entities:
        index[entity.name] = ("entity", entity)
    for surface in appspec.surfaces:
        index[surface.name] = ("surface", surface)
    for workspace in appspec.workspaces:
        index[workspace.name] = ("workspace", workspace)
    for experience in appspec.experiences:
        index[experience.name] = ("experience", experience)
    for service in appspec.domain_services:
        index[service.name] = ("service", service)
    for fm in appspec.foreign_models:
        index[fm.name] = ("foreign_model", fm)
    for integration in appspec.integrations:
        index[integration.name] = ("integration", integration)
    for view in appspec.views:
        index[view.name] = ("view", view)
    for enum in appspec.enums:
        index[enum.name] = ("enum", enum)
    for process in appspec.processes:
        index[process.name] = ("process", process)
    for story in appspec.stories:
        # Stories use story_id as the identifier
        sid = getattr(story, "story_id", None) or getattr(story, "name", None)
        if sid:
            index[sid] = ("story", story)
    for persona in appspec.personas:
        pid = getattr(persona, "id", None) or getattr(persona, "name", None)
        if pid:
            index[pid] = ("persona", persona)
    for scenario in appspec.scenarios:
        sid = getattr(scenario, "id", None) or getattr(scenario, "name", None)
        if sid:
            index[sid] = ("scenario", scenario)
    for ledger in appspec.ledgers:
        index[ledger.name] = ("ledger", ledger)
    for transaction in appspec.transactions:
        index[transaction.name] = ("transaction", transaction)
    for schedule in appspec.schedules:
        index[schedule.name] = ("schedule", schedule)
    for webhook in appspec.webhooks:
        index[webhook.name] = ("webhook", webhook)
    for approval in appspec.approvals:
        index[approval.name] = ("approval", approval)
    for sla in appspec.slas:
        index[sla.name] = ("sla", sla)
    for island in appspec.islands:
        index[island.name] = ("island", island)
    for channel in appspec.channels:
        index[channel.name] = ("channel", channel)
    for llm_model in appspec.llm_models:
        index[llm_model.name] = ("llm_model", llm_model)
    for llm_intent in appspec.llm_intents:
        index[llm_intent.name] = ("llm_intent", llm_intent)
    for archetype in appspec.archetypes:
        index[archetype.name] = ("archetype", archetype)

    return index


def _format_generic_hover(construct_type: str, spec: Any) -> str:
    """Format a generic hover for any named construct."""
    name = getattr(spec, "name", None) or getattr(spec, "id", "unknown")
    title = getattr(spec, "title", None) or getattr(spec, "description", None)

    lines = [f"**{construct_type}** `{name}`"]
    if title:
        lines.append(f"_{title}_")
    lines.append("")

    # Show key properties based on construct type
    if construct_type == "view":
        source = getattr(spec, "source_entity", None)
        if source:
            lines.append(f"**Source entity:** `{source}`")
        fields = getattr(spec, "fields", None)
        if fields:
            lines.append(f"**Fields:** {len(fields)}")
    elif construct_type == "enum":
        values = getattr(spec, "values", None)
        if values:
            preview = ", ".join(getattr(v, "name", str(v)) for v in values[:6])
            if len(values) > 6:
                preview += ", ..."
            lines.append(f"**Values:** {preview}")
    elif construct_type == "process":
        states = getattr(spec, "states", None)
        if states:
            state_names = [s if isinstance(s, str) else getattr(s, "name", str(s)) for s in states]
            lines.append(f"**States:** {', '.join(state_names[:6])}")
        implements = getattr(spec, "implements", None)
        if implements:
            lines.append(f"**Implements:** {', '.join(implements)}")
    elif construct_type == "story":
        actor = getattr(spec, "actor", None)
        if actor:
            lines.append(f"**Actor:** {actor}")
        steps = getattr(spec, "steps", None)
        if steps:
            lines.append(f"**Steps:** {len(steps)}")
    elif construct_type == "persona":
        goals = getattr(spec, "goals", None)
        if goals:
            lines.append(f"**Goals:** {', '.join(goals[:3])}")
        proficiency = getattr(spec, "proficiency", None)
        if proficiency:
            lines.append(f"**Proficiency:** {proficiency}")
    elif construct_type == "ledger":
        account_type = getattr(spec, "account_type", None)
        currency = getattr(spec, "currency", None)
        if account_type:
            lines.append(f"**Account type:** {account_type}")
        if currency:
            lines.append(f"**Currency:** {currency}")
    elif construct_type == "transaction":
        execution = getattr(spec, "execution", None)
        transfers = getattr(spec, "transfers", None)
        if execution:
            lines.append(f"**Execution:** {execution}")
        if transfers:
            lines.append(f"**Transfers:** {len(transfers)}")
    elif construct_type == "webhook":
        events = getattr(spec, "events", None)
        if events:
            lines.append(f"**Events:** {', '.join(events[:4])}")
    elif construct_type == "approval":
        approver_role = getattr(spec, "approver_role", None)
        if approver_role:
            lines.append(f"**Approver role:** {approver_role}")
    elif construct_type == "sla":
        threshold = getattr(spec, "threshold", None)
        if threshold:
            lines.append(f"**Threshold:** {threshold}")
    elif construct_type == "island":
        framework = getattr(spec, "framework", None)
        if framework:
            lines.append(f"**Framework:** {framework}")
    elif construct_type == "workspace":
        stages = getattr(spec, "stages", None)
        if stages:
            lines.append(f"**Stages:** {len(stages)}")
    elif construct_type == "experience":
        steps = getattr(spec, "steps", None)
        if steps:
            lines.append(f"**Steps:** {len(steps)}")
    elif construct_type in ("service", "integration"):
        kind = getattr(spec, "kind", None)
        if kind:
            lines.append(f"**Kind:** {kind}")
    elif construct_type == "schedule":
        cron = getattr(spec, "cron", None)
        interval = getattr(spec, "interval", None)
        if cron:
            lines.append(f"**Cron:** `{cron}`")
        if interval:
            lines.append(f"**Interval:** {interval}")

    return "\n".join(lines)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: DazzleLanguageServer, params: HoverParams) -> Hover | None:
    """Provide hover information."""
    if not ls.appspec:
        return None

    # Get the word at cursor position
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(document.source, params.position)

    if not word:
        return None

    # Build name index for O(1) lookup
    index = _build_name_index(ls.appspec)
    match = index.get(word)
    if not match:
        return None

    construct_type, spec = match

    # Use rich formatters for entity and surface, generic for others
    if construct_type == "entity":
        content = _format_entity_hover(spec)
    elif construct_type == "surface":
        content = _format_surface_hover(spec)
    else:
        content = _format_generic_hover(construct_type, spec)

    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=content))


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: DazzleLanguageServer, params: DefinitionParams) -> Location | None:
    """Provide go-to-definition."""
    if not ls.appspec or not ls.workspace_root:
        return None

    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(document.source, params.position)

    if not word:
        return None

    # Search for construct definition in DSL files
    manifest_path = ls.workspace_root / "dazzle.toml"
    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(ls.workspace_root, mf)

        for dsl_file in dsl_files:
            location = _find_definition_in_file(dsl_file, word)
            if location:
                return location
    except Exception as e:
        logger.error(f"Error finding definition: {e}")

    return None


def _detect_inline_context(prefix: str) -> str | None:
    """Check for inline completion triggers on the current line.

    Returns a context string if a trigger is found, or None.
    """
    if re.search(r"\bmode\s*:\s*$", prefix):
        return "mode_value"
    if re.search(r"\bref\s+$", prefix):
        return "ref_target"
    if re.search(r"\buses\s+entity\s+$", prefix):
        return "ref_target"
    if re.search(r"\bsource\s*:\s*$", prefix):
        return "source_target"
    if re.search(r"->\s*$", prefix):
        return "transition_target"
    return None


def _detect_enclosing_block(lines: list[str], from_line: int) -> str:
    """Walk backwards to find the enclosing construct keyword.

    Returns a block context string: "entity_block", "surface_block",
    "process_block", or "global".
    """
    for i in range(from_line, -1, -1):
        m = _CONSTRUCT_RE.match(lines[i])
        if m:
            keyword = m.group(2)
            if keyword == "entity":
                return "entity_block"
            elif keyword == "surface":
                return "surface_block"
            elif keyword == "process":
                return "process_block"
            else:
                return "global"
    return "global"


def _detect_completion_context(text: str, line: int, character: int) -> str:
    """Detect the completion context from cursor position.

    Returns a context string:
      "top_level" — at column 0, suggest construct keywords
      "mode_value" — after "mode:", suggest mode values
      "ref_target" — after "ref" or "uses entity", suggest entity names
      "source_target" — after "source:", suggest view names
      "transition_target" — after "->", suggest surface/experience names
      "entity_block" — inside an entity, suggest field types + modifiers
      "surface_block" — inside a surface, suggest surface sub-keywords
      "process_block" — inside a process, suggest process sub-keywords
      "global" — fallback: all names + types + modifiers
    """
    lines = text.split("\n")
    if line >= len(lines):
        return "global"

    current_line = lines[line]
    prefix = current_line[:character]

    # Check current line patterns first
    inline = _detect_inline_context(prefix)
    if inline is not None:
        return inline

    # Check indentation level — column 0 means top-level
    indent = len(current_line) - len(current_line.lstrip())
    if indent == 0 and not prefix.strip():
        return "top_level"

    # Look at enclosing construct to determine block context
    if indent > 0:
        return _detect_enclosing_block(lines, line - 1)

    return "global"


_FIELD_TYPES = [
    "uuid",
    "str",
    "int",
    "float",
    "bool",
    "date",
    "datetime",
    "time",
    "text",
    "json",
    "ref",
    "enum",
    "money",
    "file",
    "email",
    "decimal",
    "computed",
]

_FIELD_MODIFIERS = [
    "required",
    "unique",
    "pk",
    "optional",
    "auto_add",
    "auto_update",
    "readonly",
    "index",
]

_CONSTRUCT_KEYWORDS = [
    "entity",
    "surface",
    "workspace",
    "experience",
    "service",
    "integration",
    "foreign_model",
    "view",
    "enum",
    "process",
    "story",
    "persona",
    "scenario",
    "ledger",
    "transaction",
    "schedule",
    "webhook",
    "approval",
    "sla",
    "policy",
    "island",
    "channel",
    "archetype",
    "flow",
]

_MODE_VALUES = ["list", "view", "create", "edit", "delete", "custom"]

_SURFACE_SUBKEYWORDS = [
    "section",
    "action",
    "field",
    "mode",
    "uses",
    "source",
    "filter",
    "sort",
    "display",
    "search",
    "empty",
]

_PROCESS_SUBKEYWORDS = [
    "state",
    "transition",
    "step",
    "trigger",
    "guard",
    "parallel",
    "subprocess",
    "human_task",
    "compensate",
    "on_success",
    "on_failure",
]


NameIndex = dict[str, tuple[str, Any]]


def _complete_top_level() -> list[CompletionItem]:
    """Suggest construct keywords at the top level."""
    return [
        CompletionItem(label=kw, kind=CompletionItemKind.Keyword, detail="Construct")
        for kw in _CONSTRUCT_KEYWORDS
    ]


def _complete_mode_value() -> list[CompletionItem]:
    """Suggest mode values after 'mode:'."""
    return [
        CompletionItem(label=mode, kind=CompletionItemKind.EnumMember, detail="Mode")
        for mode in _MODE_VALUES
    ]


def _complete_ref_target(index: NameIndex) -> list[CompletionItem]:
    """Suggest entity names for 'ref' or 'uses entity'."""
    return [
        CompletionItem(
            label=name,
            kind=CompletionItemKind.Class,
            detail="Entity",
            documentation=getattr(spec, "title", name),
        )
        for name, (ctype, spec) in index.items()
        if ctype == "entity"
    ]


def _complete_source_target(index: NameIndex) -> list[CompletionItem]:
    """Suggest view names after 'source:'."""
    return [
        CompletionItem(
            label=name,
            kind=CompletionItemKind.TypeParameter,
            detail="View",
            documentation=getattr(spec, "title", name),
        )
        for name, (ctype, spec) in index.items()
        if ctype == "view"
    ]


def _complete_transition_target(index: NameIndex) -> list[CompletionItem]:
    """Suggest surface and experience names after '->'."""
    return [
        CompletionItem(
            label=name,
            kind=CompletionItemKind.Interface
            if ctype == "surface"
            else CompletionItemKind.Function,
            detail=ctype.title(),
            documentation=getattr(spec, "title", name),
        )
        for name, (ctype, spec) in index.items()
        if ctype in ("surface", "experience")
    ]


def _complete_entity_block(index: NameIndex) -> list[CompletionItem]:
    """Suggest field types, modifiers, and entity names inside an entity block."""
    items: list[CompletionItem] = []
    for ft in _FIELD_TYPES:
        items.append(CompletionItem(label=ft, kind=CompletionItemKind.Keyword, detail="Field type"))
    for mod in _FIELD_MODIFIERS:
        items.append(CompletionItem(label=mod, kind=CompletionItemKind.Keyword, detail="Modifier"))
    for name, (ctype, _) in index.items():
        if ctype == "entity":
            items.append(
                CompletionItem(
                    label=name, kind=CompletionItemKind.Class, detail="Entity (ref target)"
                )
            )
    return items


def _complete_surface_block(index: NameIndex) -> list[CompletionItem]:
    """Suggest surface sub-keywords and referenceable names inside a surface block."""
    items: list[CompletionItem] = [
        CompletionItem(label=kw, kind=CompletionItemKind.Keyword, detail="Surface keyword")
        for kw in _SURFACE_SUBKEYWORDS
    ]
    for name, (ctype, spec) in index.items():
        if ctype in ("entity", "view", "surface", "experience"):
            items.append(
                CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Class,
                    detail=ctype.title(),
                    documentation=getattr(spec, "title", name),
                )
            )
    return items


def _complete_process_block() -> list[CompletionItem]:
    """Suggest process sub-keywords inside a process block."""
    return [
        CompletionItem(label=kw, kind=CompletionItemKind.Keyword, detail="Process keyword")
        for kw in _PROCESS_SUBKEYWORDS
    ]


def _complete_global(index: NameIndex) -> list[CompletionItem]:
    """Global fallback — all names, field types, and modifiers."""
    items: list[CompletionItem] = []
    for name, (ctype, spec) in index.items():
        title = getattr(spec, "title", None) or getattr(spec, "description", None)
        items.append(
            CompletionItem(
                label=name,
                kind=CompletionItemKind.Text,
                detail=ctype.replace("_", " ").title(),
                documentation=title or name,
            )
        )
    for ft in _FIELD_TYPES:
        items.append(CompletionItem(label=ft, kind=CompletionItemKind.Keyword, detail="Field type"))
    for mod in _FIELD_MODIFIERS:
        items.append(CompletionItem(label=mod, kind=CompletionItemKind.Keyword, detail="Modifier"))
    return items


_COMPLETION_DISPATCHERS: dict[str, Any] = {
    "top_level": lambda _idx: _complete_top_level(),
    "mode_value": lambda _idx: _complete_mode_value(),
    "ref_target": _complete_ref_target,
    "source_target": _complete_source_target,
    "transition_target": _complete_transition_target,
    "entity_block": _complete_entity_block,
    "surface_block": _complete_surface_block,
    "process_block": lambda _idx: _complete_process_block(),
}


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completion(ls: DazzleLanguageServer, params: CompletionParams) -> CompletionList | None:
    """Provide context-aware completion suggestions."""
    if not ls.appspec:
        return None

    document = ls.workspace.get_text_document(params.text_document.uri)
    ctx = _detect_completion_context(
        document.source, params.position.line, params.position.character
    )

    index = _build_name_index(ls.appspec)
    dispatcher = _COMPLETION_DISPATCHERS.get(ctx)
    items = dispatcher(index) if dispatcher else _complete_global(index)

    return CompletionList(is_incomplete=False, items=items)


# All DSL construct keywords that start a named block: keyword name "Title":
_CONSTRUCT_KW_PATTERN = (
    "entity|surface|experience|service|workspace|archetype|flow|integration|"
    "foreign_model|view|enum|process|story|persona|scenario|ledger|transaction|"
    "schedule|webhook|approval|sla|policy|island|channel|event_model|"
    "llm_model|llm_config|llm_intent"
)

# Regex: keyword  name  optional("Title")  colon
_CONSTRUCT_RE = re.compile(
    rf"^(\s*)({_CONSTRUCT_KW_PATTERN})\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\"([^\"]*)\")?\s*:"
)

# Regex for child elements (fields, sections, actions, steps, states, etc.)
_CHILD_RE = re.compile(
    r"^(\s+)(?:(field|section|action|step|state|transfer|transition|tier)\s+)"
    r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\"([^\"]*)\")?"
)

# Regex for entity field declarations: indented  name: type
_FIELD_RE = re.compile(r"^(\s+)([a-zA-Z_][a-zA-Z0-9_]*)\s*:")

# Map construct keyword to SymbolKind
_CONSTRUCT_SYMBOL_KIND: dict[str, SymbolKind] = {
    "entity": SymbolKind.Class,
    "surface": SymbolKind.Interface,
    "workspace": SymbolKind.Module,
    "experience": SymbolKind.Function,
    "service": SymbolKind.Method,
    "process": SymbolKind.Event,
    "story": SymbolKind.Struct,
    "persona": SymbolKind.Object,
    "scenario": SymbolKind.Struct,
    "view": SymbolKind.TypeParameter,
    "enum": SymbolKind.Enum,
    "ledger": SymbolKind.Class,
    "transaction": SymbolKind.Function,
    "schedule": SymbolKind.Event,
    "webhook": SymbolKind.Event,
    "approval": SymbolKind.Operator,
    "sla": SymbolKind.Constant,
    "policy": SymbolKind.Key,
    "island": SymbolKind.Package,
    "integration": SymbolKind.Interface,
    "foreign_model": SymbolKind.Class,
    "archetype": SymbolKind.Class,
    "flow": SymbolKind.Function,
    "channel": SymbolKind.Event,
    "event_model": SymbolKind.Event,
    "llm_model": SymbolKind.Variable,
    "llm_config": SymbolKind.Variable,
    "llm_intent": SymbolKind.Function,
}

# Map child keyword to SymbolKind
_CHILD_SYMBOL_KIND: dict[str, SymbolKind] = {
    "field": SymbolKind.Field,
    "section": SymbolKind.Namespace,
    "action": SymbolKind.Method,
    "step": SymbolKind.Function,
    "state": SymbolKind.EnumMember,
    "transfer": SymbolKind.Function,
    "transition": SymbolKind.Operator,
    "tier": SymbolKind.Constant,
}


def _scan_document_symbols(text: str) -> list[DocumentSymbol]:
    """Scan document text to extract symbols with correct positions.

    This scans line-by-line using regex to find construct declarations and
    their children, using indentation to determine parent-child relationships.
    """
    lines = text.split("\n")
    symbols: list[DocumentSymbol] = []
    current_construct: DocumentSymbol | None = None

    for line_no, line in enumerate(lines):
        # Check for top-level construct declaration
        m = _CONSTRUCT_RE.match(line)
        if m:
            indent_str, keyword, name, title = m.groups()

            # Finish previous construct's range
            if current_construct is not None:
                _close_symbol_range(current_construct, line_no - 1, lines)

            sym_kind = _CONSTRUCT_SYMBOL_KIND.get(keyword, SymbolKind.Variable)
            sel_start = len(indent_str) + len(keyword) + 1  # after "keyword "
            sel_end = sel_start + len(name)

            sym = DocumentSymbol(
                name=name,
                kind=sym_kind,
                range=Range(
                    start=Position(line=line_no, character=0),
                    end=Position(line=line_no, character=len(line)),
                ),
                selection_range=Range(
                    start=Position(line=line_no, character=sel_start),
                    end=Position(line=line_no, character=sel_end),
                ),
                detail=f"{keyword}" + (f" — {title}" if title else ""),
                children=[],
            )

            symbols.append(sym)
            current_construct = sym
            continue

        # If we're inside a construct, look for children
        if current_construct is not None:
            # Check for named children (field, section, action, step, state, etc.)
            cm = _CHILD_RE.match(line)
            if cm:
                child_indent, child_keyword, child_name, child_title = cm.groups()
                child_kind = _CHILD_SYMBOL_KIND.get(child_keyword, SymbolKind.Field)
                sel_start = len(child_indent) + len(child_keyword) + 1
                sel_end = sel_start + len(child_name)

                child_sym = DocumentSymbol(
                    name=child_name,
                    kind=child_kind,
                    range=Range(
                        start=Position(line=line_no, character=0),
                        end=Position(line=line_no, character=len(line)),
                    ),
                    selection_range=Range(
                        start=Position(line=line_no, character=sel_start),
                        end=Position(line=line_no, character=sel_end),
                    ),
                    detail=child_keyword + (f" — {child_title}" if child_title else ""),
                )
                children = list(current_construct.children or [])
                children.append(child_sym)
                current_construct.children = children
                continue

            # For entities, also detect field declarations (name: type)
            if current_construct.kind == SymbolKind.Class:
                fm = _FIELD_RE.match(line)
                if fm:
                    field_indent, field_name = fm.groups()
                    # Skip keywords that look like fields but aren't
                    if field_name not in (
                        "id",
                        "index",
                        "constraint",
                        "invariant",
                        "mode",
                        "uses",
                        "source",
                        "intent",
                        "domain",
                        "patterns",
                        "extends",
                        "access",
                    ):
                        sel_start = len(field_indent)
                        sel_end = sel_start + len(field_name)
                        field_sym = DocumentSymbol(
                            name=field_name,
                            kind=SymbolKind.Field,
                            range=Range(
                                start=Position(line=line_no, character=0),
                                end=Position(line=line_no, character=len(line)),
                            ),
                            selection_range=Range(
                                start=Position(line=line_no, character=sel_start),
                                end=Position(line=line_no, character=sel_end),
                            ),
                            detail="",
                        )
                        children = list(current_construct.children or [])
                        children.append(field_sym)
                        current_construct.children = children

    # Close the last construct
    if current_construct is not None:
        _close_symbol_range(current_construct, len(lines) - 1, lines)

    return symbols


def _close_symbol_range(symbol: DocumentSymbol, end_line: int, lines: list[str]) -> None:
    """Update a symbol's range to extend to end_line."""
    end_char = len(lines[end_line]) if end_line < len(lines) else 0
    symbol.range = Range(
        start=symbol.range.start,
        end=Position(line=end_line, character=end_char),
    )


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: DazzleLanguageServer, params: DocumentSymbolParams) -> list[DocumentSymbol]:
    """Provide document symbols for outline view."""
    document = ls.workspace.get_text_document(params.text_document.uri)
    return _scan_document_symbols(document.source)


# Helper functions


def _get_word_at_position(text: str, position: Position) -> str | None:
    """Extract word at cursor position."""
    lines = text.split("\n")
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    if position.character >= len(line):
        return None

    # Find word boundaries
    start = position.character
    end = position.character

    # Move backwards to find start
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1

    # Move forwards to find end
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1

    return line[start:end] if start < end else None


def _get_grammar_tips(entity: Any) -> list[str]:
    """Provide DAZZLE DSL grammar-specific tips and examples."""
    tips = []

    # Check what features are being used and suggest related ones
    has_enum = any(field.type.enum_values for field in entity.fields)
    has_ref = any(field.type.ref_entity for field in entity.fields)
    has_index = hasattr(entity, "indexes") and entity.indexes

    # Enum syntax tips
    if has_enum:
        tips.append("📝 **Enum syntax**: `status: enum[draft, published, archived]=draft`")
        tips.append("   • Use brackets `[]` for enum values, not parentheses")
        tips.append("   • Set default with `=default_value`")

    # Reference field tips
    if has_ref:
        tips.append("🔗 **Reference syntax**: `author: ref User required`")
        tips.append("   • References create foreign key relationships")
        tips.append("   • Add `index author` for query performance")

    # Index syntax tips
    if not has_index and len(entity.fields) > 3:
        tips.append(
            "🔍 **Index syntax**: Add after fields: `index field_name` or `index field1,field2`"
        )
        tips.append("   • Single field: `index email`")
        tips.append("   • Composite: `index created_by,status`")

    # Field type tips
    tips.append(
        "📊 **Field types**: `str(max_len)`, `int`, `float(precision,scale)`, `uuid`, `datetime`, `date`, `time`, `bool`, `text`, `json`, `email`"
    )

    # Modifier tips
    tips.append(
        "🏷️ **Modifiers**: `required`, `unique`, `optional`, `pk`, `auto_add`, `auto_update`"
    )
    tips.append("   • Example: `email: email unique required`")

    return tips


def _analyze_entity(entity: Any) -> list[str]:
    """Analyze entity and provide recommendations."""
    recommendations = []

    # Check for missing timestamps
    has_created_at = any(f.name == "created_at" for f in entity.fields)
    has_updated_at = any(f.name == "updated_at" for f in entity.fields)

    if not has_created_at:
        recommendations.append(
            "⏰ Consider adding `created_at: datetime auto_add` to track record creation"
        )
    if not has_updated_at:
        recommendations.append(
            "🔄 Consider adding `updated_at: datetime auto_update` to track modifications"
        )

    # Check for foreign key indexes
    ref_fields_without_index = []
    indexed_fields = set()
    if hasattr(entity, "indexes"):
        for idx in entity.indexes:
            if hasattr(idx, "fields"):
                indexed_fields.update(idx.fields)

    for field in entity.fields:
        if field.type.ref_entity and field.name not in indexed_fields:
            ref_fields_without_index.append(field.name)

    if ref_fields_without_index:
        fields_str = ", ".join(f"`{f}`" for f in ref_fields_without_index[:3])
        recommendations.append(f"🔍 Consider adding indexes on foreign keys: {fields_str}")

    # Check for too many fields
    if len(entity.fields) > 15:
        recommendations.append(
            f"📊 Entity has {len(entity.fields)} fields - consider splitting into related entities"
        )

    # Check for proper naming
    snake_case_issues = [f.name for f in entity.fields if "-" in f.name or " " in f.name]
    if snake_case_issues:
        recommendations.append("🔤 Use snake_case for field names (avoid hyphens and spaces)")

    # Check for unique constraints
    unique_fields = [f.name for f in entity.fields if f.is_unique and not f.is_primary_key]
    if not unique_fields and len(entity.fields) > 3:
        recommendations.append(
            "⭐ Consider adding unique constraints on identifying fields (e.g., email, code)"
        )

    # Check for soft delete pattern
    has_deleted_at = any(f.name in ("deleted_at", "archived_at") for f in entity.fields)
    if not has_deleted_at and len(entity.fields) > 5:
        recommendations.append(
            "🗑️ Consider soft delete pattern: add `deleted_at: datetime optional` for safer record archival"
        )

    return recommendations


def _format_entity_hover(entity: Any) -> str:
    """Format entity information for hover with rich, contextual details."""
    lines = []

    # Header with icon
    lines.append(f"# 📦 Entity: `{entity.name}`")

    if entity.title:
        lines.append(f"_{entity.title}_")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Fields section with detailed information
    lines.append("## Fields")
    lines.append("")

    # Create a table-like format
    lines.append("| Field | Type | Constraints |")
    lines.append("|-------|------|-------------|")

    for field in entity.fields:
        # Format field type with details
        field_type = field.type.kind.value

        # Add length/precision for sized types
        if field.type.max_length:
            field_type = f"{field_type}({field.type.max_length})"
        elif field.type.precision:
            if field.type.scale:
                field_type = f"{field_type}({field.type.precision},{field.type.scale})"
            else:
                field_type = f"{field_type}({field.type.precision})"

        # Format references
        if field.type.ref_entity:
            field_type = f"→ `{field.type.ref_entity}`"

        # Format enum values
        if field.type.enum_values:
            enum_vals = ", ".join(field.type.enum_values[:3])
            if len(field.type.enum_values) > 3:
                enum_vals += ", ..."
            field_type = f"{field_type}[{enum_vals}]"

        # Collect constraints/modifiers
        constraints = []
        if field.is_primary_key:
            constraints.append("🔑 Primary Key")
        if field.is_required:
            constraints.append("✓ Required")
        if field.is_unique:
            constraints.append("⭐ Unique")

        # Check for auto timestamps
        if any("auto_add" in str(m) for m in field.modifiers):
            constraints.append("📅 Auto-add")
        if any("auto_update" in str(m) for m in field.modifiers):
            constraints.append("🔄 Auto-update")

        constraint_str = "<br>".join(constraints) if constraints else "-"

        lines.append(f"| **{field.name}** | `{field_type}` | {constraint_str} |")

    # Add recommendations/advice
    recommendations = _analyze_entity(entity)
    if recommendations:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 🎯 Recommendations")
        lines.append("")
        for rec in recommendations:
            lines.append(f"- {rec}")

    # Add DAZZLE DSL grammar tips
    grammar_tips = _get_grammar_tips(entity)
    if grammar_tips:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 📚 DAZZLE DSL Syntax")
        lines.append("")
        for tip in grammar_tips:
            lines.append(tip)

    # Add helpful context
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**💡 Quick Tips:**")
    lines.append("- Use Cmd+Click (Mac) or Ctrl+Click (Windows) to navigate to references")
    lines.append("- Primary keys are automatically indexed")
    lines.append("- Required fields must have a value when creating records")

    return "\n".join(lines)


def _get_surface_grammar_tips(surface: Any) -> list[str]:
    """Provide DAZZLE DSL grammar tips for surfaces."""
    tips = []

    mode = surface.mode.value if hasattr(surface.mode, "value") else str(surface.mode)

    # Basic surface syntax
    tips.append("📋 **Surface syntax**:")
    tips.append("```")
    tips.append('surface my_surface "Title":')
    tips.append("  uses entity MyEntity")
    tips.append("  mode: list")
    tips.append("```")

    # Section syntax
    tips.append("")
    tips.append("📦 **Section syntax**:")
    tips.append("```")
    tips.append('section main "Main Fields":')
    tips.append('  field name "Name"')
    tips.append('  field status "Status"')
    tips.append("```")

    # Action syntax based on mode
    tips.append("")
    tips.append("⚡ **Action syntax**:")
    if mode == "list":
        tips.append("```")
        tips.append('action create "New":')
        tips.append("  on click -> surface my_create")
        tips.append("")
        tips.append('action view "View":')
        tips.append("  on click -> surface my_detail")
        tips.append("```")
    elif mode == "view":
        tips.append("```")
        tips.append('action edit "Edit":')
        tips.append("  on click -> surface my_edit")
        tips.append("")
        tips.append('action delete "Delete":')
        tips.append("  on submit -> experience my_flow step confirm")
        tips.append("```")
    else:
        tips.append("```")
        tips.append('action submit "Save":')
        tips.append("  on submit -> experience my_flow step success")
        tips.append("```")

    # Experience reference
    tips.append("")
    tips.append("🎬 **Experience reference**: Actions can navigate to experiences:")
    tips.append("   • `on click -> experience flow_name step step_name`")
    tips.append("   • `on submit -> experience flow_name step next_step`")

    return tips


def _analyze_surface(surface: Any) -> list[str]:
    """Analyze surface and provide recommendations."""
    recommendations = []

    mode = surface.mode.value if hasattr(surface.mode, "value") else str(surface.mode)

    # Check for missing sections
    num_sections = len(surface.sections) if hasattr(surface, "sections") and surface.sections else 0

    if num_sections == 0:
        recommendations.append("📋 Add sections to organize fields and improve UX")

    # List surface specific advice
    if mode == "list":
        # Check if key identifying fields are present
        if hasattr(surface, "sections") and surface.sections:
            all_fields = []
            for section in surface.sections:
                if hasattr(section, "fields"):
                    all_fields.extend([f.name for f in section.fields if hasattr(f, "name")])

            if "id" not in all_fields and len(all_fields) > 0:
                recommendations.append(
                    "🔍 Include an ID or identifier field in list view for better navigation"
                )

        recommendations.append(
            "🔎 Consider adding filters section for user-friendly data exploration"
        )
        recommendations.append("📊 Add pagination for better performance with large datasets")

    # Create/Edit surface advice
    elif mode in ("create", "edit"):
        if num_sections < 2 and hasattr(surface, "sections"):
            # Count total fields
            total_fields = sum(
                len(s.fields) if hasattr(s, "fields") else 0 for s in surface.sections
            )
            if total_fields > 5:
                recommendations.append(
                    "📦 Group related fields into multiple sections for better form organization"
                )

        recommendations.append("✅ Add validation rules to ensure data quality")
        recommendations.append("💾 Include clear submit/cancel actions")

    # View surface advice
    elif mode == "view":
        has_actions = hasattr(surface, "actions") and surface.actions and len(surface.actions) > 0

        if not has_actions:
            recommendations.append(
                "⚡ Add actions (edit, delete, etc.) to enable user interactions"
            )

        recommendations.append(
            "🔗 Consider adding related record sections (e.g., comments, history)"
        )

    # Check for missing entity reference
    if not surface.entity_ref:
        recommendations.append("⚠️ Surface should reference an entity with `uses entity EntityName`")

    # Check for actions
    has_actions = hasattr(surface, "actions") and surface.actions and len(surface.actions) > 0
    if not has_actions and mode != "view":
        recommendations.append(
            "🎬 Add actions to define user interactions (buttons, forms, navigation)"
        )

    return recommendations


def _format_surface_hover(surface: Any) -> str:
    """Format surface information for hover with rich, contextual details."""
    lines = []

    # Header with icon
    lines.append(f"# 🎨 Surface: `{surface.name}`")

    if surface.title:
        lines.append(f"_{surface.title}_")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Surface details
    lines.append("## Configuration")
    lines.append("")

    # Mode with description
    mode = surface.mode.value
    mode_descriptions = {
        "list": "📋 Displays multiple records in a list/table view",
        "view": "👁️ Shows details of a single record (read-only)",
        "create": "➕ Form for creating new records",
        "edit": "✏️ Form for editing existing records",
        "delete": "🗑️ Confirmation for deleting records",
    }
    mode_desc = mode_descriptions.get(mode, "📄 Custom surface mode")

    lines.append(f"**Mode:** `{mode}`")
    lines.append(f"> {mode_desc}")
    lines.append("")

    # Entity reference
    if surface.entity_ref:
        lines.append(f"**Entity:** `{surface.entity_ref}`")
        lines.append(f"> This surface operates on **{surface.entity_ref}** records")
        lines.append("")

    # Sections info if available
    if hasattr(surface, "sections") and surface.sections:
        lines.append("## Sections")
        lines.append("")
        for section in surface.sections[:5]:  # Show first 5 sections
            section_name = section.name if hasattr(section, "name") else "unnamed"
            section_title = section.title if hasattr(section, "title") else section_name
            lines.append(f"- **{section_title}** (`{section_name}`)")
        if len(surface.sections) > 5:
            lines.append(f"- _(and {len(surface.sections) - 5} more sections)_")
        lines.append("")

    # Add recommendations/advice
    recommendations = _analyze_surface(surface)
    if recommendations:
        lines.append("---")
        lines.append("")
        lines.append("## 🎯 Recommendations")
        lines.append("")
        for rec in recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    # Add DAZZLE DSL grammar tips for surfaces
    grammar_tips = _get_surface_grammar_tips(surface)
    if grammar_tips:
        lines.append("---")
        lines.append("")
        lines.append("## 📚 DAZZLE DSL Syntax")
        lines.append("")
        for tip in grammar_tips:
            lines.append(tip)
        lines.append("")

    # Add helpful context
    lines.append("---")
    lines.append("")
    lines.append("**💡 Quick Tips:**")

    if mode == "list":
        lines.append("- List surfaces typically include filters and pagination")
        lines.append("- Use sections to organize fields and actions")
    elif mode == "view":
        lines.append("- View surfaces are read-only by default")
        lines.append("- Add actions to enable user interactions")
    elif mode in ("create", "edit"):
        lines.append("- Form surfaces should have clear field labels")
        lines.append("- Group related fields in sections for better UX")

    lines.append("- Use Cmd+Click to navigate to the entity definition")

    return "\n".join(lines)


def _find_definition_in_file(file_path: Path, word: str) -> Location | None:
    """Find definition of word in a DSL file.

    Searches for any construct declaration matching the word using the full
    set of DSL keywords (entity, surface, view, process, ledger, etc.).
    """
    try:
        content = file_path.read_text()
        lines = content.split("\n")

        for line_no, line in enumerate(lines):
            m = _CONSTRUCT_RE.match(line)
            if m and m.group(3) == word:
                keyword = m.group(2)
                # Position selection on the name, not the keyword
                name_start = len(m.group(1)) + len(keyword) + 1
                uri = file_path.as_uri()
                range_ = Range(
                    start=Position(line=line_no, character=name_start),
                    end=Position(line=line_no, character=name_start + len(word)),
                )
                return Location(uri=uri, range=range_)
    except Exception as e:
        logger.error(f"Error searching file {file_path}: {e}")

    return None


def start_server() -> None:
    """Start the DAZZLE LSP server."""
    logger.info("Starting DAZZLE Language Server...")
    server.start_io()


if __name__ == "__main__":
    start_server()
