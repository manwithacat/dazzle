# DAZZLE Inventory Scanner - SCANNER_TABLE Archetype Example
# Demonstrates data-heavy browsing and filtering with table-focused layout

module inventory_scanner.core

app inventory_scanner "Inventory Scanner"

# Product entity for inventory management
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

# Workspace with single large table - triggers SCANNER_TABLE archetype
# Single TABLE signal with no limits → high table_weight
workspace inventory "Inventory Browser":
  purpose: "Browse and filter all products"

  # Main table - no limits, supports browsing all data
  # This creates a TABLE signal with default weight (0.5)
  # Since it's the only/dominant signal, should trigger SCANNER_TABLE
  all_products:
    source: Product
