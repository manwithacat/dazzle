module shapes_validation.entities

entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  role: enum[oracle,sovereign,architect,chromat,forgemaster,witness,outsider]=outsider
  realm: ref Realm optional
  colour: enum[red,blue,green,gold,void] optional
  is_active: bool=true
  created_at: datetime auto_add

  # Only Oracle can manage users
  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle)
    update: role(oracle)
    delete: role(oracle)

  scope:
    list: all
      for: oracle

entity Realm "Realm":
  id: uuid pk
  name: str(100) required unique
  sigil: str(50)

  permit:
    list: role(oracle)
    read: role(oracle)
    list: role(sovereign)
    read: role(sovereign)
    list: role(architect)
    read: role(architect)

  scope:
    list: all
      for: oracle, sovereign, architect

entity Shape "Shape":
  id: uuid pk
  name: str(200) required
  form: enum[circle,triangle,square,hexagon,star] required
  colour: enum[red,blue,green,gold,void] required
  material: enum[glass,stone,metal,shadow] required
  realm: ref Realm required
  creator: ref User required
  created_at: datetime auto_add

  # Oracle can do everything
  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle)
    update: role(oracle)
    delete: role(oracle)

  # Sovereign can create shapes, and see/edit shapes in their realm
  permit:
    create: role(sovereign)

  # Shadow material is forbidden for non-oracle roles
  forbid:
    list: role(sovereign) or role(architect) or role(chromat) or role(forgemaster) or role(witness) or role(outsider)
    read: role(sovereign) or role(architect) or role(chromat) or role(forgemaster) or role(witness) or role(outsider)

  # Row-level filters: oracle sees all, others are realm/colour-scoped
  scope:
    list: all
      for: oracle
    read: all
      for: oracle
    create: all
      for: oracle, sovereign
    update: all
      for: oracle
    delete: all
      for: oracle
    list: realm = current_user.realm
      for: sovereign, architect
    read: realm = current_user.realm
      for: sovereign, architect
    update: realm = current_user.realm
      for: sovereign
    delete: realm = current_user.realm
      for: sovereign
    list: colour = current_user.colour
      for: chromat
    read: colour = current_user.colour
      for: chromat
    list: realm = current_user.realm or creator = current_user
      for: forgemaster, witness
    read: realm = current_user.realm or creator = current_user
      for: forgemaster, witness

# --- Junction-Table Scope Example (#530) ---
# Demonstrates via clause for access control through junction tables.

entity RealmGuardian "Realm Guardian":
  id: uuid pk
  guardian: ref User required
  realm: str(100) required
  revoked_at: datetime

  permit:
    create: role(oracle)
    list: role(oracle)
    read: role(oracle)

  scope:
    list: all
      for: oracle

entity Artifact "Artifact":
  id: uuid pk
  name: str(200) required
  realm: str(100) required
  creator: ref User

  permit:
    list: role(oracle) or role(guardian)
    read: role(oracle) or role(guardian)

  scope:
    list: all
      for: oracle
    list: via RealmGuardian(guardian = current_user, realm = realm, revoked_at = null)
      for: guardian

entity Inscription "Inscription":
  id: uuid pk
  text: str(500) required
  shape: ref Shape required
  author: ref User required
  created_at: datetime auto_add

  permit:
    list: role(oracle)
    read: role(oracle)

  scope:
    list: shape.realm = current_user.realm
      for: *
    read: shape.realm = current_user.realm
      for: *
