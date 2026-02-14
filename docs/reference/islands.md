# UI Islands

Islands are self-contained, interactive JavaScript components that mount into server-rendered pages. They let you add client-side interactivity — charts, editors, drag-and-drop — without coupling the entire app to a JavaScript framework.

## Overview

Dazzle apps are server-rendered with htmx. Most interactions work without JavaScript. But some features (data visualizations, rich editors, real-time updates) need client-side code. Islands solve this by providing designated mount points where JavaScript components take over a specific DOM subtree.

Each island:

- Owns its DOM subtree
- Manages its own state
- Communicates with the server through a defined API contract
- Cleans up when removed from the page (including htmx swaps)

## DSL Syntax

```dsl
island <name> "<Title>":
  entity: <EntityName>
  src: "<path/to/island.js>"
  fallback: "<HTML shown before JS loads>"
  prop <name>: <type> [= default]
  event <name>:
    detail: [field1, field2]
```

All fields except `name` are optional.

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier. Used for mount points and API routes. |
| `title` | No | Human-readable display name |
| `entity` | No | Entity reference. Generates a data API at `/api/islands/{name}/data` |
| `src` | No | JavaScript entry point. Defaults to `/static/islands/{name}/index.js` |
| `fallback` | No | HTML rendered server-side before JavaScript loads |

### Props

Typed properties passed to the JavaScript component:

```dsl
prop chart_type: str = "bar"
prop count: int = 10
prop enabled: bool = true
prop ratio: float = 3.14
prop label: str                  # no default
```

Supported types: `str`, `int`, `bool`, `float`. Props are serialized to JSON and passed to the mount function.

### Events

Document the CustomEvents the island may emit:

```dsl
event chart_clicked:
  detail: [task_id, series_index]
```

Events are informational — they document the contract for consumers. The actual event emission is handled by the island's JavaScript code.

## JavaScript Contract

Each island module must export a `mount` function:

```javascript
// islands/my-component/index.js
export function mount({ el, props, apiBase }) {
  // el:      HTMLElement — the <div data-island="..."> mount point
  // props:   object     — parsed props with defaults applied
  // apiBase: string     — base URL for API endpoints ("" if no entity)

  // ... initialize component ...

  // Optionally return a cleanup function
  return function unmount(el) {
    // cleanup timers, listeners, etc.
  };
}
```

The cleanup function is called when:

- The island element is removed from the DOM
- htmx swaps content that contains the island
- The page navigates away

## Generated HTML

The framework renders each island as:

```html
<div data-island="task_chart"
     data-island-src="/static/islands/task-chart/index.js"
     data-island-props='{"chart_type":"bar","height":400}'
     data-island-api-base="/api/islands/task_chart"
     class="dz-island">
  Loading task chart...
</div>
```

The island loader (`dz-islands.js`) handles:

1. Mounting islands on page load
2. Rescanning after htmx swaps (`htmx:afterSettle`)
3. Unmounting before htmx replaces content (`htmx:beforeSwap`)
4. Deduplication (prevents double-mounting)

## API Routes

When an island declares an `entity` binding, the framework generates:

```
GET /api/islands/{island_name}/data?limit=100&offset=0
```

Response:

```json
{
  "items": [...],
  "island": "task_chart"
}
```

No route is created for islands without an entity binding.

## Examples

### Data-Bound Chart

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool = false

island task_chart "Task Progress":
  entity: Task
  src: "islands/task-chart/index.js"
  fallback: "Loading chart..."
  prop chart_type: str = "bar"
  prop period: str = "week"
```

```javascript
// islands/task-chart/index.js
export async function mount({ el, props, apiBase }) {
  const response = await fetch(`${apiBase}/data`);
  const data = await response.json();

  renderChart(el, {
    items: data.items,
    type: props.chart_type,
    period: props.period,
  });
}
```

### Simple Effect (No Entity)

```dsl
island confetti "Celebration Confetti":
  src: "islands/confetti/index.js"
  fallback: "<p>Celebration!</p>"
```

```javascript
export function mount({ el }) {
  const button = document.createElement("button");
  button.textContent = "Celebrate";
  button.addEventListener("click", () => launchConfetti());
  el.appendChild(button);

  return () => button.remove();
}
```

### Event-Emitting Island

```dsl
island timeline_editor "Timeline Editor":
  entity: Event
  src: "islands/timeline/index.js"
  event time_updated:
    detail: [event_id, new_time]
  event event_deleted:
    detail: [event_id]
```

```javascript
export function mount({ el, props, apiBase }) {
  el.addEventListener("click", (e) => {
    if (e.target.dataset.action === "delete") {
      el.dispatchEvent(
        new CustomEvent("event_deleted", {
          detail: { event_id: e.target.dataset.id },
        })
      );
    }
  });
}
```

## File Structure

Islands follow this layout:

```
static/islands/
  my-component/
    index.js          # ES module with mount() export
    styles.css        # Scoped styles (optional)
```

## Best Practices

1. **Return cleanup functions** — clear timers, remove listeners, abort fetches
2. **Handle errors** — wrap fetch calls and show fallback UI on failure
3. **Scope styles** — use BEM or CSS modules to avoid global collisions
4. **Keep islands focused** — one responsibility per island
5. **Use progressive enhancement** — provide meaningful `fallback` content
6. **Lazy load dependencies** — use dynamic `import()` for large libraries
7. **Document events** — declare all CustomEvents in the DSL for discoverability
