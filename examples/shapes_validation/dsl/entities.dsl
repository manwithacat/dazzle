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

entity Shape "Shape":
  id: uuid pk
  name: str(200) required
  form: enum[circle,triangle,square,hexagon,star] required
  colour: enum[red,blue,green,gold,void] required
  material: enum[glass,stone,metal,shadow] required
  realm: ref Realm required
  creator: ref User required
  created_at: datetime auto_add

  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle)
    update: role(oracle)
    delete: role(oracle)

  permit:
    list: realm = current_user.realm
    read: realm = current_user.realm
    create: role(sovereign)
    update: realm = current_user.realm
    delete: realm = current_user.realm

  permit:
    list: realm = current_user.realm
    read: realm = current_user.realm

  permit:
    list: colour = current_user.colour
    read: colour = current_user.colour

  permit:
    list: material = metal or material = stone
    read: material = metal or material = stone

  forbid:
    list: material = shadow
    read: material = shadow

  permit:
    list: realm = current_user.realm or creator = current_user
    read: realm = current_user.realm or creator = current_user

entity Inscription "Inscription":
  id: uuid pk
  text: str(500) required
  shape: ref Shape required
  author: ref User required
  created_at: datetime auto_add

  permit:
    list: role(oracle)
    read: role(oracle)

  permit:
    list: shape.realm = current_user.realm
    read: shape.realm = current_user.realm
