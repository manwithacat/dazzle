# DNR Quick Start Guide

Get a working application from your Dazzle DSL in under 5 minutes.

## Prerequisites

- Dazzle 0.4.0+ installed
- A Dazzle project with `dazzle.toml`

## Step 1: Check Your Setup

```bash
dazzle info
```

You should see:
```
Dazzle Native Runtime (DNR) Status
==================================================
DNR Backend:   ✓ installed
Dazzle UI:        ✓ installed
```

## Step 2: Validate Your DSL

```bash
dazzle validate
```

Fix any errors before proceeding.

## Step 3: Generate UI

### Option A: Single HTML Preview (Fastest)

```bash
dazzle build-ui --format html -o ./preview
```

Open `./preview/index.html` in your browser.

### Option B: Vite Project (Recommended)

```bash
dazzle build-ui --format vite -o ./my-app
cd my-app
npm install
npm run dev
```

Visit `http://localhost:5173`

### Option C: Split JS Files

```bash
dazzle build-ui --format js -o ./app
cd app
python -m http.server 8000
```

Visit `http://localhost:8000`

## Step 4: Generate API (Optional)

```bash
dazzle build-api -o ./api
```

Creates `backend-spec.json` with your API definition.

## Step 5: Run Full Stack Server

If you have FastAPI installed:

```bash
pip install fastapi uvicorn
dazzle serve
```

This starts:
- UI at `http://localhost:8000/`
- API at `http://localhost:8000/api/`
- Docs at `http://localhost:8000/docs`

## Example: Simple Task Manager

Given this DSL:

```dsl
app simple_task "Simple Task Manager"

module simple_task

entity Task "Task":
    id: uuid pk
    title: str(200) required
    status: str = "pending"
    created_at: datetime auto_add

surface task_list "Task List" -> Task list:
    section main:
        field title
        field status
```

Generate and run:

```bash
dazzle build-ui --format html -o ./task-app
open ./task-app/index.html
```

## What Gets Generated

### Vite Project Structure

```
my-app/
├── package.json
├── vite.config.js
└── src/
    ├── index.html
    ├── main.js
    ├── ui-spec.json
    └── dnr/
        ├── signals.js      # Reactive state
        ├── state.js        # State management
        ├── dom.js          # DOM utilities
        ├── bindings.js     # Data binding
        ├── components.js   # Component system
        ├── renderer.js     # View rendering
        ├── theme.js        # Theme engine
        ├── actions.js      # Action handlers
        ├── app.js          # App initialization
        └── index.js        # Entry point
```

### API Spec Structure

```json
{
  "name": "simple_task",
  "entities": [...],
  "services": [...],
  "endpoints": [...]
}
```

## Next Steps

- [CLI Reference](../reference/cli.md) - All command options
- [Architecture](../architecture/overview.md) - How DNR works internally
- [Architecture](../architecture/overview.md) - Customize your UI
