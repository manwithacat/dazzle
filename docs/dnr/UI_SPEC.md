# UISpec Reference

Complete reference for DNR UI specification types.

## Overview

UISpec defines your application's frontend structure:
- Workspaces (pages/layouts)
- Components (reusable UI elements)
- State (reactive data)
- Actions (event handlers)
- Themes (styling)

## UISpec

Root specification for the UI.

```python
class UISpec:
    name: str                           # Application name
    workspaces: list[WorkspaceSpec]     # Pages/layouts
    components: list[ComponentSpec]      # UI components
    themes: list[ThemeSpec]             # Theme definitions
    default_theme: str = "default"      # Active theme
```

## WorkspaceSpec

Defines a page or screen with its layout.

```python
class WorkspaceSpec:
    name: str                           # Workspace identifier
    layout: LayoutSpec                  # Layout structure
    routes: list[RouteSpec]             # URL routes
    state: list[StateSpec]              # Workspace-level state
```

### LayoutSpec

Defines the structural layout:

```python
# Single column
SingleColumnLayout(main="MainContent")

# Two columns with header
TwoColumnWithHeaderLayout(
    header="Header",
    main="MainContent",
    secondary="Sidebar"
)

# Application shell
AppShellLayout(
    sidebar="Navigation",
    main="Content",
    header="TopBar"
)

# Custom layout
CustomLayout(
    regions={"left": "Sidebar", "center": "Content", "right": "Details"}
)
```

### RouteSpec

Maps URLs to components:

```python
class RouteSpec:
    path: str                           # URL path
    component: str                      # Component name
    params: dict[str, str]              # Path parameters
```

Example:
```python
RouteSpec(path="/tasks", component="TaskList")
RouteSpec(path="/tasks/{id}", component="TaskDetail", params={"id": "string"})
```

## ComponentSpec

Defines a reusable UI component.

```python
class ComponentSpec:
    name: str                           # Component name
    category: str                       # "primitive", "pattern", "custom"
    props_schema: PropsSchema           # Expected props
    view: ViewNode                      # Render structure
    state: list[StateSpec]              # Local state
    actions: list[ActionSpec]           # Event handlers
```

### PropsSchema

Defines component props:

```python
class PropsSchema:
    fields: list[PropFieldSpec]
```

```python
class PropFieldSpec:
    name: str                           # Prop name
    type: str                           # Type (string, number, boolean, etc.)
    required: bool = False              # Is required?
    default: Any | None                 # Default value
```

Example:
```python
PropsSchema(fields=[
    PropFieldSpec(name="title", type="string", required=True),
    PropFieldSpec(name="count", type="number", default=0),
    PropFieldSpec(name="visible", type="boolean", default=True),
])
```

## ViewNode

Declarative structure for rendering.

### ElementNode

Basic DOM element:

```python
class ElementNode:
    tag: str                            # HTML tag
    props: dict[str, Binding]           # Attributes/properties
    children: list[ViewNode]            # Child nodes
```

Example:
```python
ElementNode(
    tag="div",
    props={"class": LiteralBinding("card")},
    children=[
        ElementNode(tag="h2", children=[TextNode(text=PropBinding("title"))]),
        ElementNode(tag="p", children=[TextNode(text=PropBinding("description"))])
    ]
)
```

### ConditionalNode

Conditional rendering:

```python
class ConditionalNode:
    condition: Binding                  # Condition to evaluate
    then_branch: ViewNode               # Render if true
    else_branch: ViewNode | None        # Render if false
```

Example:
```python
ConditionalNode(
    condition=StateBinding("isLoading"),
    then_branch=ElementNode(tag="div", props={"class": LiteralBinding("spinner")}),
    else_branch=ElementNode(tag="div", children=[...])
)
```

### LoopNode

Iterate over collections:

```python
class LoopNode:
    source: Binding                     # Collection to iterate
    item_name: str                      # Variable name for each item
    index_name: str | None              # Optional index variable
    body: ViewNode                      # Template for each item
```

Example:
```python
LoopNode(
    source=StateBinding("tasks"),
    item_name="task",
    body=ElementNode(
        tag="li",
        children=[TextNode(text=DerivedBinding("task.title"))]
    )
)
```

### SlotNode

Placeholder for child content:

```python
class SlotNode:
    name: str = "default"               # Slot name
```

### TextNode

Text content:

```python
class TextNode:
    text: Binding                       # Text content (can be dynamic)
```

## Binding

Data binding for dynamic content.

### LiteralBinding

Static value:

```python
LiteralBinding(value="Hello World")
LiteralBinding(value=42)
LiteralBinding(value=True)
```

### PropBinding

Bind to component prop:

```python
PropBinding(path="title")
PropBinding(path="user.name")  # Nested path
```

### StateBinding

Bind to local state:

```python
StateBinding(path="count")
StateBinding(path="form.email")
```

### WorkspaceStateBinding

Bind to workspace-level state:

```python
WorkspaceStateBinding(path="selectedId")
```

### AppStateBinding

Bind to application-level state:

```python
AppStateBinding(path="currentUser")
```

### DerivedBinding

Computed value (JavaScript expression):

```python
DerivedBinding(expr="count * 2")
DerivedBinding(expr="items.length > 0 ? 'Has items' : 'Empty'")
DerivedBinding(expr="task.title.toUpperCase()")
```

## StateSpec

Defines reactive state.

```python
class StateSpec:
    name: str                           # State variable name
    scope: StateScope                   # State scope
    initial: Any                        # Initial value
    persistent: bool = False            # Persist to storage?
```

### StateScope

| Scope | Lifetime | Storage |
|-------|----------|---------|
| `LOCAL` | Component | Memory |
| `WORKSPACE` | Page/workspace | Memory |
| `APP` | Application | Memory |
| `SESSION` | Browser session | sessionStorage |

Example:
```python
StateSpec(name="count", scope=StateScope.LOCAL, initial=0)
StateSpec(name="filter", scope=StateScope.WORKSPACE, initial="all")
StateSpec(name="theme", scope=StateScope.APP, initial="light", persistent=True)
```

## ActionSpec

Defines event handlers.

```python
class ActionSpec:
    name: str                           # Action name
    inputs: PropsSchema | None          # Action parameters
    transitions: list[TransitionSpec]   # State updates
    effect: EffectSpec | None           # Side effect
```

### TransitionSpec

State update:

```python
class TransitionSpec:
    target_state: str                   # State to update
    patch: PatchSpec                    # Update operation
```

### PatchSpec

Update operation:

```python
class PatchSpec:
    operation: str                      # "set", "merge", "append", "remove"
    value: Binding                      # New value
```

Example:
```python
ActionSpec(
    name="increment",
    transitions=[
        TransitionSpec(
            target_state="count",
            patch=PatchSpec(operation="set", value=DerivedBinding("count + 1"))
        )
    ]
)
```

### EffectSpec

Side effects:

```python
# API call
FetchEffect(
    service="TaskService",
    operation="list",
    on_success="handleTasks",
    on_error="handleError"
)

# Navigation
NavigateEffect(
    route="/tasks/{id}",
    params={"id": PropBinding("taskId")}
)
```

## ThemeSpec

Defines visual styling.

```python
class ThemeSpec:
    name: str                           # Theme name
    tokens: ThemeTokens                 # Design tokens
    variants: list[VariantSpec]         # Component variants
```

### ThemeTokens

```python
class ThemeTokens:
    colors: dict[str, str]              # Color palette
    spacing: dict[str, str]             # Spacing scale
    radii: dict[str, str]               # Border radii
    typography: dict[str, TextStyle]    # Text styles
```

Example:
```python
ThemeTokens(
    colors={
        "primary": "#3b82f6",
        "secondary": "#64748b",
        "success": "#22c55e",
        "danger": "#ef4444",
        "background": "#ffffff",
        "text": "#1e293b",
    },
    spacing={
        "xs": "0.25rem",
        "sm": "0.5rem",
        "md": "1rem",
        "lg": "1.5rem",
        "xl": "2rem",
    },
    radii={
        "sm": "0.25rem",
        "md": "0.5rem",
        "lg": "1rem",
        "full": "9999px",
    },
    typography={
        "heading": TextStyle(family="system-ui", size="1.5rem", weight="600"),
        "body": TextStyle(family="system-ui", size="1rem", weight="400"),
        "small": TextStyle(family="system-ui", size="0.875rem", weight="400"),
    }
)
```

### TextStyle

```python
class TextStyle:
    family: str                         # Font family
    size: str                           # Font size
    weight: str                         # Font weight
    line_height: str | None             # Line height
    letter_spacing: str | None          # Letter spacing
```

### VariantSpec

Component-specific styling:

```python
class VariantSpec:
    name: str                           # Variant name
    component: str                      # Target component
    tokens: dict[str, str]              # Token overrides
```

## Complete Example

```python
UISpec(
    name="task_manager",
    workspaces=[
        WorkspaceSpec(
            name="dashboard",
            layout=SingleColumnLayout(main="TaskList"),
            routes=[RouteSpec(path="/", component="TaskList")],
            state=[StateSpec(name="filter", scope=StateScope.WORKSPACE, initial="all")]
        )
    ],
    components=[
        ComponentSpec(
            name="TaskList",
            category="pattern",
            props_schema=PropsSchema(fields=[]),
            view=ElementNode(
                tag="div",
                props={"class": LiteralBinding("task-list")},
                children=[
                    LoopNode(
                        source=StateBinding("tasks"),
                        item_name="task",
                        body=ElementNode(
                            tag="div",
                            props={"class": LiteralBinding("task-item")},
                            children=[
                                TextNode(text=DerivedBinding("task.title"))
                            ]
                        )
                    )
                ]
            ),
            state=[StateSpec(name="tasks", scope=StateScope.LOCAL, initial=[])],
            actions=[
                ActionSpec(
                    name="loadTasks",
                    effect=FetchEffect(service="TaskService", operation="list", on_success="setTasks")
                )
            ]
        )
    ],
    themes=[
        ThemeSpec(
            name="default",
            tokens=ThemeTokens(
                colors={"primary": "#3b82f6", "background": "#ffffff"},
                spacing={"md": "1rem"},
                radii={"md": "0.5rem"},
                typography={}
            )
        )
    ],
    default_theme="default"
)
```

## JSON Serialization

UISpec can be serialized to JSON:

```python
spec.model_dump_json(indent=2)
```

And restored:

```python
UISpec.model_validate_json(json_string)
```
