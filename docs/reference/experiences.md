# Experiences

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Experiences define multi-step user flows such as onboarding wizards, checkout processes, and approval workflows. Each step references a surface, process, or entity, with transitions driven by user events like continue, back, success, and failure.

---

## Experience

A multi-step user flow or wizard that guides users through a sequence of steps.
Experiences define step-by-step interactions with navigation, branching, and
error recovery. Each step references a surface, process, or integration, and
transitions between steps are driven by user events (continue, back, success,
failure, etc.). Use experiences for onboarding wizards, checkout flows, approval
workflows, and any multi-screen interaction that needs explicit flow control.

Steps can reference entities directly with `entity: EntityName` to auto-generate
creation forms — no separate surface definition needed. Use `creates: varname` to
capture the created entity in flow state, and `defaults: field: $varname` to
forward IDs between steps (e.g. setting a foreign key from a previously created
entity). The `context:` block declares typed variables, and `when:` guards
conditionally skip steps based on state.

### Syntax

```dsl
experience <name> "<Display Name>":
  # Optional: declare typed context variables
  context:
    <varname>: <EntityName>

  # Optional: access control, priority
  access: <public|authenticated|persona(name1, name2)>
  priority: <critical|high|medium|low>

  start at step <step_name>

  # Entity shorthand — auto-generates a create form from entity fields
  step <step_name>:
    entity: <EntityName>
    creates: <varname>             # saves_to: context.varname
    defaults:                      # prefill fields
      <field>: $<varname>          # → context.varname.id
      <field>: "<literal>"         # → quoted literal
    on <event> -> step <target>

  # Explicit surface reference (original syntax)
  step <step_name>:
    kind: <surface|process|integration>
    surface <surface_name>         # when kind is surface
    saves_to: context.<varname>    # capture created entity
    prefill:                       # pre-populate form fields
      <field>: context.<var>.<prop>
      <field>: "<literal>"
    when: context.<var>.<prop> = <value>   # conditional guard
    on <event> -> step <target>
```

### Example

```dsl
# Entity creation with ID forwarding (recommended for multi-entity flows)
experience client_onboarding "Client Onboarding":
  start at step add_company

  step add_company:
    entity: Company
    creates: company
    on success -> step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    defaults:
      company_id: $company
    on success -> step add_address
    on back -> step add_company

  step add_address:
    entity: Address
    creates: address
    defaults:
      contact_id: $contact
    on success -> step done
    on back -> step add_contact

  step done:
    entity: Company

# Surface-based flow (original syntax — still fully supported)
experience user_onboarding "User Onboarding":
  context:
    company: Company

  start at step welcome

  step welcome:
    kind: surface
    surface onboarding_welcome
    on continue -> step profile

  step profile:
    kind: surface
    surface onboarding_profile
    saves_to: context.company
    on continue -> step vat_check
    on back -> step welcome

  step vat_check:
    kind: surface
    surface vat_form
    when: context.company.is_vat_registered = true
    prefill:
      company: context.company.id
    on success -> step complete
    on back -> step profile

  step complete:
    kind: surface
    surface onboarding_complete
```

**Related:** [Surface](surfaces.md#surface), [Process](processes.md#process), [Integration](integrations.md#integration), [State Machine](entities.md#state-machine), [Entity](entities.md#entity)

---

## Stage

Layout stage that defines how a workspace's UI components are arranged.
Stages are like theater stages - they provide a layout where your UI components perform.
Select a stage to control the visual presentation of your workspace.

### Syntax

```dsl
workspace <name> "<Title>":
  purpose: "<intent>"
  stage: "<stage_name>"  # Optional: auto-selected if omitted

# Available stages:
# - focus_metric: Spotlight - one hero KPI with supporting context
# - scanner_table: Open stage - data-heavy table with filters
# - dual_pane_flow: Split stage - list on one side, detail on the other
# - monitor_wall: Gallery - multiple displays arranged in grid
# - command_center: Control room - dense expert interface
```

### Example

```dsl
# Explicit stage selection
workspace ops_center "Operations Center":
  purpose: "Real-time monitoring and incident response"
  stage: "command_center"

  alerts:
    source: Alert
    filter: is_active = true
    sort: severity desc

  services:
    source: Service
    aggregate:
      healthy: count(Service where status = healthy)

# Auto-selected stage (DUAL_PANE_FLOW)
workspace contacts "Contact Manager":
  purpose: "Browse and view contact details"

  contact_list:
    source: Contact
    display: list
    limit: 20

  contact_detail:
    source: Contact
    display: detail
```

### Best Practices

- Let auto-selection work for most cases
- Use explicit stage: for ops dashboards (command_center) or specific layouts
- Match stage to user needs: novices prefer simpler stages, experts prefer command_center
- Consider persona when choosing stage - same workspace can use different stages per persona

**Related:** [Workspace](workspaces.md#workspace), [Persona](ux.md#persona), [Attention Signals](ux.md#attention-signals)

---
