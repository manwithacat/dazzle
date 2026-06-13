module contact_manager.guides

use contact_manager.core

# First-run onboarding for contact_manager. Workspace: `contacts`.
# Walks an admin through:
#   1. Landing on the empty contact list -> empty_state invites them
#      to add their first contact
#   2. On the create form, popover prompts them to fill in a name
#   3. Banner after the first save congratulating + nudging them
#      toward exploring detail views
#
# Targets, completion events, and CTA surfaces are validated against
# the DSL by the concordance linker pass; renaming any of these
# without updating the guide fails `dazzle validate`.

guide contacts_onboarding "Getting started with Contacts":
  audience: persona = admin or persona = user

  step welcome_empty:
    kind: empty_state
    target: surface.contact_list
    title: "Add your first contact"
    body: "Contacts are people you correspond with — colleagues, vendors, clients. Start with someone you talk to often."
    cta_label: "New Contact"
    cta_target: surface.contact_create
    complete_on: event entity.Contact.created

  step fill_first_name:
    kind: popover
    target: surface.contact_create
    title: "Start with a first name"
    body: "First name + email are the only required fields. You can fill in phone, company, and notes later."
    placement: bottom
    complete_on: field_filled surface.contact_create.field.first_name

  step explore_detail:
    kind: banner
    target: surface.contact_list
    title: "Your first contact is in"
    body: "Click any row to open the detail view — that's where edits and notes live."
    complete_on: dismiss

  step_order: [welcome_empty, fill_first_name, explore_detail]

  on_complete:
    redirect: surface.contact_list
