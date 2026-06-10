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
      as: oracle

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
      as: oracle, sovereign, architect

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

  # Tenant personas see realm/colour-scoped shapes; sovereign also creates
  # and edits within their realm (#1355 — these permits were missing, making
  # every non-oracle scope rule below unreachable behind default-deny).
  permit:
    create: role(sovereign)
    list: role(sovereign) or role(architect) or role(chromat) or role(forgemaster) or role(witness)
    read: role(sovereign) or role(architect) or role(chromat) or role(forgemaster) or role(witness)
    update: role(sovereign)
    delete: role(sovereign)

  # Row-level filters: oracle sees all; non-oracle roles are realm/colour
  # scoped AND never see shadow material (the intent the old blanket forbid
  # claimed but could not express — forbid carries role conditions only).
  scope:
    list: all
      as: oracle
    read: all
      as: oracle
    create: all
      as: oracle, sovereign
    update: all
      as: oracle
    delete: all
      as: oracle
    list: realm = current_user.realm and material != shadow
      as: sovereign, architect
    read: realm = current_user.realm and material != shadow
      as: sovereign, architect
    update: realm = current_user.realm and material != shadow
      as: sovereign
    delete: realm = current_user.realm and material != shadow
      as: sovereign
    list: colour = current_user.colour and material != shadow
      as: chromat
    read: colour = current_user.colour and material != shadow
      as: chromat
    list: (realm = current_user.realm or creator = current_user) and material != shadow
      as: forgemaster, witness
    read: (realm = current_user.realm or creator = current_user) and material != shadow
      as: forgemaster, witness

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
      as: oracle

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
      as: oracle
    list: via RealmGuardian(guardian = current_user, realm = realm, revoked_at = null)
      as: guardian

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
      as: *
    read: shape.realm = current_user.realm
      as: *
