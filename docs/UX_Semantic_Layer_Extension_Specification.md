# DAZZLE UX Semantic Layer Extension Specification

**Version**: 0.2.0-alpha  
**Target Implementation**: Claude Code (Opus 4.5)  
**Created**: 2025-11-25  
**Status**: DRAFT FOR IMPLEMENTATION

---

## Executive Summary

This specification defines extensions to the DAZZLE DSL v0.1 to capture **User Experience (UX) semantics** without prescribing visual implementation. The extension introduces three core concepts:

1. **Information Needs** - Why surfaces exist and what questions they answer
2. **Attention Signals** - Data conditions requiring user awareness or action  
3. **Persona Variants** - Context-specific surface adaptations

Additionally, a new **workspace** construct enables composition of related information needs without resorting to implementation-specific "dashboard" patterns.

**Design Philosophy**: Express *what matters to users* and *why*, not *how to display it*. Stack generators interpret semantic intent into appropriate platform idioms.

---

## Context: What Already Exists

### DAZZLE v0.1 Current State

DAZZLE is a domain-specific language for generating full-stack applications from high-level specifications. The current implementation includes:

**Core Constructs:**
- `entity` - Domain models with typed fields
- `surface` - User-facing screens (list/view/create/edit modes)
- `experience` - Multi-step workflows
- `service` - External API configurations
- `foreign_model` - External data shapes
- `integration` - Service interaction logic

**Key Files:**
- `src/dazzle/core/ir.py` - Internal Representation (Pydantic models)
- `src/dazzle/core/dsl_parser.py` - DSL parser
- `src/dazzle/core/dsl_grammar.py` - Lark grammar
- `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` - EBNF reference grammar
- `docs/DAZZLE_DSL_REFERENCE_0_1.md` - Language documentation

**Stacks (Code Generators):**
- `src/dazzle/stacks/django_micro_modular/` - Django web apps
- `src/dazzle/stacks/django_api/` - Django REST Framework
- `src/dazzle/stacks/express_micro/` - Express.js
- `src/dazzle/stacks/openapi/` - OpenAPI specs

**Current Surface Example:**
```dsl
surface tree_list "All Trees":
  uses entity Tree
  mode: list

  section main "Trees":
    field species "Species"
    field condition_status "Condition"
    field steward "Steward"
```

**What's Missing:**
- No way to express *why* this surface exists (purpose)
- No way to indicate *priority* of data (attention signals)
- No way to adapt for *different user roles* (persona variants)
- No composition mechanism beyond single surfaces (workspaces)

---

## Requirements

### R1: UX Block Extension (Surface Enhancement)

**Requirement**: Extend existing `surface` declarations with optional `ux:` block.

**Constraints:**
- MUST be backward compatible (existing surfaces remain valid)
- MUST parse without errors when `ux:` block is absent
- MUST integrate with existing IR validation

**Grammar Addition:**
```ebnf
surface_decl ::= "surface" SURFACE_NAME STRING? ":" NEWLINE
                 INDENT
                   uses_entity_line
                   mode_line
                   section_decl+
                   action_decl*
                   ux_block?              (* NEW: optional UX block *)
                 DEDENT ;

ux_block ::= "ux" ":" NEWLINE
             INDENT
               ux_directive+
             DEDENT ;
```

### R2: Purpose Declaration

**Requirement**: Capture semantic intent of surface in single line.

**Syntax:**
```dsl
ux:
  purpose: "Monitor tree health and coordinate stewardship"
```

**Validation:**
- MUST be a non-empty string
- SHOULD be present (warning if absent)
- Used for: documentation, code comments, help text generation

### R3: Information Needs (Display Controls)

**Requirement**: Express what fields to show, how to sort/filter/search.

**Syntax:**
```dsl
ux:
  show: species, condition_status, steward
  sort: condition_status desc, last_inspection_date asc
  filter: condition_status, steward
  search: species, street_address
  empty: "No trees registered yet."
```

**Grammar:**
```ebnf
ux_directive ::= purpose_line
              | show_line
              | sort_line
              | filter_line
              | search_line
              | empty_line
              | attention_block
              | persona_block ;

purpose_line ::= "purpose" ":" STRING NEWLINE ;
show_line    ::= "show" ":" field_list NEWLINE ;
sort_line    ::= "sort" ":" sort_expr ("," sort_expr)* NEWLINE ;
filter_line  ::= "filter" ":" field_list NEWLINE ;
search_line  ::= "search" ":" field_list NEWLINE ;
empty_line   ::= "empty" ":" STRING NEWLINE ;

field_list   ::= FIELD_NAME ("," FIELD_NAME)* ;
sort_expr    ::= FIELD_NAME ("asc" | "desc")? ;
```

**Validation:**
- All field names MUST exist in referenced entity
- Sort expressions MUST reference valid fields
- Filter/search fields SHOULD be indexed (warning if not)

**Code Generation Mapping:**

| Directive | Django | React | Notes |
|-----------|--------|-------|-------|
| `show:` | Queryset `.values()` | Display columns | Override section fields if present |
| `sort:` | Queryset `.order_by()` | Default sort state | User can override |
| `filter:` | django-filter config | Filter dropdowns | Per-field filtering |
| `search:` | SearchVector | Search input | Full-text when possible |
| `empty:` | Template conditional | Empty state component | User-friendly message |

### R4: Attention Signals

**Requirement**: Define data-driven priority indicators without prescribing visual style.

**Syntax:**
```dsl
ux:
  attention critical:
    when: condition_status in [SevereStress, Dead]
    message: "Urgent attention required"
    action: task_create
    
  attention warning:
    when: days_since(last_inspection_date) > 30
    message: "Overdue for inspection"
    action: observation_create
```

**Grammar:**
```ebnf
attention_block ::= "attention" signal_level ":" NEWLINE
                    INDENT
                      "when" ":" condition_expr NEWLINE
                      "message" ":" STRING NEWLINE
                      ("action" ":" surface_ref NEWLINE)?
                    DEDENT ;

signal_level ::= "critical" | "warning" | "notice" | "info" ;

condition_expr ::= field_comparison
                | field_comparison ("and" | "or") condition_expr
                | "(" condition_expr ")" ;

field_comparison ::= FIELD_NAME operator value
                  | function_call operator value ;

operator ::= "=" | "!=" | ">" | "<" | ">=" | "<=" 
          | "in" | "not in" | "is" | "is not" ;

function_call ::= FUNCTION_NAME "(" FIELD_NAME ")" ;
```

**Supported Functions (Phase 1):**
- `days_since(datetime_field)` → integer
- `count(related_field)` → integer  
- `sum(numeric_field)` → number
- `avg(numeric_field)` → number

**Validation:**
- Signal level MUST be one of: `critical`, `warning`, `notice`, `info`
- Condition expression MUST reference valid fields
- Condition expression MUST be type-compatible (no `int > string`)
- Action MUST reference valid surface if present
- Warn if conditions overlap (e.g., two `critical` signals can both fire)

**Code Generation Mapping:**

| Signal Level | Django | React | Semantic Meaning |
|--------------|--------|-------|------------------|
| `critical` | `danger` class | Red badge/border | Requires immediate action |
| `warning` | `warning` class | Amber badge/border | Needs attention soon |
| `notice` | `info` class | Blue badge/border | Worth noting |
| `info` | `secondary` class | Grey badge/border | Informational only |

**Implementation Notes:**
- Conditions evaluated per-row in list views
- Conditions evaluated once in detail views
- Multiple signals can apply to same row (stack order: critical → warning → notice → info)
- If action specified, generate inline button/link

### R5: Persona Variants

**Requirement**: Define role-specific adaptations to surfaces.

**Syntax:**
```dsl
ux:
  for volunteer:
    scope: steward = current_user
    purpose: "Monitor your adopted trees"
    show: species, condition_status, last_inspection_date
    action_primary: observation_create
    
  for coordinator:
    scope: all
    purpose: "Oversee all trees in network"
    show_aggregate: critical_count, warning_count
    action_primary: task_create
    
  for public:
    scope: all
    hide: steward
    read_only: true
```

**Grammar:**
```ebnf
persona_block ::= "for" persona_name ":" NEWLINE
                  INDENT
                    persona_directive+
                  DEDENT ;

persona_name ::= IDENTIFIER ;

persona_directive ::= "scope" ":" filter_expr NEWLINE
                   | "purpose" ":" STRING NEWLINE
                   | "show" ":" field_list NEWLINE
                   | "hide" ":" field_list NEWLINE
                   | "show_aggregate" ":" aggregate_list NEWLINE
                   | "action_primary" ":" surface_ref NEWLINE
                   | "read_only" ":" bool NEWLINE ;

filter_expr ::= field_comparison
             | field_comparison ("and" | "or") filter_expr
             | "all" ;

aggregate_list ::= aggregate_name ("," aggregate_name)* ;
aggregate_name ::= IDENTIFIER ;
```

**Validation:**
- Persona name MUST be valid identifier
- Scope filter MUST reference valid fields
- Show/hide fields MUST exist in entity
- Action_primary MUST reference valid surface
- Aggregates reference attention signal counts (e.g., `critical_count`)
- Warn if `show:` and `hide:` conflict

**Special Scopes:**
- `scope: all` - No filtering (see everything)
- `scope: owned_by = current_user` - Filter to user's records
- `scope: team = current_user.team` - Filter to user's team
- Current user accessed via `current_user` pseudo-variable

**Code Generation Mapping:**

| Directive | Django | React | Notes |
|-----------|--------|-------|-------|
| `scope:` | Queryset filter | Data filtering | Applied before rendering |
| `purpose:` | Template comment | Component docstring | Documentation |
| `show:` | Template conditional | Conditional render | Override base fields |
| `hide:` | Template conditional | Conditional render | Remove base fields |
| `show_aggregate:` | Template variable | Aggregate component | Show counts/sums |
| `action_primary:` | Primary button | Primary action button | Most prominent action |
| `read_only:` | Disable forms | Disable inputs | No mutations allowed |

**Implementation Strategy:**
- Personas resolved at runtime based on user context
- Multiple personas can match (use first match)
- Base surface used if no persona matches
- Persona detection via Django user attributes or React context

### R6: Workspace Construct

**Requirement**: New top-level construct for composing related information needs.

**Syntax:**
```dsl
workspace volunteer_hub "My Trees":
  purpose: "Daily tree stewardship dashboard"
  
  priority_trees:
    source: Tree
    filter: steward = current_user
    sort: attention desc
    limit: 10
    action: observation_create
    empty: "No trees assigned yet."
  
  recent_observations:
    source: Observation
    filter: observer = current_user
    sort: submitted_at desc
    limit: 5
    display: timeline
  
  network_health:
    aggregate:
      total_trees: count(Tree)
      healthy_pct: round(count(Tree where condition_status = Healthy) * 100 / count(Tree))
```

**Grammar:**
```ebnf
workspace_decl ::= "workspace" WORKSPACE_NAME STRING? ":" NEWLINE
                   INDENT
                     purpose_line?
                     workspace_region+
                     ux_block?
                   DEDENT ;

workspace_region ::= region_name ":" NEWLINE
                     INDENT
                       region_directive+
                     DEDENT ;

region_name ::= IDENTIFIER ;

region_directive ::= "source" ":" (ENTITY_NAME | SURFACE_NAME) NEWLINE
                  | "filter" ":" filter_expr NEWLINE
                  | "sort" ":" sort_expr NEWLINE
                  | "limit" ":" NUMBER NEWLINE
                  | "display" ":" display_mode NEWLINE
                  | "action" ":" surface_ref NEWLINE
                  | "empty" ":" STRING NEWLINE
                  | "aggregate" ":" aggregate_block ;

display_mode ::= "list" | "grid" | "timeline" | "map" ;

aggregate_block ::= NEWLINE INDENT metric_line+ DEDENT ;

metric_line ::= metric_name ":" aggregate_expr NEWLINE ;

aggregate_expr ::= function_call
                | arithmetic_expr ;

arithmetic_expr ::= aggregate_expr ("+" | "-" | "*" | "/") aggregate_expr
                 | NUMBER ;
```

**Validation:**
- Workspace name MUST be unique within app
- Region names MUST be unique within workspace
- Source MUST reference valid entity or surface
- Filter expressions MUST reference valid fields
- Aggregate expressions MUST be type-compatible
- Action MUST reference valid surface

**Aggregate Functions:**
- `count(Entity)` - Count all records
- `count(Entity where condition)` - Conditional count
- `sum(Entity.field)` - Sum numeric field
- `avg(Entity.field)` - Average numeric field
- `min(Entity.field)` - Minimum value
- `max(Entity.field)` - Maximum value
- `round(expr)` - Round to integer
- `round(expr, N)` - Round to N decimals

**Display Modes:**
- `list` - Traditional table/list (default)
- `grid` - Card grid layout
- `timeline` - Chronological timeline
- `map` - Geographic visualization (requires lat/lng fields)

**Code Generation:**
- Django: Custom view with multiple querysets
- React: Dashboard component with multiple sections
- Each region becomes a section/panel
- Aggregates compute on queryset

---

## IR Extensions (Pydantic Models)

### File: `src/dazzle/core/ir.py`

Add the following classes after existing IR definitions:

```python
# UX Semantic Layer Types

class UXPurpose(BaseModel):
    """Semantic purpose of a surface or workspace."""
    text: str = Field(min_length=1, max_length=500)
    
    class Config:
        frozen = True


class AttentionSignal(BaseModel):
    """Data-driven attention signal for prioritization."""
    level: Literal["critical", "warning", "notice", "info"]
    condition: str  # Condition expression (to be validated separately)
    message: str = Field(min_length=1, max_length=200)
    action: Optional[str] = None  # Surface reference
    
    class Config:
        frozen = True
    
    @property
    def css_class(self) -> str:
        """Map signal level to CSS class name."""
        return {
            "critical": "danger",
            "warning": "warning", 
            "notice": "info",
            "info": "secondary"
        }[self.level]


class PersonaVariant(BaseModel):
    """Role-specific surface adaptation."""
    persona: str = Field(min_length=1)
    scope: Optional[str] = None  # Filter expression or "all"
    purpose: Optional[str] = None
    show: List[str] = Field(default_factory=list)
    hide: List[str] = Field(default_factory=list)
    show_aggregate: List[str] = Field(default_factory=list)
    action_primary: Optional[str] = None  # Surface reference
    read_only: bool = False
    
    class Config:
        frozen = True
    
    def applies_to_user(self, user_context: Dict[str, Any]) -> bool:
        """Check if persona applies to given user context."""
        # Implementation will check user_context["role"] or similar
        return user_context.get("persona") == self.persona


class UXSpec(BaseModel):
    """Complete UX specification for a surface."""
    purpose: Optional[UXPurpose] = None
    show: List[str] = Field(default_factory=list)
    sort: List[str] = Field(default_factory=list)  # e.g., ["field asc", "other desc"]
    filter: List[str] = Field(default_factory=list)
    search: List[str] = Field(default_factory=list)
    empty_message: Optional[str] = None
    attention_signals: List[AttentionSignal] = Field(default_factory=list)
    persona_variants: List[PersonaVariant] = Field(default_factory=list)
    
    class Config:
        frozen = True
    
    def get_persona_variant(self, user_context: Dict[str, Any]) -> Optional[PersonaVariant]:
        """Get applicable persona variant for user context."""
        for variant in self.persona_variants:
            if variant.applies_to_user(user_context):
                return variant
        return None
    
    @property
    def has_attention_signals(self) -> bool:
        return len(self.attention_signals) > 0


class WorkspaceRegion(BaseModel):
    """Named region within a workspace."""
    name: str
    source: str  # Entity or surface name
    filter: Optional[str] = None  # Filter expression
    sort: Optional[str] = None
    limit: Optional[int] = Field(None, ge=1, le=1000)
    display: Optional[Literal["list", "grid", "timeline", "map"]] = None
    action: Optional[str] = None  # Surface reference
    empty_message: Optional[str] = None
    aggregates: Dict[str, str] = Field(default_factory=dict)  # metric_name: expr
    
    class Config:
        frozen = True


class WorkspaceSpec(BaseModel):
    """Composition of related information needs."""
    name: str
    title: Optional[str] = None
    purpose: Optional[str] = None
    regions: List[WorkspaceRegion] = Field(default_factory=list)
    ux: Optional[UXSpec] = None  # Workspace-level UX (e.g., responsive)
    
    class Config:
        frozen = True
    
    def get_region(self, name: str) -> Optional[WorkspaceRegion]:
        """Get region by name."""
        for region in self.regions:
            if region.name == name:
                return region
        return None
```

### Extend Existing IR Types

**Modify `SurfaceSpec` in `src/dazzle/core/ir.py`:**

```python
class SurfaceSpec(BaseModel):
    name: str
    title: Optional[str] = None
    entity_ref: Optional[str] = None
    mode: SurfaceMode
    sections: List[SurfaceSection] = Field(default_factory=list)
    actions: List[SurfaceAction] = Field(default_factory=list)
    ux: Optional[UXSpec] = None  # NEW: UX semantic layer

    class Config:
        frozen = True

    # ... existing methods ...
```

**Modify `AppSpec` in `src/dazzle/core/ir.py`:**

```python
class AppSpec(BaseModel):
    name: str
    title: Optional[str] = None
    version: str = "0.1.0"
    domain: DomainSpec = Field(default_factory=DomainSpec)
    surfaces: List[SurfaceSpec] = Field(default_factory=list)
    workspaces: List[WorkspaceSpec] = Field(default_factory=list)  # NEW
    experiences: List[ExperienceSpec] = Field(default_factory=list)
    services: List[ServiceSpec] = Field(default_factory=list)
    foreign_models: List[ForeignModelSpec] = Field(default_factory=list)
    integrations: List[IntegrationSpec] = Field(default_factory=list)

    class Config:
        frozen = True

    # Add new helper methods
    def get_workspace(self, name: str) -> Optional[WorkspaceSpec]:
        """Get workspace by name."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None
```

---

## Grammar Updates

### File: `src/dazzle/core/dsl_grammar.py`

Add to the Lark grammar definition:

```python
# Add after existing surface_decl rule
surface_decl: "surface" identifier string? ":" NEWLINE
              INDENT
                uses_entity_line
                mode_line
                section_decl+
                action_decl*
                ux_block?              # NEW: optional UX block
              DEDENT

# NEW: UX block rules
ux_block: "ux" ":" NEWLINE
          INDENT
            ux_directive+
          DEDENT

ux_directive: purpose_line
            | show_line
            | sort_line
            | filter_line
            | search_line
            | empty_line
            | attention_block
            | persona_block

purpose_line: "purpose" ":" string NEWLINE
show_line: "show" ":" field_list NEWLINE
sort_line: "sort" ":" sort_expr ("," sort_expr)* NEWLINE
filter_line: "filter" ":" field_list NEWLINE
search_line: "search" ":" field_list NEWLINE
empty_line: "empty" ":" string NEWLINE

field_list: identifier ("," identifier)*
sort_expr: identifier ("asc" | "desc")?

# Attention signals
attention_block: "attention" signal_level ":" NEWLINE
                 INDENT
                   "when" ":" condition_expr NEWLINE
                   "message" ":" string NEWLINE
                   ("action" ":" identifier NEWLINE)?
                 DEDENT

signal_level: "critical" | "warning" | "notice" | "info"

condition_expr: comparison
              | comparison ("and" | "or") condition_expr
              | "(" condition_expr ")"

comparison: identifier operator value
          | function_call operator value

operator: "=" | "!=" | ">" | "<" | ">=" | "<="
        | "in" | "not in" | "is" | "is not"

function_call: identifier "(" identifier ")"

value: string | number | identifier | value_list

value_list: "[" value ("," value)* "]"

# Persona variants
persona_block: "for" identifier ":" NEWLINE
               INDENT
                 persona_directive+
               DEDENT

persona_directive: "scope" ":" scope_expr NEWLINE
                 | "purpose" ":" string NEWLINE
                 | "show" ":" field_list NEWLINE
                 | "hide" ":" field_list NEWLINE
                 | "show_aggregate" ":" identifier ("," identifier)* NEWLINE
                 | "action_primary" ":" identifier NEWLINE
                 | "read_only" ":" BOOLEAN NEWLINE

scope_expr: "all"
          | comparison
          | comparison ("and" | "or") scope_expr

# Workspace construct
workspace_decl: "workspace" identifier string? ":" NEWLINE
                INDENT
                  purpose_line?
                  workspace_region+
                  ux_block?
                DEDENT

workspace_region: identifier ":" NEWLINE
                  INDENT
                    region_directive+
                  DEDENT

region_directive: "source" ":" identifier NEWLINE
                | "filter" ":" filter_expr NEWLINE
                | "sort" ":" sort_expr NEWLINE
                | "limit" ":" number NEWLINE
                | "display" ":" display_mode NEWLINE
                | "action" ":" identifier NEWLINE
                | "empty" ":" string NEWLINE
                | "aggregate" ":" aggregate_block

display_mode: "list" | "grid" | "timeline" | "map"

aggregate_block: NEWLINE INDENT metric_line+ DEDENT

metric_line: identifier ":" aggregate_expr NEWLINE

aggregate_expr: function_call
              | arithmetic_expr
              | number

arithmetic_expr: aggregate_expr ("+" | "-" | "*" | "/") aggregate_expr
               | "(" aggregate_expr ")"

filter_expr: "all"
           | comparison
           | comparison ("and" | "or") filter_expr

# Terminals
BOOLEAN: "true" | "false"
```

### File: `docs/DAZZLE_DSL_GRAMMAR_0_2.ebnf`

Create new version of EBNF grammar incorporating all changes above. Copy from `DAZZLE_DSL_GRAMMAR_0_1.ebnf` and add the new rules.

---

## Parser Updates

### File: `src/dazzle/core/dsl_parser.py`

Add transformer methods for new grammar rules:

```python
class DazzleTransformer(Transformer):
    # ... existing methods ...
    
    # UX Block Transformers
    def ux_block(self, items):
        """Transform ux block into UXSpec."""
        purpose = None
        show = []
        sort = []
        filter_fields = []
        search = []
        empty_message = None
        attention_signals = []
        persona_variants = []
        
        for item in items:
            if isinstance(item, UXPurpose):
                purpose = item
            elif isinstance(item, dict):
                if "show" in item:
                    show = item["show"]
                elif "sort" in item:
                    sort = item["sort"]
                elif "filter" in item:
                    filter_fields = item["filter"]
                elif "search" in item:
                    search = item["search"]
                elif "empty" in item:
                    empty_message = item["empty"]
            elif isinstance(item, AttentionSignal):
                attention_signals.append(item)
            elif isinstance(item, PersonaVariant):
                persona_variants.append(item)
        
        return UXSpec(
            purpose=purpose,
            show=show,
            sort=sort,
            filter=filter_fields,
            search=search,
            empty_message=empty_message,
            attention_signals=attention_signals,
            persona_variants=persona_variants
        )
    
    def purpose_line(self, items):
        """Transform purpose line."""
        text = str(items[0]).strip('"')
        return UXPurpose(text=text)
    
    def show_line(self, items):
        """Transform show line."""
        fields = [str(f) for f in items[0]]
        return {"show": fields}
    
    def sort_line(self, items):
        """Transform sort line."""
        sort_exprs = [self._format_sort_expr(expr) for expr in items]
        return {"sort": sort_exprs}
    
    def _format_sort_expr(self, expr):
        """Format sort expression as 'field asc/desc'."""
        if isinstance(expr, tuple):
            field, direction = expr
            return f"{field} {direction}"
        return f"{expr} asc"
    
    def filter_line(self, items):
        """Transform filter line."""
        fields = [str(f) for f in items[0]]
        return {"filter": fields}
    
    def search_line(self, items):
        """Transform search line."""
        fields = [str(f) for f in items[0]]
        return {"search": fields}
    
    def empty_line(self, items):
        """Transform empty message line."""
        message = str(items[0]).strip('"')
        return {"empty": message}
    
    def attention_block(self, items):
        """Transform attention block."""
        level = str(items[0])
        condition = None
        message = None
        action = None
        
        for item in items[1:]:
            if isinstance(item, dict):
                if "when" in item:
                    condition = item["when"]
                elif "message" in item:
                    message = item["message"]
                elif "action" in item:
                    action = item["action"]
        
        return AttentionSignal(
            level=level,
            condition=condition,
            message=message,
            action=action
        )
    
    def condition_expr(self, items):
        """Transform condition expression to string."""
        # For Phase 1, store as string for later evaluation
        # Future: parse into AST for validation
        return {"when": " ".join(str(i) for i in items)}
    
    def persona_block(self, items):
        """Transform persona block."""
        persona_name = str(items[0])
        scope = None
        purpose = None
        show = []
        hide = []
        show_aggregate = []
        action_primary = None
        read_only = False
        
        for item in items[1:]:
            if isinstance(item, dict):
                if "scope" in item:
                    scope = item["scope"]
                elif "purpose" in item:
                    purpose = item["purpose"]
                elif "show" in item:
                    show = item["show"]
                elif "hide" in item:
                    hide = item["hide"]
                elif "show_aggregate" in item:
                    show_aggregate = item["show_aggregate"]
                elif "action_primary" in item:
                    action_primary = item["action_primary"]
                elif "read_only" in item:
                    read_only = item["read_only"]
        
        return PersonaVariant(
            persona=persona_name,
            scope=scope,
            purpose=purpose,
            show=show,
            hide=hide,
            show_aggregate=show_aggregate,
            action_primary=action_primary,
            read_only=read_only
        )
    
    def workspace_decl(self, items):
        """Transform workspace declaration."""
        name = str(items[0])
        title = str(items[1]).strip('"') if len(items) > 1 and isinstance(items[1], str) else None
        
        purpose = None
        regions = []
        ux = None
        
        for item in items[2:]:
            if isinstance(item, UXPurpose):
                purpose = item.text
            elif isinstance(item, WorkspaceRegion):
                regions.append(item)
            elif isinstance(item, UXSpec):
                ux = item
        
        return WorkspaceSpec(
            name=name,
            title=title,
            purpose=purpose,
            regions=regions,
            ux=ux
        )
    
    def workspace_region(self, items):
        """Transform workspace region."""
        name = str(items[0])
        
        source = None
        filter_expr = None
        sort = None
        limit = None
        display = None
        action = None
        empty_message = None
        aggregates = {}
        
        for item in items[1:]:
            if isinstance(item, dict):
                if "source" in item:
                    source = item["source"]
                elif "filter" in item:
                    filter_expr = item["filter"]
                elif "sort" in item:
                    sort = item["sort"]
                elif "limit" in item:
                    limit = item["limit"]
                elif "display" in item:
                    display = item["display"]
                elif "action" in item:
                    action = item["action"]
                elif "empty" in item:
                    empty_message = item["empty"]
                elif "aggregates" in item:
                    aggregates = item["aggregates"]
        
        return WorkspaceRegion(
            name=name,
            source=source,
            filter=filter_expr,
            sort=sort,
            limit=limit,
            display=display,
            action=action,
            empty_message=empty_message,
            aggregates=aggregates
        )
    
    def aggregate_block(self, items):
        """Transform aggregate block."""
        aggregates = {}
        for item in items:
            if isinstance(item, tuple):
                metric_name, expr = item
                aggregates[metric_name] = expr
        return {"aggregates": aggregates}
    
    def metric_line(self, items):
        """Transform metric line."""
        name = str(items[0])
        expr = str(items[1])
        return (name, expr)
```

---

## Validation Rules

### File: `src/dazzle/core/lint.py`

Add validation for UX extensions:

```python
def validate_ux_spec(surface: SurfaceSpec, appspec: AppSpec) -> List[LintMessage]:
    """Validate UX specification on surface."""
    messages = []
    
    if not surface.ux:
        return messages
    
    ux = surface.ux
    entity = appspec.get_entity(surface.entity_ref) if surface.entity_ref else None
    
    # Validate purpose
    if not ux.purpose:
        messages.append(LintMessage(
            level="warning",
            message=f"Surface '{surface.name}' has UX block but no purpose",
            suggestion="Add purpose: line to explain why this surface exists"
        ))
    
    # Validate field references
    if entity:
        all_fields = {f.name for f in entity.fields}
        
        for field in ux.show:
            if field not in all_fields:
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown field '{field}' in show: directive",
                    suggestion=f"Valid fields: {', '.join(all_fields)}"
                ))
        
        for field in ux.filter:
            if field not in all_fields:
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown field '{field}' in filter: directive",
                    suggestion=f"Valid fields: {', '.join(all_fields)}"
                ))
        
        for field in ux.search:
            if field not in all_fields:
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown field '{field}' in search: directive",
                    suggestion=f"Valid fields: {', '.join(all_fields)}"
                ))
    
    # Validate attention signals
    for signal in ux.attention_signals:
        # Validate action reference
        if signal.action:
            if not appspec.get_surface(signal.action):
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown surface '{signal.action}' in attention action",
                    suggestion="Check surface name spelling"
                ))
        
        # TODO: Validate condition expression syntax
        # For Phase 1: store as string, validate in Phase 2
    
    # Validate persona variants
    for variant in ux.persona_variants:
        # Validate field references
        if entity:
            for field in variant.show:
                if field not in all_fields:
                    messages.append(LintMessage(
                        level="error",
                        message=f"Unknown field '{field}' in persona show",
                        suggestion=f"Valid fields: {', '.join(all_fields)}"
                    ))
            
            for field in variant.hide:
                if field not in all_fields:
                    messages.append(LintMessage(
                        level="error",
                        message=f"Unknown field '{field}' in persona hide",
                        suggestion=f"Valid fields: {', '.join(all_fields)}"
                    ))
        
        # Validate action reference
        if variant.action_primary:
            if not appspec.get_surface(variant.action_primary):
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown surface '{variant.action_primary}' in persona action_primary",
                    suggestion="Check surface name spelling"
                ))
        
        # Check for show/hide conflicts
        conflicts = set(variant.show) & set(variant.hide)
        if conflicts:
            messages.append(LintMessage(
                level="warning",
                message=f"Fields in both show and hide: {', '.join(conflicts)}",
                suggestion="Remove from one list or the other"
            ))
    
    return messages


def validate_workspace(workspace: WorkspaceSpec, appspec: AppSpec) -> List[LintMessage]:
    """Validate workspace specification."""
    messages = []
    
    # Check for duplicate region names
    region_names = [r.name for r in workspace.regions]
    duplicates = [name for name in region_names if region_names.count(name) > 1]
    if duplicates:
        messages.append(LintMessage(
            level="error",
            message=f"Duplicate region names in workspace '{workspace.name}': {', '.join(set(duplicates))}",
            suggestion="Use unique names for each region"
        ))
    
    # Validate each region
    for region in workspace.regions:
        # Validate source reference
        source_entity = appspec.get_entity(region.source)
        source_surface = appspec.get_surface(region.source)
        
        if not source_entity and not source_surface:
            messages.append(LintMessage(
                level="error",
                message=f"Unknown source '{region.source}' in region '{region.name}'",
                suggestion="Check entity or surface name spelling"
            ))
        
        # Validate action reference
        if region.action:
            if not appspec.get_surface(region.action):
                messages.append(LintMessage(
                    level="error",
                    message=f"Unknown surface '{region.action}' in region action",
                    suggestion="Check surface name spelling"
                ))
        
        # Validate display mode
        if region.display == "map":
            if source_entity:
                has_lat = any(f.name in ["latitude", "location_lat", "lat"] for f in source_entity.fields)
                has_lng = any(f.name in ["longitude", "location_lng", "lng", "lon"] for f in source_entity.fields)
                
                if not (has_lat and has_lng):
                    messages.append(LintMessage(
                        level="warning",
                        message=f"Region '{region.name}' uses map display but entity lacks lat/lng fields",
                        suggestion="Add latitude and longitude fields to entity"
                    ))
        
        # Validate limit range
        if region.limit and region.limit > 1000:
            messages.append(LintMessage(
                level="warning",
                message=f"Region '{region.name}' limit is very high ({region.limit})",
                suggestion="Consider pagination for large datasets"
            ))
    
    return messages
```

---

## Stack Implementation Guide

### Django Micro Modular Stack

**File: `src/dazzle/stacks/django_micro_modular/templates_ext.py`**

Create new file for UX-aware template generation:

```python
"""Extended template generation with UX support."""

from dazzle.core.ir import SurfaceSpec, AttentionSignal, PersonaVariant
from typing import Dict, Any


def generate_list_view_ux(surface: SurfaceSpec, entity_name: str) -> str:
    """Generate ListView with UX enhancements."""
    
    if not surface.ux:
        # Fall back to basic template
        return generate_basic_list_view(surface, entity_name)
    
    ux = surface.ux
    
    template = f"""
{{% extends "base.html" %}}
{{% load static %}}

{{% block title %}}{surface.title or surface.name}{{% endblock %}}

{{% block content %}}
<div class="container mt-4">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h1>{surface.title or surface.name}</h1>
"""
    
    # Add primary action if persona has one
    if ux.persona_variants:
        template += """
    {% if user.persona %}
      {% if user.persona == 'coordinator' %}
        <a href="{% url 'task_create' %}" class="btn btn-primary">Create Task</a>
      {% elif user.persona == 'volunteer' %}
        <a href="{% url 'observation_create' %}" class="btn btn-primary">Log Observation</a>
      {% endif %}
    {% endif %}
"""
    
    template += "  </div>\n\n"
    
    # Add search if specified
    if ux.search:
        search_fields = ", ".join(ux.search)
        template += f"""
  <div class="mb-3">
    <input type="text" 
           class="form-control" 
           placeholder="Search {search_fields}..." 
           id="searchInput">
  </div>
"""
    
    # Add filters if specified
    if ux.filter:
        template += """
  <div class="mb-3">
    <form method="get" class="row g-3">
"""
        for field in ux.filter:
            template += f"""
      <div class="col-auto">
        <select name="filter_{field}" class="form-select">
          <option value="">All {field.title()}</option>
          {{{{ filter_choices.{field} }}}}
        </select>
      </div>
"""
        template += """
      <div class="col-auto">
        <button type="submit" class="btn btn-secondary">Filter</button>
      </div>
    </form>
  </div>
"""
    
    # Empty state
    empty_msg = ux.empty_message or "No items yet."
    template += f"""
  {{% if object_list %}}
    <table class="table table-striped">
      <thead>
        <tr>
"""
    
    # Column headers
    fields_to_show = ux.show if ux.show else [f.name for s in surface.sections for f in s.elements]
    for field in fields_to_show:
        template += f"          <th>{field.replace('_', ' ').title()}</th>\n"
    
    template += """
        </tr>
      </thead>
      <tbody>
        {% for obj in object_list %}
          <tr
"""
    
    # Add attention signal classes
    if ux.attention_signals:
        for signal in ux.attention_signals:
            condition_check = _translate_condition_to_django(signal.condition)
            template += f"""
            {{% if {condition_check} %}}class="table-{signal.css_class}"{{% endif %}}
"""
    
    template += "          >\n"
    
    # Table cells
    for field in fields_to_show:
        template += f"            <td>{{{{ obj.{field} }}}}</td>\n"
    
    # Action column if signals have actions
    if any(s.action for s in ux.attention_signals):
        template += "            <td>\n"
        for signal in ux.attention_signals:
            if signal.action:
                condition_check = _translate_condition_to_django(signal.condition)
                template += f"""
              {{% if {condition_check} %}}
                <a href="{{% url '{signal.action}' obj.pk %}}" 
                   class="btn btn-sm btn-{signal.css_class}">
                  {signal.message}
                </a>
              {{% endif %}}
"""
        template += "            </td>\n"
    
    template += """
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
"""
    
    template += f"""
    <div class="alert alert-info">
      {empty_msg}
    </div>
  {{% endif %}}
</div>
{{% endblock %}}
"""
    
    return template


def _translate_condition_to_django(condition: str) -> str:
    """Translate condition expression to Django template syntax."""
    # Phase 1: Simple string replacement
    # Phase 2: Parse and validate condition AST
    
    replacements = {
        "days_since(": "obj.days_since_",
        " in [": " in ",
        "]": "",
        "=": "==",
        "is null": "== None",
        "is not null": "!= None"
    }
    
    result = condition
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    return result
```

**File: `src/dazzle/stacks/django_micro_modular/views_ext.py`**

```python
"""Extended view generation with UX support."""

def generate_list_view_class(surface: SurfaceSpec, entity_name: str) -> str:
    """Generate ListView class with UX enhancements."""
    
    base_class = f"""
class {entity_name}ListView(ListView):
    model = {entity_name}
    template_name = '{entity_name.lower()}/list.html'
    context_object_name = 'object_list'
"""
    
    if not surface.ux:
        return base_class
    
    ux = surface.ux
    
    # Add queryset filtering
    if ux.persona_variants:
        base_class += """
    
    def get_queryset(self):
        qs = super().get_queryset()
        user_persona = getattr(self.request.user, 'persona', None)
        
"""
        for variant in ux.persona_variants:
            if variant.scope and variant.scope != "all":
                scope_filter = _translate_scope_to_django(variant.scope)
                base_class += f"""
        if user_persona == '{variant.persona}':
            qs = qs.filter({scope_filter})
"""
        
        base_class += """
        return qs
"""
    
    # Add sorting
    if ux.sort:
        sort_fields = []
        for sort_expr in ux.sort:
            parts = sort_expr.split()
            field = parts[0]
            direction = parts[1] if len(parts) > 1 else "asc"
            sort_fields.append(f"'-{field}'" if direction == "desc" else f"'{field}'")
        
        base_class += f"""
    
    def get_ordering(self):
        return [{', '.join(sort_fields)}]
"""
    
    # Add context for filters
    if ux.filter:
        base_class += """
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter choices
        context['filter_choices'] = {
"""
        for field in ux.filter:
            base_class += f"""
            '{field}': self.model.objects.values_list('{field}', flat=True).distinct(),
"""
        base_class += """
        }
        
        return context
"""
    
    return base_class


def _translate_scope_to_django(scope: str) -> str:
    """Translate scope expression to Django Q filter."""
    # Phase 1: Simple translation
    # Phase 2: Parse and build Q objects
    
    replacements = {
        "current_user": "self.request.user",
        " = ": "__exact=",
        " and ": ", ",
    }
    
    result = scope
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    return result
```

---

## Testing Requirements

### Unit Tests

**File: `tests/test_ux_parsing.py`**

```python
"""Test UX block parsing."""

def test_parse_ux_purpose():
    """Test parsing purpose line."""
    dsl = '''
surface tree_list "Trees":
  uses entity Tree
  mode: list
  
  section main:
    field species
  
  ux:
    purpose: "Monitor tree health"
'''
    appspec = parse_dsl(dsl)
    surface = appspec.surfaces[0]
    assert surface.ux is not None
    assert surface.ux.purpose.text == "Monitor tree health"


def test_parse_attention_signals():
    """Test parsing attention signals."""
    dsl = '''
surface tree_list "Trees":
  uses entity Tree
  mode: list
  
  section main:
    field species
  
  ux:
    attention critical:
      when: status = Dead
      message: "Requires immediate attention"
      action: task_create
'''
    appspec = parse_dsl(dsl)
    surface = appspec.surfaces[0]
    assert len(surface.ux.attention_signals) == 1
    signal = surface.ux.attention_signals[0]
    assert signal.level == "critical"
    assert signal.message == "Requires immediate attention"
    assert signal.action == "task_create"


def test_parse_persona_variants():
    """Test parsing persona variants."""
    dsl = '''
surface tree_list "Trees":
  uses entity Tree
  mode: list
  
  section main:
    field species
  
  ux:
    for volunteer:
      scope: steward = current_user
      show: species, condition
      action_primary: observation_create
'''
    appspec = parse_dsl(dsl)
    surface = appspec.surfaces[0]
    assert len(surface.ux.persona_variants) == 1
    variant = surface.ux.persona_variants[0]
    assert variant.persona == "volunteer"
    assert variant.scope == "steward = current_user"
    assert variant.show == ["species", "condition"]


def test_parse_workspace():
    """Test parsing workspace construct."""
    dsl = '''
workspace hub "My Hub":
  purpose: "Daily overview"
  
  priority:
    source: Tree
    filter: steward = current_user
    limit: 10
  
  metrics:
    aggregate:
      total: count(Tree)
      healthy: count(Tree where status = Healthy)
'''
    appspec = parse_dsl(dsl)
    assert len(appspec.workspaces) == 1
    workspace = appspec.workspaces[0]
    assert workspace.name == "hub"
    assert workspace.purpose == "Daily overview"
    assert len(workspace.regions) == 2
```

### Integration Tests

**File: `tests/test_django_ux_generation.py`**

```python
"""Test Django stack UX generation."""

def test_generate_list_view_with_attention():
    """Test ListView generation with attention signals."""
    # Build surface with UX
    surface = SurfaceSpec(
        name="tree_list",
        entity_ref="Tree",
        mode=SurfaceMode.LIST,
        sections=[...],
        ux=UXSpec(
            attention_signals=[
                AttentionSignal(
                    level="critical",
                    condition="status = Dead",
                    message="Urgent",
                    action="task_create"
                )
            ]
        )
    )
    
    # Generate Django code
    template = generate_list_view_ux(surface, "Tree")
    
    # Verify attention signal in template
    assert "table-danger" in template
    assert "Urgent" in template
    assert "task_create" in template


def test_generate_workspace_view():
    """Test workspace view generation."""
    workspace = WorkspaceSpec(
        name="hub",
        regions=[
            WorkspaceRegion(
                name="priority",
                source="Tree",
                filter="steward = current_user",
                limit=10
            )
        ]
    )
    
    view_code = generate_workspace_view(workspace)
    
    assert "class HubView" in view_code
    assert "steward = current_user" in view_code or "request.user" in view_code
```

---

## Documentation Updates

### User-Facing Documentation

**File: `docs/DAZZLE_DSL_REFERENCE_0_2.md`**

Create comprehensive reference including:
- All new syntax
- Complete examples
- Semantic explanations
- Stack-specific behavior notes

**File: `docs/UX_GUIDE.md`**

Create user guide:
- Philosophy (information needs not dashboards)
- How to think about attention signals
- Persona-based design patterns
- Workspace composition strategies
- Migration guide from v0.1

### Developer Documentation

**File: `docs/STACK_UX_IMPLEMENTATION.md`**

Guide for stack developers:
- How to interpret UXSpec
- Translation strategies for different frameworks
- Extension points for custom UX directives
- Testing UX generation

---

## Implementation Phases

### Phase 1: Core Parsing (Week 1)

**Goal**: Parse UX blocks into IR without code generation

**Tasks:**
1. Update grammar with new rules
2. Implement transformer methods
3. Extend IR with new Pydantic models
4. Unit tests for parsing
5. Validation rules

**Success Criteria:**
- `dazzle validate` accepts UX blocks
- IR serialization includes UX specs
- All unit tests pass

### Phase 2: Django Stack Integration (Week 2)

**Goal**: Generate Django code with UX enhancements

**Tasks:**
1. Implement template generation with attention signals
2. Implement view generation with persona filtering
3. Implement workspace views
4. Integration tests
5. Update Django stack documentation

**Success Criteria:**
- Urban Canopy example generates with UX
- Attention signals appear as styled rows
- Persona filtering works in views
- Workspace generates dashboard view

### Phase 3: Additional Stacks (Week 3)

**Goal**: Extend to other stacks

**Tasks:**
1. Express/React stack integration
2. OpenAPI stack (document UX in extensions)
3. Stack-specific tests
4. Cross-stack compatibility verification

**Success Criteria:**
- Same DSL generates across all stacks
- UX semantics preserved appropriately per platform
- All stack tests pass

### Phase 4: Polish & Documentation (Week 4)

**Goal**: Production-ready release

**Tasks:**
1. Complete user documentation
2. Example projects with UX
3. Migration guide
4. Performance optimization
5. Error message improvements

**Success Criteria:**
- Documentation complete
- 3+ example projects
- Performance benchmarks pass
- Error messages are clear and actionable

---

## Example: Complete Urban Canopy with UX

**File: `examples/urban_canopy_v2/dsl/app.dsl`**

```dsl
module urbancanopy.core

app UrbanCanopy "Urban Canopy"

# Entities (unchanged from v1)
entity Tree "Tree":
  id: uuid pk
  species: str(200) required
  location_lat: decimal(9,6) required
  location_lng: decimal(9,6) required
  street_address: str(300)
  condition_status: enum[Healthy, ModerateStress, SevereStress, Dead]=Healthy
  soil_condition: enum[Compact, Loose, Mulched, Unknown]=Unknown
  last_inspection_date: datetime
  steward: ref Volunteer
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity Volunteer "Volunteer":
  id: uuid pk
  name: str(200) required
  skill_level: enum[Beginner, Intermediate, TrainedArborist]=Beginner
  is_active: bool=true
  joined_at: datetime auto_add

entity Observation "Observation":
  id: uuid pk
  tree: ref Tree required
  observer: ref Volunteer required
  moisture_level: enum[Low, Medium, High] required
  leaf_condition: enum[Normal, Yellowing, Browning, Spotting] required
  has_insect_signs: bool
  notes: text
  submitted_at: datetime auto_add

entity MaintenanceTask "Maintenance Task":
  id: uuid pk
  tree: ref Tree required
  task_type: enum[Watering, Mulching, PruningRequest, SoilAeration] required
  created_by: ref Volunteer required
  assigned_to: ref Volunteer
  status: enum[Open, InProgress, Completed, Cancelled]=Open
  notes: text
  created_at: datetime auto_add

# Enhanced surfaces with UX layer
surface tree_list "Trees":
  uses entity Tree
  mode: list
  
  section main "All Trees":
    field species "Species"
    field street_address "Location"
    field condition_status "Condition"
    field steward "Steward"
    field last_inspection_date "Last Checked"
  
  ux:
    purpose: "Monitor tree health and coordinate stewardship across the network"
    
    sort: condition_status desc, last_inspection_date asc
    filter: condition_status, steward
    search: species, street_address
    empty: "No trees registered yet. Add your first tree to begin community stewardship."
    
    attention critical:
      when: condition_status in [SevereStress, Dead]
      message: "Urgent attention required"
      action: task_create
    
    attention warning:
      when: days_since(last_inspection_date) > 30
      message: "Overdue for inspection"
      action: observation_create
    
    attention notice:
      when: steward is null
      message: "Needs steward assignment"
      action: tree_edit
    
    for volunteer:
      scope: steward = current_user
      purpose: "Monitor your adopted trees"
      show: species, street_address, condition_status, last_inspection_date
      action_primary: observation_create
      
    for coordinator:
      scope: all
      purpose: "Oversee all trees in network"
      show_aggregate: critical_count, warning_count, unassigned_count
      action_primary: task_create
      
    for public:
      scope: all
      purpose: "Browse neighbourhood trees"
      hide: steward
      read_only: true

# Other surfaces omitted for brevity...

# Volunteer workspace
workspace volunteer_hub "My Trees":
  purpose: "Your daily tree stewardship dashboard"
  
  priority_trees:
    source: Tree
    filter: steward = current_user
    sort: attention desc
    limit: 10
    display: list
    action: observation_create
    empty: "No trees assigned yet. Contact a coordinator to adopt trees in your area."
  
  recent_observations:
    source: Observation
    filter: observer = current_user
    sort: submitted_at desc
    limit: 5
    display: timeline
    empty: "No observations yet. Check on a tree to get started!"
  
  my_tasks:
    source: MaintenanceTask
    filter: assigned_to = current_user, status in [Open, InProgress]
    sort: created_at asc
    action: task_edit
    empty: "No open tasks. Great work!"
  
  ux:
    for volunteer:
      purpose: "Your personalized tree care hub"

# Coordinator workspace
workspace coordinator_hub "Network Overview":
  purpose: "Monitor and manage the volunteer tree care network"
  
  needs_attention:
    source: Tree
    filter: condition_status in [ModerateStress, SevereStress, Dead]
    sort: condition_status desc, last_inspection_date asc
    limit: 20
    display: list
    action: task_create
    empty: "All trees are healthy! 🌳"
  
  network_health:
    aggregate:
      total_trees: count(Tree)
      healthy_pct: round(count(Tree where condition_status = Healthy) * 100 / count(Tree))
      inspections_this_week: count(Observation where submitted_at > 7_days_ago)
      active_volunteers: count(distinct Observation.observer where submitted_at > 30_days_ago)
  
  unassigned_work:
    source: MaintenanceTask
    filter: assigned_to is null, status = Open
    sort: created_at asc
    action: task_edit
    empty: "No unassigned tasks."
  
  recent_activity:
    source: Observation
    sort: submitted_at desc
    limit: 10
    display: timeline
  
  ux:
    for coordinator:
      purpose: "Comprehensive network oversight and task coordination"
```

---

## Success Metrics

### Functional Requirements Met

- ✅ Backward compatible (v0.1 DSL still valid)
- ✅ UX blocks parse without errors
- ✅ Validation catches invalid references
- ✅ Django stack generates enhanced templates
- ✅ Workspace generates composite views

### Quality Metrics

- Code coverage >85% for new code
- All existing tests still pass
- No performance regression (parse time <2x)
- Documentation coverage 100%

### User Validation

- Urban Canopy example fully functional
- 3+ additional example projects
- Positive feedback from 5+ beta testers
- Migration path documented and tested

---

## Questions for Implementation

1. **Condition Expression Parsing**: Phase 1 stores as string. Should Phase 2 build a full AST or keep simple string-based evaluation?

2. **Persona Detection**: How should stacks detect user persona? Django user attribute? Request middleware? Configuration?

3. **Workspace Routing**: Should workspaces get automatic URL routes or require explicit routing?

4. **Aggregate Caching**: Should workspace aggregates compute on every request or cache with TTL?

5. **Extension Points**: Should we expose hooks for custom attention signals or persona logic?

---

## Conclusion

This specification provides a complete implementation path for adding UX semantic layer to DAZZLE. The design maintains backward compatibility while enabling founders to express user experience concerns without prescribing visual implementation.

**Next Steps for Claude Code:**
1. Review this spec for clarity
2. Ask clarifying questions
3. Begin Phase 1 implementation
4. Checkpoint after each phase

**Key Principle**: Express *what matters to users* and *why*, not *how to display it*. Stack generators interpret semantic intent into appropriate platform idioms.