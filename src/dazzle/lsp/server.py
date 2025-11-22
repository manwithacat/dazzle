"""
DAZZLE Language Server implementation using pygls.

Provides IDE features by analyzing DAZZLE DSL files and using the DAZZLE IR.
"""

import logging
from pathlib import Path
from typing import Optional, List

from pygls.lsp.server import LanguageServer

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DID_CLOSE,
    INITIALIZE,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidSaveTextDocumentParams,
    DidCloseTextDocumentParams,
    InitializeParams,
    HoverParams,
    Hover,
    DefinitionParams,
    Location,
    CompletionParams,
    CompletionList,
    CompletionItem,
    CompletionItemKind,
    DocumentSymbolParams,
    DocumentSymbol,
    SymbolKind,
    Range,
    Position,
    MarkupContent,
    MarkupKind,
)

from dazzle.core.manifest import load_manifest
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.parser import parse_modules
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.errors import DazzleError, ParseError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create server instance
server = LanguageServer("dazzle-lsp", "v0.3.0")

# Store workspace state on server
server.workspace_root: Optional[Path] = None
server.appspec = None


@server.feature(INITIALIZE)
def initialize(ls: LanguageServer, params: InitializeParams):
    """Initialize the language server."""
    if params.root_uri:
        ls.workspace_root = Path(params.root_uri.replace("file://", ""))
        logger.info(f"Workspace root: {ls.workspace_root}")

        # Try to load the DAZZLE project
        try:
            _load_project(ls)
        except Exception as e:
            logger.error(f"Failed to load project: {e}")


def _load_project(ls: LanguageServer):
    """Load DAZZLE project and build AppSpec."""
    if not ls.workspace_root:
        return

    manifest_path = ls.workspace_root / "dazzle.toml"
    if not manifest_path.exists():
        logger.warning(f"No dazzle.toml found in {ls.workspace_root}")
        return

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(ls.workspace_root, mf)
        modules = parse_modules(dsl_files)
        ls.appspec = build_appspec(modules, mf.project_root)
        logger.info(f"Loaded project with {len(ls.appspec.domain.entities)} entities")
    except Exception as e:
        logger.error(f"Error loading project: {e}")
        ls.appspec = None


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    """Handle document open."""
    logger.info(f"Opened: {params.text_document.uri}")


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: DidChangeTextDocumentParams):
    """Handle document change."""
    # Reload project on change
    try:
        _load_project(ls)
    except Exception as e:
        logger.error(f"Error reloading project: {e}")


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: DidSaveTextDocumentParams):
    """Handle document save."""
    logger.info(f"Saved: {params.text_document.uri}")
    # Reload project on save
    try:
        _load_project(ls)
    except Exception as e:
        logger.error(f"Error reloading project: {e}")


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: LanguageServer, params: DidCloseTextDocumentParams):
    """Handle document close."""
    logger.info(f"Closed: {params.text_document.uri}")


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    """Provide hover information."""
    if not ls.appspec:
        return None

    # Get the word at cursor position
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(document.source, params.position)

    if not word:
        return None

    # Look up entity
    for entity in ls.appspec.domain.entities:
        if entity.name == word:
            content = _format_entity_hover(entity)
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=content))

    # Look up surface
    for surface in ls.appspec.surfaces:
        if surface.name == word:
            content = _format_surface_hover(surface)
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=content))

    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: LanguageServer, params: DefinitionParams) -> Optional[Location]:
    """Provide go-to-definition."""
    if not ls.appspec or not ls.workspace_root:
        return None

    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(document.source, params.position)

    if not word:
        return None

    # Search for entity/surface definition in DSL files
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


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completion(ls: LanguageServer, params: CompletionParams) -> Optional[CompletionList]:
    """Provide completion suggestions."""
    if not ls.appspec:
        return None

    items: List[CompletionItem] = []

    # Add entity names
    for entity in ls.appspec.domain.entities:
        items.append(
            CompletionItem(
                label=entity.name,
                kind=CompletionItemKind.Class,
                detail="Entity",
                documentation=entity.title or entity.name,
            )
        )

    # Add surface names
    for surface in ls.appspec.surfaces:
        items.append(
            CompletionItem(
                label=surface.name,
                kind=CompletionItemKind.Interface,
                detail="Surface",
                documentation=surface.title or surface.name,
            )
        )

    # Add common field types
    field_types = ["uuid", "str", "int", "float", "bool", "date", "datetime", "time", "text", "json", "ref", "enum"]
    for ft in field_types:
        items.append(
            CompletionItem(
                label=ft,
                kind=CompletionItemKind.Keyword,
                detail="Field type",
            )
        )

    # Add common modifiers
    modifiers = ["required", "unique", "pk", "auto_add", "auto_update"]
    for mod in modifiers:
        items.append(
            CompletionItem(
                label=mod,
                kind=CompletionItemKind.Keyword,
                detail="Modifier",
            )
        )

    return CompletionList(is_incomplete=False, items=items)


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: LanguageServer, params: DocumentSymbolParams) -> List[DocumentSymbol]:
    """Provide document symbols for outline view."""
    if not ls.appspec:
        return []

    symbols: List[DocumentSymbol] = []

    # Add entities
    for entity in ls.appspec.domain.entities:
        # Create range (we don't have exact positions, so use dummy range)
        range_ = Range(start=Position(line=0, character=0), end=Position(line=0, character=0))

        entity_symbol = DocumentSymbol(
            name=entity.name,
            kind=SymbolKind.Class,
            range=range_,
            selection_range=range_,
            detail=entity.title or "",
        )

        # Add fields as children
        children = []
        for field in entity.fields:
            field_range = Range(start=Position(line=0, character=0), end=Position(line=0, character=0))
            field_symbol = DocumentSymbol(
                name=field.name,
                kind=SymbolKind.Field,
                range=field_range,
                selection_range=field_range,
                detail=str(field.type.kind.value),
            )
            children.append(field_symbol)

        entity_symbol.children = children
        symbols.append(entity_symbol)

    # Add surfaces
    for surface in ls.appspec.surfaces:
        range_ = Range(start=Position(line=0, character=0), end=Position(line=0, character=0))

        surface_symbol = DocumentSymbol(
            name=surface.name,
            kind=SymbolKind.Interface,
            range=range_,
            selection_range=range_,
            detail=surface.title or "",
        )
        symbols.append(surface_symbol)

    return symbols


# Helper functions


def _get_word_at_position(text: str, position: Position) -> Optional[str]:
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


def _get_grammar_tips(entity) -> list[str]:
    """Provide DAZZLE DSL grammar-specific tips and examples."""
    tips = []

    # Check what features are being used and suggest related ones
    has_enum = any(field.type.enum_values for field in entity.fields)
    has_ref = any(field.type.ref_entity for field in entity.fields)
    has_index = hasattr(entity, 'indexes') and entity.indexes

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
        tips.append("🔍 **Index syntax**: Add after fields: `index field_name` or `index field1,field2`")
        tips.append("   • Single field: `index email`")
        tips.append("   • Composite: `index created_by,status`")

    # Field type tips
    tips.append("📊 **Field types**: `str(max_len)`, `int`, `float(precision,scale)`, `uuid`, `datetime`, `date`, `time`, `bool`, `text`, `json`, `email`")

    # Modifier tips
    tips.append("🏷️ **Modifiers**: `required`, `unique`, `optional`, `pk`, `auto_add`, `auto_update`")
    tips.append("   • Example: `email: email unique required`")

    return tips


def _analyze_entity(entity) -> list[str]:
    """Analyze entity and provide recommendations."""
    recommendations = []

    # Check for missing timestamps
    has_created_at = any(f.name == 'created_at' for f in entity.fields)
    has_updated_at = any(f.name == 'updated_at' for f in entity.fields)

    if not has_created_at:
        recommendations.append("⏰ Consider adding `created_at: datetime auto_add` to track record creation")
    if not has_updated_at:
        recommendations.append("🔄 Consider adding `updated_at: datetime auto_update` to track modifications")

    # Check for foreign key indexes
    ref_fields_without_index = []
    indexed_fields = set()
    if hasattr(entity, 'indexes'):
        for idx in entity.indexes:
            if hasattr(idx, 'fields'):
                indexed_fields.update(idx.fields)

    for field in entity.fields:
        if field.type.ref_entity and field.name not in indexed_fields:
            ref_fields_without_index.append(field.name)

    if ref_fields_without_index:
        fields_str = ", ".join(f"`{f}`" for f in ref_fields_without_index[:3])
        recommendations.append(f"🔍 Consider adding indexes on foreign keys: {fields_str}")

    # Check for too many fields
    if len(entity.fields) > 15:
        recommendations.append(f"📊 Entity has {len(entity.fields)} fields - consider splitting into related entities")

    # Check for proper naming
    snake_case_issues = [f.name for f in entity.fields if '-' in f.name or ' ' in f.name]
    if snake_case_issues:
        recommendations.append("🔤 Use snake_case for field names (avoid hyphens and spaces)")

    # Check for unique constraints
    unique_fields = [f.name for f in entity.fields if f.is_unique and not f.is_primary_key]
    if not unique_fields and len(entity.fields) > 3:
        recommendations.append("⭐ Consider adding unique constraints on identifying fields (e.g., email, code)")

    # Check for soft delete pattern
    has_deleted_at = any(f.name in ('deleted_at', 'archived_at') for f in entity.fields)
    if not has_deleted_at and len(entity.fields) > 5:
        recommendations.append("🗑️ Consider soft delete pattern: add `deleted_at: datetime optional` for safer record archival")

    return recommendations


def _format_entity_hover(entity) -> str:
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
        if any('auto_add' in str(m) for m in field.modifiers):
            constraints.append("📅 Auto-add")
        if any('auto_update' in str(m) for m in field.modifiers):
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


def _get_surface_grammar_tips(surface) -> list[str]:
    """Provide DAZZLE DSL grammar tips for surfaces."""
    tips = []

    mode = surface.mode.value if hasattr(surface.mode, 'value') else str(surface.mode)

    # Basic surface syntax
    tips.append("📋 **Surface syntax**:")
    tips.append("```")
    tips.append("surface my_surface \"Title\":")
    tips.append("  uses entity MyEntity")
    tips.append("  mode: list")
    tips.append("```")

    # Section syntax
    tips.append("")
    tips.append("📦 **Section syntax**:")
    tips.append("```")
    tips.append("section main \"Main Fields\":")
    tips.append("  field name \"Name\"")
    tips.append("  field status \"Status\"")
    tips.append("```")

    # Action syntax based on mode
    tips.append("")
    tips.append("⚡ **Action syntax**:")
    if mode == "list":
        tips.append("```")
        tips.append("action create \"New\":")
        tips.append("  on click -> surface my_create")
        tips.append("")
        tips.append("action view \"View\":")
        tips.append("  on click -> surface my_detail")
        tips.append("```")
    elif mode == "view":
        tips.append("```")
        tips.append("action edit \"Edit\":")
        tips.append("  on click -> surface my_edit")
        tips.append("")
        tips.append("action delete \"Delete\":")
        tips.append("  on submit -> experience my_flow step confirm")
        tips.append("```")
    else:
        tips.append("```")
        tips.append("action submit \"Save\":")
        tips.append("  on submit -> experience my_flow step success")
        tips.append("```")

    # Experience reference
    tips.append("")
    tips.append("🎬 **Experience reference**: Actions can navigate to experiences:")
    tips.append("   • `on click -> experience flow_name step step_name`")
    tips.append("   • `on submit -> experience flow_name step next_step`")

    return tips


def _analyze_surface(surface) -> list[str]:
    """Analyze surface and provide recommendations."""
    recommendations = []

    mode = surface.mode.value if hasattr(surface.mode, 'value') else str(surface.mode)

    # Check for missing sections
    num_sections = len(surface.sections) if hasattr(surface, 'sections') and surface.sections else 0

    if num_sections == 0:
        recommendations.append("📋 Add sections to organize fields and improve UX")

    # List surface specific advice
    if mode == "list":
        # Check if key identifying fields are present
        if hasattr(surface, 'sections') and surface.sections:
            all_fields = []
            for section in surface.sections:
                if hasattr(section, 'fields'):
                    all_fields.extend([f.name for f in section.fields if hasattr(f, 'name')])

            if 'id' not in all_fields and len(all_fields) > 0:
                recommendations.append("🔍 Include an ID or identifier field in list view for better navigation")

        recommendations.append("🔎 Consider adding filters section for user-friendly data exploration")
        recommendations.append("📊 Add pagination for better performance with large datasets")

    # Create/Edit surface advice
    elif mode in ("create", "edit"):
        if num_sections < 2 and hasattr(surface, 'sections'):
            # Count total fields
            total_fields = sum(len(s.fields) if hasattr(s, 'fields') else 0
                             for s in surface.sections)
            if total_fields > 5:
                recommendations.append("📦 Group related fields into multiple sections for better form organization")

        recommendations.append("✅ Add validation rules to ensure data quality")
        recommendations.append("💾 Include clear submit/cancel actions")

    # View surface advice
    elif mode == "view":
        has_actions = hasattr(surface, 'actions') and surface.actions and len(surface.actions) > 0

        if not has_actions:
            recommendations.append("⚡ Add actions (edit, delete, etc.) to enable user interactions")

        recommendations.append("🔗 Consider adding related record sections (e.g., comments, history)")

    # Check for missing entity reference
    if not surface.entity_ref:
        recommendations.append("⚠️ Surface should reference an entity with `uses entity EntityName`")

    # Check for actions
    has_actions = hasattr(surface, 'actions') and surface.actions and len(surface.actions) > 0
    if not has_actions and mode != "view":
        recommendations.append("🎬 Add actions to define user interactions (buttons, forms, navigation)")

    return recommendations


def _format_surface_hover(surface) -> str:
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
        "delete": "🗑️ Confirmation for deleting records"
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
    if hasattr(surface, 'sections') and surface.sections:
        lines.append("## Sections")
        lines.append("")
        for section in surface.sections[:5]:  # Show first 5 sections
            section_name = section.name if hasattr(section, 'name') else 'unnamed'
            section_title = section.title if hasattr(section, 'title') else section_name
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


def _find_definition_in_file(file_path: Path, word: str) -> Optional[Location]:
    """Find definition of word in a DSL file."""
    try:
        content = file_path.read_text()
        lines = content.split("\n")

        for line_no, line in enumerate(lines):
            # Look for entity/surface definition
            if f"entity {word} " in line or f"surface {word} " in line:
                uri = file_path.as_uri()
                range_ = Range(
                    start=Position(line=line_no, character=0),
                    end=Position(line=line_no, character=len(line)),
                )
                return Location(uri=uri, range=range_)
    except Exception as e:
        logger.error(f"Error searching file {file_path}: {e}")

    return None


def start_server():
    """Start the DAZZLE LSP server."""
    logger.info("Starting DAZZLE Language Server...")
    server.start_io()


if __name__ == "__main__":
    start_server()
