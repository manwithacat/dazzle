# Dazzle MCP Interface – DNR UI/Backend (v1 Sketch)

This document sketches an MCP tool surface for interacting with Dazzle’s Native Runtimes (DNR-Back and DNR-UI) via an LLM.

The aim is to keep UI and backend **spec-first** and **LLM-friendly**, with a small set of well-defined tools.

---

## 1. MCP Tool: list_dnr_components

List known DNR UI components (primitives and patterns).

- **Name:** `list_dnr_components`
- **Description:** Return metadata about all registered DNR UI components.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "kind": {
        "type": "string",
        "enum": ["all", "primitives", "patterns"],
        "default": "all"
      }
    },
    "required": []
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "components": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "category": { "type": "string", "enum": ["primitive", "pattern"] },
            "description": { "type": "string" },
            "propsSchemaSummary": { "type": "string" }
          },
          "required": ["name", "category"]
        }
      }
    },
    "required": ["components"]
  }
  ```

---

## 2. MCP Tool: get_dnr_component_spec

Fetch the full UISpec `ComponentSpec` for a named component.

- **Name:** `get_dnr_component_spec`
- **Description:** Return the full UISpec component definition by name.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "name": { "type": "string" }
    },
    "required": ["name"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "componentSpec": {
        "type": "object"
        // raw ComponentSpec as JSON
      }
    },
    "required": ["componentSpec"]
  }
  ```

---

## 3. MCP Tool: list_workspace_layouts

List available workspace layout primitives (from UISpec LayoutSpec).

- **Name:** `list_workspace_layouts`
- **Description:** Describe supported layout types for Dazzle workspaces.
- **Input schema:**
  ```json
  { "type": "object", "properties": {}, "required": [] }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "layouts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "kind": { "type": "string" },
            "description": { "type": "string" },
            "regions": {
              "type": "array",
              "items": { "type": "string" }
            }
          },
          "required": ["kind", "regions"]
        }
      }
    },
    "required": ["layouts"]
  }
  ```

---

## 4. MCP Tool: create_uispec_component

Create a new UISpec `ComponentSpec` from a description and a list of desired atomic components (primitives/patterns).

- **Name:** `create_uispec_component`
- **Description:** Generate and persist a new ComponentSpec in the app’s UISpec.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "name": { "type": "string" },
      "description": { "type": "string" },
      "atoms": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Names of primitive/pattern components to compose."
      },
      "propsSchemaHint": {
        "type": "string",
        "description": "Optional textual hint describing expected props."
      }
    },
    "required": ["name", "description", "atoms"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "componentSpec": {
        "type": "object"
        // generated ComponentSpec
      },
      "location": {
        "type": "string",
        "description": "Identifier/path where the spec was stored in the project."
      }
    },
    "required": ["componentSpec", "location"]
  }
  ```

---

## 5. MCP Tool: patch_uispec_component

Apply a structured patch to an existing UISpec component.

- **Name:** `patch_uispec_component`
- **Description:** Modify an existing ComponentSpec by applying JSON-patch-like operations.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "name": { "type": "string" },
      "patch": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "op": { "type": "string", "enum": ["add", "remove", "replace"] },
            "path": { "type": "string" },
            "value": {}
          },
          "required": ["op", "path"]
        }
      }
    },
    "required": ["name", "patch"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "componentSpec": {
        "type": "object"
      }
    },
    "required": ["componentSpec"]
  }
  ```

---

## 6. MCP Tool: compose_workspace

Create or update a WorkspaceSpec wiring components into a layout.

- **Name:** `compose_workspace`
- **Description:** Create or update a workspace using existing components and a chosen layout type.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "workspaceName": { "type": "string" },
      "persona": { "type": "string" },
      "layoutKind": { "type": "string" },
      "regionComponents": {
        "type": "object",
        "additionalProperties": {
          "type": "string"
        },
        "description": "Map from layout region name to ComponentSpec.name"
      },
      "routes": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "path": { "type": "string" },
            "component": { "type": "string" }
          },
          "required": ["path", "component"]
        }
      }
    },
    "required": ["workspaceName", "layoutKind", "regionComponents", "routes"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "workspaceSpec": {
        "type": "object"
      }
    },
    "required": ["workspaceSpec"]
  }
  ```

---

## 7. MCP Tool: list_backend_services

Expose backend services (from BackendSpec) to the LLM for wiring Effects.

- **Name:** `list_backend_services`
- **Description:** List available backend services (ServiceSpec) with input/output summaries.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "entityName": {
        "type": "string",
        "description": "Optional filter by entity name."
      }
    },
    "required": []
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "services": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "entity": { "type": "string" },
            "kind": { "type": "string" },
            "inputSummary": { "type": "string" },
            "outputSummary": { "type": "string" }
          },
          "required": ["name"]
        }
      }
    },
    "required": ["services"]
  }
  ```

---

## 8. MCP Tool: get_backend_service_spec

Fetch the full ServiceSpec for a given service.

- **Name:** `get_backend_service_spec`
- **Description:** Return the full ServiceSpec JSON for a backend service by name.
- **Input schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "name": { "type": "string" }
    },
    "required": ["name"]
  }
  ```
- **Output schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "serviceSpec": {
        "type": "object"
      }
    },
    "required": ["serviceSpec"]
  }
  ```

---

## 9. Usage pattern (LLM agent perspective)

Typical agent workflow:

1. Call `list_backend_services` (optionally filtered by entity) to see what the backend can do.
2. Call `list_dnr_components` and `list_workspace_layouts` to understand UI capabilities.
3. Decide on:
   - which pattern components to use (e.g. `FilterableTable`, `CRUDPage`)
   - which backend services to bind to (e.g. `listClients`, `createClient`).
4. Call `create_uispec_component` to create new UISpec components.
5. Call `compose_workspace` to assemble components into a WorkspaceSpec.
6. Use `patch_uispec_component` for incremental refinements.

All interactions are **spec-level**; the actual Dazzle runtimes (DNR-Back, DNR-UI) read the updated specs and serve the live app.

End of Dazzle MCP Interface – DNR v1 Sketch.
