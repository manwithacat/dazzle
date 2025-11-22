# AppSpec Normalisation Specification — Expert LLM Imperatives (v1)

## PURPOSE
Transform multiple DSL-defined system specifications into a unified *AppSpec* using mathematically rigorous graph‑normalisation and equivalence‑class joins. Implement all instructions exactly as stated.

---

## 1. BUILD LOCAL SPECIFICATIONS

### 1.1 Parse each input DSL
- Parse each DSL program into a **Local Spec**.
- Represent the Local Spec as a *typed, directed multigraph with ports*.
- Emit JSON describing:
  - Nodes: `id`, `kind`, `name`, `description`.
  - Edges: `id`, `kind`, `source`, `target`.
  - For each node: ordered input and output ports.
    - Each port: `port_id`, `name`, `candidate_type`, `description`.

### 1.2 Apply strict typing to ports
- For every port, assign a *candidate global type identifier*.
- Preserve port direction.

### 1.3 Extract the local interface
- Identify all *exposed* ports (inputs/outputs interacting with the outside world).
- Emit a structured record for each exposed port with:
  - DSL name
  - Spec name
  - Node ID
  - Port ID
  - Direction (in/out)
  - Candidate type
  - Port semantic description
  - Port data shape (fields if available)

---

## 2. DEFINE GLOBAL TYPE CATALOGUE

### 2.1 Construct catalogue T
- Build or extend a **global type catalogue** T.
- Each type must include:
  - Canonical name
  - Structured field definitions
  - Constraints (if any)
  - Semantic description
  - Optional version information

### 2.2 Link ports to global types
- For each interface port, bind its candidate type to one type in T.
- Where binding cannot be determined uniquely:
  - Propose a set of possible matches.
  - Evaluate name similarity, field shape compatibility, and semantic description.

---

## 3. BUILD EQUIVALENCE RELATION OVER PORTS

### 3.1 Universal set of ports
- Construct U = union of exposed ports across all Local Specs.

### 3.2 Define equivalence relation ~
- Establish equivalence p ~ q if and only if:
  - Ports share the same global type in T, and
  - Their directions are compatible (output → input).
- Allow additional criteria where helpful:
  - Semantic name similarity
  - Field-shape compatibility
  - Textual description proximity

### 3.3 Compute equivalence classes
- Partition U into equivalence classes under ~.
- Each class is a **junction point** for graph unification.

---

## 4. BUILD AppSpec BY QUOTIENTING LOCAL SPECS

### 4.1 Construct quotient graph
- For each equivalence class [p]~, create a **single canonical port** in AppSpec.
- Rewrite all Local Specs so that ports in [p]~ map to the canonical port.

### 4.2 Create embeddings fᵢ : LocalSpec → AppSpec
- For each Local Spec Gᵢ, construct a structure-preserving embedding fᵢ that:
  - Maps nodes to nodes, edges to edges.
  - Preserves node kinds, edge kinds, port types, and port direction.
  - Maps equivalent ports from different DSLs into the same canonical AppSpec port.

### 4.3 Assemble the unified graph
- Merge all embedded nodes and edges.
- Ensure all port identifications follow the equivalence classes.
- Resolve naming collisions using deterministic canonicalisation rules.

---

## 5. EMIT AppSpec STRUCTURE

### 5.1 Emit global types
- Output all global types T in structured JSON/YAML.

### 5.2 Emit component blocks
- For each Local Spec, output:
  - Component ID
  - Originating DSL
  - Nodes
  - Edges
  - Input/Output interface after canonicalisation

### 5.3 Emit junction definitions
- For each equivalence class [p]~, output:
  - Junction ID
  - Global type
  - All participating component-port mappings

### 5.4 Output full AppSpec
- Emit complete JSON or YAML object containing:
  - Types
  - Components
  - Junctions
  - Global graph structure

---

## 6. USE AppSpec TO IMPROVE DSL

### 6.1 Check consistency
- Validate that junctions have valid producers and consumers.
- Validate type compatibility.
- Detect cycles and disconnected components.

### 6.2 Infer DSL grammar improvements
- Analyse AppSpec for recurring structural patterns.
- Propose DSL syntax extensions for:
  - Pipelines
  - Event-routing
  - Request/response patterns
  - Sagas or orchestrations

### 6.3 Support DSL regeneration and refactoring
- From AppSpec, regenerate Local DSL fragments consistently.
- Enforce canonical types at the DSL level.
- Enforce cross-DSL interactions via declared junctions.

---

## 7. IMPLEMENTATION CONTRACT (MANDATORY)
You must obey the following rules when applying this specification:

1. Treat all Local Specs as typed directed graphs with port structure.
2. Build equivalence classes only via explicit rules.
3. Always emit AppSpec as a single unified structured object.
4. Ensure mathematical rigour when performing graph quotienting.
5. Preserve the semantics of each Local Spec under the embedding.
6. Never merge ports or nodes that violate typing or direction constraints.
7. Always normalise names deterministically when collisions occur.

---

END OF SPECIFICATION
