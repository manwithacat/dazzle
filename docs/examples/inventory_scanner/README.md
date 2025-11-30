# Inventory Scanner

> SCANNER_TABLE workspace archetype - data-heavy browsing and filtering.

## Quick Start

```bash
cd examples/inventory_scanner
dazzle dnr serve
# UI: http://localhost:3000
# API: http://localhost:8000/docs
```

## Overview

| Attribute | Value |
|-----------|-------|
| **Complexity** | Intermediate |
| **CI Priority** | P1 |
| **Archetype** | SCANNER_TABLE |
| **Entities** | Product |
| **Workspaces** | inventory |

## DSL Specification

**Source**: [`examples/inventory_scanner/dsl/app.dsl`](../../../examples/inventory_scanner/dsl/app.dsl)

### Entity: Product

```dsl
entity Product "Product":
  id: uuid pk
  sku: str(50) unique required
  name: str(200) required
  category: enum[electronics,clothing,home,food,other]=other
  quantity: int required
  price: decimal(10,2) required
  reorder_level: int=10
  supplier: str(200)
  last_restocked: datetime auto_update
  created_at: datetime auto_add
```

### Workspace: Inventory Browser

```dsl
workspace inventory "Inventory Browser":
  purpose: "Browse and filter all products"

  # Main table - no limits, supports browsing all data
  all_products:
    source: Product
```

## Archetype Analysis

This example demonstrates the **SCANNER_TABLE** archetype:

- Single TABLE signal with no limit
- Full data browsing capability
- Table-focused layout optimized for filtering and scanning

**Use Cases**:
- Admin panels
- Catalog browsing
- Inventory management
- Data administration

## E2E Test Coverage

| Metric | Coverage |
|--------|----------|
| Routes | 4 |
| CRUD Operations | Full |
| Components | 4 |

## Screenshots

*Screenshots are generated automatically during CI.*

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/products` | List all products |
| POST | `/api/products` | Create a product |
| GET | `/api/products/{id}` | Get product by ID |
| PUT | `/api/products/{id}` | Update product |
| DELETE | `/api/products/{id}` | Delete product |

## Related Examples

- [Ops Dashboard](../ops_dashboard/) - COMMAND_CENTER archetype
- [Contact Manager](../contact_manager/) - DUAL_PANE_FLOW archetype
