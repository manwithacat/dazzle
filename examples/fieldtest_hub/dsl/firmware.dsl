module fieldtest_hub.firmware

# Entity: FirmwareRelease
entity FirmwareRelease "Firmware Release":
  intent: "A versioned firmware build that can be rolled out to a Device batch and transitions from draft to released to deprecated"
  domain: hardware
  patterns: lifecycle, versioning, audit_trail
  id: uuid pk
  version: str(50) required unique
  release_notes: text
  release_date: datetime required
  status: enum[draft,released,deprecated]=draft
  applies_to_batch: str(100)
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # State machine: firmware lifecycle
  transitions:
    draft -> released: requires release_notes
    released -> deprecated
    deprecated -> draft: role(engineer)

  # Invariant: released firmware must have release notes
  invariant: status != released or release_notes != null

  permit:
    list: role(engineer) or role(manager) or role(tester)
    read: role(engineer) or role(manager) or role(tester)
    create: role(engineer)
    update: role(engineer)
    delete: role(engineer)
  scope:
    list: all
      as: engineer, manager, tester
    read: all
      as: engineer, manager, tester
    # v0.71.19 (#1123): firmware management is engineer-only.
    create: all
      as: engineer
    update: all
      as: engineer
    delete: all
      as: engineer

  index status
  index version

  fitness:
    repr_fields: [version, status, release_date, applies_to_batch]

# Surface: Firmware Release Timeline
surface firmware_release_list "Firmware Releases":
  uses entity FirmwareRelease
  mode: list
  render: fragment
  open: FirmwareRelease via id

  section main "Firmware Releases":
    field version "Version"
    field status "Status"
    field release_date "Release Date"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Track firmware versions — open a row for the release hub"
    sort: release_date desc
    filter: status, applies_to_batch
    search: version, release_notes
    empty: "No firmware releases yet."

    attention warning:
      when: status = deprecated
      message: "Deprecated firmware - upgrade recommended"
      action: firmware_release_detail

    as engineer:
      scope: all
      action_primary: firmware_release_create

# Surface: Firmware Release Detail
surface firmware_release_detail "Firmware Detail":
  uses entity FirmwareRelease
  mode: view
  render: fragment

  section main "Firmware Information":
    field version "Version"
    field release_notes "Release Notes"
    field release_date "Release Date"
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "View firmware release details"

    as engineer:
      scope: all
      action_primary: firmware_release_edit

# Surface: Firmware Release Create
surface firmware_release_create "Create Firmware Release":
  uses entity FirmwareRelease
  mode: create
  render: fragment

  section identity "Release":
    field version "Version"
    field release_date "Release Date"

  section notes "Release Notes":
    field release_notes "Release Notes"

  section rollout "Rollout":
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Create a new firmware release"

    as engineer:
      defaults:
        status: draft

# Surface: Firmware Release Edit
surface firmware_release_edit "Edit Firmware Release":
  uses entity FirmwareRelease
  mode: edit
  render: fragment

  section identity "Release":
    field version "Version"
    field release_date "Release Date"

  section notes "Release Notes":
    field release_notes "Release Notes"

  section rollout "Rollout":
    field status "Status"
    field applies_to_batch "Applies to Batch"

  ux:
    purpose: "Update firmware release"

    as engineer:
      scope: all
workspace draft_releases "Draft Releases":
  # Goal B empty_region_honesty (cycle 1855): one draft queue + pulse — not twin
  # draft queues, draft trail, and status bar theater.
  purpose: "Draft firmware pressure — unshipped builds without warehouse CRUD"
  access: persona(engineer, manager)

  draft_metrics:
    source: FirmwareRelease
    display: metrics
    aggregate:
      drafts: count(FirmwareRelease where status = draft)
      released: count(FirmwareRelease where status = released)
      deprecated: count(FirmwareRelease where status = deprecated)
    tones:
      drafts: warning
      released: positive
      deprecated: accent

  draft_queue:
    source: FirmwareRelease
    filter: status = draft
    sort: release_date desc
    limit: 20
    display: queue
    action: firmware_release_edit
    empty: "No draft firmware releases"
