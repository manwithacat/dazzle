# Extensibility Guide

> **Version**: 0.5.0 | **Status**: Production Ready

This guide covers the three-layer extensibility model for adding custom behavior to DAZZLE applications.

## Overview

DAZZLE uses a **Three-Layer Architecture** that separates concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DSL Layer (Declarative)                      │
│        Entities, Surfaces, Services, Experiences, Flows         │
│                   Anti-Turing: No custom code                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kernel Layer (DNR Runtime)                   │
│         Entity CRUD, Auth, Routing, State Management            │
│                   Platform-managed behavior                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Stub Layer (Turing-Complete)                 │
│        Custom business logic, validations, integrations         │
│                   Developer-implemented code                    │
└─────────────────────────────────────────────────────────────────┘
```

## Anti-Turing DSL

The DSL layer is deliberately **Anti-Turing** - it cannot express arbitrary computation. This ensures:

- **Predictability**: The behavior is fully analyzable from the DSL
- **Safety**: No runtime errors from DSL-level code
- **Tooling**: Complete static analysis and validation

### What the DSL Can Express

```dsl
# Entity definitions
entity Invoice "Invoice":
  id: uuid pk
  total: decimal(10,2) required
  status: enum[draft,sent,paid]=draft

# Surface definitions
surface invoice_list "Invoices":
  uses entity Invoice
  mode: list

# Data relationships and constraints
entity InvoiceItem "Line Item":
  invoice: ref Invoice required
```

### What Requires Stubs

- Custom validation logic
- External API integration
- Business rule calculations
- Multi-step workflows
- Data transformation

## Domain Services (v0.5.0)

Domain services declare business logic contracts in the DSL, with implementation in stubs.

### DSL Declaration

```dsl
service calculate_vat "Calculate VAT for Invoice":
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

### Service Kinds

| Kind | Purpose | Example |
|------|---------|---------|
| `domain_logic` | Business calculations | VAT calculation, pricing |
| `validation` | Complex validation rules | Cross-field validation |
| `integration` | External system calls | Payment gateway, email |
| `workflow` | Multi-step processes | Order fulfillment |

### Generating Stubs

```bash
# Generate stub files for all services
dazzle stubs generate

# Generate stubs for specific service
dazzle stubs generate --service calculate_vat

# List available services
dazzle stubs list
```

This generates a stub file with the service contract:

```python
# stubs/calculate_vat.py
# === AUTO-GENERATED HEADER - DO NOT MODIFY ===
# Service ID: calculate_vat
# Title: Calculate VAT for Invoice
# Kind: domain_logic
#
# Input:
#   invoice_id: uuid (required)
#   country_code: str(2) (optional)
#
# Output:
#   vat_amount: decimal(10,2)
#   breakdown: json
#
# Guarantees:
#   - Must not mutate the invoice record
#   - Must raise domain error if config incomplete
# ============================================

from typing import TypedDict


class CalculateVatResult(TypedDict):
    vat_amount: float
    breakdown: dict


def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    # === IMPLEMENTATION SECTION ===
    # Implement your business logic here.
    # The header above documents the service contract.
    raise NotImplementedError("Implement this service")
```

### Implementing Stubs

Replace the placeholder with your implementation:

```python
def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    # Fetch invoice from database
    invoice = get_invoice(invoice_id)

    # Determine VAT rate based on country
    vat_rate = get_vat_rate(country_code or invoice.country)

    # Calculate VAT
    vat_amount = invoice.total * vat_rate

    return {
        "vat_amount": vat_amount,
        "breakdown": {
            "rate": vat_rate,
            "country": country_code or invoice.country
        }
    }
```

### Stub Discovery

The DNR runtime automatically discovers and loads stubs from:

1. `stubs/` directory in project root
2. Paths specified in `pyproject.toml`

```toml
[tool.dazzle]
stub_paths = ["custom_stubs", "shared/stubs"]
```

## Extending the DSL

### Adding New Constructs

To add new DSL constructs:

1. **Update EBNF Grammar** (`docs/v0.2/DAZZLE_DSL_GRAMMAR.ebnf`)
2. **Add IR Types** (`src/dazzle/core/ir/`)
3. **Implement Parser** (`src/dazzle/core/dsl_parser.py`)
4. **Add Tests** (`tests/unit/test_parser.py`)

Example - adding a new `webhook` construct:

```ebnf
(* In EBNF grammar *)
webhook_decl ::= "webhook" IDENTIFIER STRING? ":" webhook_body ;
webhook_body ::= INDENT webhook_directive+ DEDENT ;
```

```python
# In IR types
class WebhookSpec(BaseModel):
    name: str
    url: str
    events: list[str]
```

### Custom Code Generation

For deployment targets not supported by DNR:

```python
from dazzle.stacks.base import BaseBackend

class FlaskBackend(BaseBackend):
    """Generate Flask application from DAZZLE spec."""

    def generate(self, appspec, output_dir, artifacts=None):
        for entity in appspec.domain.entities:
            self._generate_model(entity, output_dir)

        for service in appspec.domain_services:
            self._generate_service_route(service, output_dir)
```

Register in `pyproject.toml`:

```toml
[project.entry-points."dazzle.stacks"]
flask = "mypackage.flask_stack:FlaskBackend"
```

## Best Practices

### DSL Design

1. **Keep DSL minimal** - Only declare what's needed
2. **Use services for logic** - Don't try to encode logic in entity defaults
3. **Document guarantees** - Make service contracts explicit

### Stub Implementation

1. **Honor guarantees** - The guarantees are part of the contract
2. **Keep stubs focused** - One service, one responsibility
3. **Test independently** - Stubs should be unit-testable

### Extension Points

| Extension Point | Method | Use Case |
|-----------------|--------|----------|
| Domain services | DSL + Stubs | Custom business logic |
| Custom stacks | Python backend | New deployment targets |
| MCP tools | TypeScript/Python | IDE integration |
| CLI commands | Click plugins | Custom workflows |

## Resources

- [Domain Service IR](v0.1/DAZZLE_IR.md)
- [Stub Generator Source](../src/dazzle/stubs/generator.py)
- [Custom Stacks Guide](CUSTOM_STACKS.md)
- [DNR Architecture](dnr/ARCHITECTURE.md)
