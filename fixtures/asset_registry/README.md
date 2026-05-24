# asset_registry

Framework-validation fixture for the **subtype_of:** keyword (#1217 Phase 3e,
Pattern 8 of the 3NF audit).

> **This fixture exercises an escape hatch.** Do NOT copy this as a
> recommended modelling pattern. See ADR-0026 and the inference KB entry
> `subtype_of_only_for_true_isa` (lands in slice 3e.vi) for guidance on
> alternatives.

## Shape

```
        Asset  ← base entity (shared fields + auto kind discriminator)
         ▲ ▲ ▲
         │ │ └── Equipment (serial_number, manufacturer)
         │ └─── Building   (floors, square_metres, occupancy_type)
         └───── Vehicle    (wheels, vin, fuel_type)
```

The `asset_registry` workspace lists all assets polymorphically (kind
badge column). The `fleet` workspace lists only Vehicles (subtype-specific
auto-JOIN; slice 3e.iv).

## When `subtype_of:` is justified

ALL three must hold:

1. True IS-A relationship (Vehicle IS an Asset).
2. Subtype-specific fields need NOT NULL at the schema level.
3. Polymorphic queries needed ("show me all assets, mixed kinds").

If any of these doesn't hold, model differently. Use separate entities,
a state machine + variant fields, or nullable subtype-specific fields on
a single entity.
