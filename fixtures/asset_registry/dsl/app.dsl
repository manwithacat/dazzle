module asset_registry
app asset_registry "Asset Registry"

# ── Personas ────────────────────────────────────────────────────────
# Three personas exercise scope composition across base + subtype:
#   registry_viewer  — read-only access to all assets (polymorphic list)
#   fleet_admin      — manages Vehicle subtypes; scope restricts to electric vehicles
#   facilities_admin — manages Building subtypes

persona registry_viewer "Registry Viewer":
  description: "Read-only view of the asset registry."
  default_workspace: asset_registry

persona fleet_admin "Fleet Admin":
  description: "Manage Vehicle subtypes (restricted to electric vehicles)."
  default_workspace: fleet

persona facilities_admin "Facilities Admin":
  description: "Manage Building subtypes."
  default_workspace: asset_registry

# ── Entities ────────────────────────────────────────────────────────
# Asset is the polymorphic base. Vehicle / Building / Equipment are
# its subtypes — each declares `subtype_of: Asset` and inherits the
# shared id (via FK with ON DELETE CASCADE) plus the synthesised
# `kind` enum discriminator the linker adds.

entity Asset "Asset":
  id: uuid pk
  acquired_at: date required
  acquired_value: decimal(12,2) required
  location: str(120)

  permit:
    list: role(registry_viewer) or role(fleet_admin) or role(facilities_admin)
    read: role(registry_viewer) or role(fleet_admin) or role(facilities_admin)
    create: role(fleet_admin) or role(facilities_admin)
    update: role(fleet_admin) or role(facilities_admin)
    delete: role(fleet_admin) or role(facilities_admin)

  scope:
    list: all
      as: registry_viewer, fleet_admin, facilities_admin
    read: all
      as: registry_viewer, fleet_admin, facilities_admin
    create: all
      as: fleet_admin, facilities_admin
    update: all
      as: fleet_admin, facilities_admin
    delete: all
      as: fleet_admin, facilities_admin

entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
  vin: str(17) required unique
  fuel_type: enum[petrol,diesel,electric,hybrid] required

  permit:
    list: role(registry_viewer) or role(fleet_admin)
    read: role(registry_viewer) or role(fleet_admin)
    create: role(fleet_admin)
    update: role(fleet_admin)
    delete: role(fleet_admin)

  # Restrict fleet_admin to electric vehicles only — exercises scope
  # composition on a subtype (intersected with Asset's base scope at
  # query time when the polymorphic JOIN runs).
  scope:
    list: fuel_type = electric
      as: fleet_admin
    read: fuel_type = electric
      as: fleet_admin
    list: all
      as: registry_viewer
    read: all
      as: registry_viewer
    create: all
      as: fleet_admin
    update: all
      as: fleet_admin
    delete: all
      as: fleet_admin

entity Building "Building":
  subtype_of: Asset
  floors: int required
  square_metres: int required
  occupancy_type: enum[office,warehouse,residential] required

  permit:
    list: role(registry_viewer) or role(facilities_admin)
    read: role(registry_viewer) or role(facilities_admin)
    create: role(facilities_admin)
    update: role(facilities_admin)
    delete: role(facilities_admin)

  scope:
    list: all
      as: registry_viewer, facilities_admin
    read: all
      as: registry_viewer, facilities_admin
    create: all
      as: facilities_admin
    update: all
      as: facilities_admin
    delete: all
      as: facilities_admin

entity Equipment "Equipment":
  subtype_of: Asset
  serial_number: str(64) required unique
  manufacturer: str(120) required

  permit:
    list: role(registry_viewer)
    read: role(registry_viewer)

  scope:
    list: all
      as: registry_viewer
    read: all
      as: registry_viewer

# ── Workspaces ──────────────────────────────────────────────────────
# asset_registry — polymorphic list of all assets (base entity). The
#                  synthesised `kind` field discriminates rows.
# fleet          — Vehicle-only list (subtype auto-JOIN pulls base
#                  columns into the row at query time; slice 3e.iv).

workspace asset_registry "Asset Registry":
  access: persona(registry_viewer, fleet_admin, facilities_admin)
  purpose: "Polymorphic asset list — exercises subtype_of: base read path"

  assets:
    source: Asset
    sort: acquired_at desc
    display: list
    empty: "No assets registered"

workspace fleet "Fleet":
  access: persona(fleet_admin, registry_viewer)
  purpose: "Vehicle-only list — exercises subtype_of: child JOIN path (slice 3e.iv)"

  vehicles:
    source: Vehicle
    sort: vin asc
    display: list
    empty: "No vehicles registered"

# ── Surfaces ────────────────────────────────────────────────────────
# Per-subtype detail surfaces hold the subtype-specific fields.
# asset_card is the polymorphic VIEW that dispatches by `kind` via
# subtype_panel: — slice 3e.v adds this construct.

surface vehicle_detail "Vehicle Detail":
  uses entity Vehicle
  mode: view
  section main:
    field wheels "Wheels"
    field vin "VIN"
    field fuel_type "Fuel"

surface building_detail "Building Detail":
  uses entity Building
  mode: view
  section main:
    field floors "Floors"
    field square_metres "Square Metres"
    field occupancy_type "Occupancy"

surface equipment_detail "Equipment Detail":
  uses entity Equipment
  mode: view
  section main:
    field serial_number "Serial Number"
    field manufacturer "Manufacturer"

surface asset_card "Asset":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    field acquired_value "Value"
    field location "Location"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail
      when kind = equipment: include surface equipment_detail
