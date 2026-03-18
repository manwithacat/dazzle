module shapes_validation
app shapes "Shapes RBAC Validation"

enum ShapeForm "Shape Form":
  circle
  triangle
  square
  hexagon
  star

enum Colour "Colour":
  red
  blue
  green
  gold
  void

enum Material "Material":
  glass
  stone
  metal
  shadow

persona oracle "Oracle":
  description: "Platform admin — sees everything across all realms"

persona sovereign "Sovereign":
  description: "Tenant admin — sees everything in own realm only"

persona architect "Architect":
  description: "Scoped viewer — sees shapes in own realm"

persona chromat "Chromat":
  description: "Attribute filter — sees shapes matching assigned colour"

persona forgemaster "Forgemaster":
  description: "Enum filter with forbid — sees metal/stone, forbidden shadow"

persona witness "Witness":
  description: "Mixed OR — sees own realm or own creations"

persona outsider "Outsider":
  description: "Deny-all baseline — proves complete mediation"
