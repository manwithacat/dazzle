# Services

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Services declare custom business logic in DSL with implementation in Python or TypeScript stubs. DAZZLE separates concerns into three layers: DSL (declarative), Kernel (runtime), and Stubs (custom code). This page covers domain services, stubs, action purity, and component roles.

---

## Domain Service

Custom business logic declaration in DSL with implementation in Python/TypeScript stubs. Part of the Anti-Turing extensibility model.

### Syntax

```dsl
service <name> "<Title>":
  kind: <domain_logic|validation|integration|workflow>
  input:
    <field_name>: <type> [required]
    ...
  output:
    <field_name>: <type>
    ...
  guarantees:
    - "<contract guarantee>"
  stub: <python|typescript>
```

### Example

```dsl
service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
  stub: python
```

**Related:** [Stub](services.md#stub), [Three Layer Architecture](services.md#three-layer-architecture)

---

## Stub

Turing-complete implementation of a domain service. Stubs are auto-generated from DSL with typed function signatures.

### Example

```dsl
# stubs/calculate_vat.py (auto-generated header)
# === AUTO-GENERATED HEADER - DO NOT MODIFY ===
# Service ID: calculate_vat
# Kind: domain_logic
# Input: invoice_id (uuid required), country_code (str(2) optional)
# Output: vat_amount (decimal), breakdown (json)
# ============================================

from typing import TypedDict

class CalculateVatResult(TypedDict):
    vat_amount: float
    breakdown: dict

def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    # Your implementation here
    invoice = get_invoice(invoice_id)
    vat_rate = get_vat_rate(country_code or invoice.country)
    return {
        "vat_amount": invoice.total * vat_rate,
        "breakdown": {"rate": vat_rate, "country": country_code}
    }
```

**Related:** [Domain Service](services.md#domain-service), [Three Layer Architecture](services.md#three-layer-architecture)

---

## Action Purity

Classification of actions as pure (no side effects) or impure (has side effects like fetch, navigate, etc.).

### Syntax

```dsl
actions:
  toggleFilter: pure    # Only affects local state
  saveTask: impure      # Has side effect (API call)
```

**Related:** [Component Role](services.md#component-role)

---

## Component Role

Classification of components as presentational (no state/impure actions) or container (has state or impure actions).

**Related:** [Action Purity](services.md#action-purity)

---

## Three Layer Architecture

DAZZLE's separation of concerns: DSL (declarative) → Kernel (runtime) → Stubs (custom code). The DSL is Anti-Turing (no arbitrary computation) while stubs allow full programming.

**Related:** [Domain Service](services.md#domain-service), [Stub](services.md#stub)

---
