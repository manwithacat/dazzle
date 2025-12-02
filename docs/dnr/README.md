# Dazzle Native Runtime (DNR)

DNR is Dazzle's framework-agnostic runtime system that generates working applications directly from your DSL specifications—no React or Vue required.

## Overview

DNR provides two runtime components:

- **DNR-Back**: Generates FastAPI backends from your entities and services
- **DNR-UI**: Generates pure JavaScript frontends with signals-based reactivity

## Quick Start

```bash
# Check DNR installation status
dazzle dnr info

# Generate a Vite project from your DSL
dazzle dnr build-ui --format vite -o ./my-app

# Generate API specification
dazzle dnr build-api -o ./api

# Run development server (API + UI)
dazzle dnr serve
```

## Documentation

- [Quick Start Guide](./QUICKSTART.md) - Get running in 5 minutes
- [CLI Reference](./CLI.md) - Complete command reference
- [Architecture](./ARCHITECTURE.md) - How DNR works
- [BackendSpec Reference](./BACKEND_SPEC.md) - Backend specification types
- [UISpec Reference](./UI_SPEC.md) - UI specification types

## Why DNR?

### LLM-First Design
Specifications are structured for deterministic generation and easy patching by LLMs.

### No Framework Lock-in
Pure JavaScript UI with signals—no React, Vue, or build complexity required.

### Full Stack from DSL
Your Dazzle DSL compiles to both backend API and frontend UI automatically.

### Multiple Output Formats
- **Vite**: Production-ready bundled application
- **JS**: Split files for development
- **HTML**: Single-file preview

## Pipeline

```
DSL (your app.dsl)
    ↓
AppSpec (Dazzle IR)
    ├──→ BackendSpec ──→ FastAPI App
    │                    ├── REST endpoints
    │                    ├── Pydantic models
    │                    └── CRUD services
    │
    └──→ UISpec ──→ JavaScript Runtime
                    ├── Signals-based state
                    ├── Component system
                    └── Theme engine
```

## Requirements

- Python 3.11+
- Dazzle 0.4.0+

Optional:
- FastAPI + Uvicorn (for `dazzle dnr serve`)
- Node.js 18+ (for Vite development server)

## Installation

DNR is included with Dazzle. To use the full server capabilities:

```bash
# Install FastAPI support
pip install fastapi uvicorn

# Verify installation
dazzle dnr info
```
