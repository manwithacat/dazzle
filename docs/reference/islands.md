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
```

All fields except `name` are optional.

> **Status today: only `entity:` has a runtime effect.** It mounts the data
> route described under [API Routes](#api-routes). No DSL construct places an
> island on a page, so the framework does not render any island mount point:
> `title`, `src:` and `fallback:` are parsed and stored on `IslandSpec` but not
> read, and `dazzle validate` emits a warning naming DD-011 for each island that
> declares them. Rendering is parked in
> [DD-011](../decisions/DD-011-island-rendering.md). To mount an island today,
> emit the mount point yourself (see [Mount-point HTML](#mount-point-html)) from a
> custom route or `render:` surface and load `dz-islands.js` via
> `[ui] app_scripts = ["/static/js/dz-islands.js"]` in `dazzle.toml`.

### Fields

| Field | Required | Runtime effect today |
|-------|----------|----------------------|
| `name` | Yes | Unique identifier; names the API route |
| `title` | No | None (parsed, not rendered — DD-011) |
| `entity` | No | Generates a data API at `/_dazzle/islands/{name}/data` |
| `src` | No | None (parsed, not rendered — DD-011) |
| `fallback` | No | None (parsed, not rendered — DD-011) |

## JavaScript Contract

Each island module must export a `mount` function:

```javascript
// islands/my-component/index.js
export function mount({ el, props, apiBase }) {
  // el:      HTMLElement — the <div data-island="..."> mount point
  // props:   object     — parsed `data-island-props` JSON
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

## Mount-point HTML

The framework does not generate this markup from the DSL yet (DD-011). The
island loader mounts any element of this shape, which is what a custom route
or `render:` surface emits by hand (the built-in signing pad does the same):

```html
<div data-island="task_chart"
     data-island-src="/static/islands/task-chart/index.js"
     data-island-props='{"chart_type":"bar","height":400}'
     data-island-api-base="/_dazzle/islands/task_chart"
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
GET /_dazzle/islands/{island_name}/data?limit=100&offset=0
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
```

```javascript
// islands/task-chart/index.js
export async function mount({ el, props, apiBase }) {
  const response = await fetch(`${apiBase}/data`);
  const data = await response.json();

  renderChart(el, {
    items: data.items,
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
