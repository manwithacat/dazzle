# DNR CLI Reference

Complete reference for `dazzle dnr` commands.

## Commands Overview

| Command | Description |
|---------|-------------|
| `dazzle dnr info` | Show installation status |
| `dazzle dnr build-ui` | Generate UI artifacts |
| `dazzle dnr build-api` | Generate API specification |
| `dazzle dnr serve` | Run development server |

---

## dazzle dnr info

Show DNR installation status and available features.

```bash
dazzle dnr info
```

**Output:**
```
Dazzle Native Runtime (DNR) Status
==================================================
DNR Backend:   ✓ installed
DNR UI:        ✓ installed
FastAPI:       ✓ installed
Uvicorn:       ✓ installed

Available Commands:
  dazzle dnr build-ui   Generate UI (Vite/JS/HTML)
  dazzle dnr build-api  Generate API spec
  dazzle dnr serve      Run development server
```

---

## dazzle dnr build-ui

Generate UI artifacts from your AppSpec.

```bash
dazzle dnr build-ui [OPTIONS]
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--manifest` | `-m` | `dazzle.toml` | Path to manifest file |
| `--out` | `-o` | `./dnr-ui` | Output directory |
| `--format` | `-f` | `vite` | Output format |

### Formats

#### vite (default)
Full Vite project with ES modules. Production-ready.

```bash
dazzle dnr build-ui --format vite -o ./my-app
```

Generated structure:
```
my-app/
├── package.json
├── vite.config.js
└── src/
    ├── index.html
    ├── main.js
    ├── ui-spec.json
    └── dnr/
        ├── signals.js
        ├── state.js
        ├── dom.js
        ├── bindings.js
        ├── components.js
        ├── renderer.js
        ├── theme.js
        ├── actions.js
        ├── app.js
        └── index.js
```

To run:
```bash
cd my-app
npm install
npm run dev
```

#### js
Split HTML/JS files. Good for development without Node.js.

```bash
dazzle dnr build-ui --format js -o ./app
```

Generated files:
- `index.html` - Main HTML file
- `dnr-runtime.js` - Combined runtime
- `app.js` - Application code
- `ui-spec.json` - UI specification

To run:
```bash
cd app
python -m http.server 8000
```

#### html
Single HTML file with embedded runtime. Quickest preview.

```bash
dazzle dnr build-ui --format html -o ./preview
```

Generated file:
- `index.html` - Self-contained application

Open directly in browser - no server needed.

### Examples

```bash
# Default: Vite project
dazzle dnr build-ui

# Single HTML for quick preview
dazzle dnr build-ui --format html -o ./preview

# Use different manifest
dazzle dnr build-ui -m path/to/dazzle.toml

# Split JS files
dazzle dnr build-ui --format js -o ./dev-app
```

---

## dazzle dnr build-api

Generate API specification from your AppSpec.

```bash
dazzle dnr build-api [OPTIONS]
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--manifest` | `-m` | `dazzle.toml` | Path to manifest file |
| `--out` | `-o` | `./dnr-api` | Output directory |
| `--format` | `-f` | `json` | Output format |

### Formats

#### json (default)
BackendSpec as JSON file.

```bash
dazzle dnr build-api --format json -o ./api
```

Generated file:
- `backend-spec.json` - Complete API specification

#### python
Python stub module with JSON spec.

```bash
dazzle dnr build-api --format python -o ./api
```

Generated files:
- `api_stub.py` - Runnable FastAPI stub
- `backend-spec.json` - API specification

To run:
```bash
cd api
pip install fastapi uvicorn
uvicorn api_stub:app --reload
```

### Examples

```bash
# JSON spec only
dazzle dnr build-api

# Python stub for quick server
dazzle dnr build-api --format python -o ./server

# Custom manifest location
dazzle dnr build-api -m ../project/dazzle.toml
```

---

## dazzle dnr serve

Run development server with API and UI preview.

```bash
dazzle dnr serve [OPTIONS]
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--manifest` | `-m` | `dazzle.toml` | Path to manifest file |
| `--port` | `-p` | `8000` | Port to serve on |
| `--host` | | `127.0.0.1` | Host to bind to |
| `--reload` | `-r` | `false` | Enable auto-reload |
| `--ui-only` | | `false` | Serve UI only (no API) |

### Requirements

Full server requires:
- FastAPI
- Uvicorn

Install with:
```bash
pip install fastapi uvicorn
```

### Endpoints

When running with full API:

| Endpoint | Description |
|----------|-------------|
| `/` | UI preview |
| `/ui` | UI preview (alternate) |
| `/api/` | API root |
| `/docs` | Interactive API documentation |
| `/redoc` | Alternative API documentation |

### Examples

```bash
# Default server on localhost:8000
dazzle dnr serve

# Different port
dazzle dnr serve --port 3000

# Auto-reload on DSL changes
dazzle dnr serve --reload

# Bind to all interfaces (for Docker/remote access)
dazzle dnr serve --host 0.0.0.0

# UI only (no FastAPI required)
dazzle dnr serve --ui-only
```

### UI-Only Mode

If FastAPI is not installed, use `--ui-only` to serve just the UI:

```bash
dazzle dnr serve --ui-only
```

This uses Python's built-in HTTP server and doesn't require any additional packages.

---

## Common Workflows

### Development Preview

Quick preview while editing DSL:

```bash
# Terminal 1: Serve with reload
dazzle dnr serve --reload

# Terminal 2: Edit your DSL
vim dsl/app.dsl
```

### Production Build

Generate production-ready artifacts:

```bash
# Build Vite project
dazzle dnr build-ui --format vite -o ./dist/frontend

# Build API spec
dazzle dnr build-api --format python -o ./dist/backend

# Deploy frontend
cd dist/frontend && npm install && npm run build

# Deploy backend
cd dist/backend && uvicorn api_stub:app
```

### CI/CD Integration

```yaml
# GitHub Actions example
steps:
  - name: Validate DSL
    run: dazzle validate

  - name: Build UI
    run: dazzle dnr build-ui --format vite -o ./build

  - name: Build API
    run: dazzle dnr build-api -o ./api
```
