module fieldtest_hub.guides

use fieldtest_hub.core

# Two onboarding guides — different journeys per persona:
#
#   1. engineer_onboarding: engineer registers a device, then a
#      firmware release for it.
#   2. tester_onboarding: tester logs into their dashboard, starts
#      a test session against an existing device, and learns how
#      to file issue reports against the session.
#
# Managers land on manager_ops (fleet KPIs); engineers on engineering_dashboard;
# testers on tester_dashboard (+ field_kit). Guides still root on surfaces
# (guide targets cannot be workspaces). Admins are out of scope. Linker-
# validated — renaming device_create / firmware_release_create /
# test_session_create / issue_report_create fails validate without guide update.

# ─── Engineer journey ─────────────────────────────────────────────

guide engineer_onboarding "Set up your engineering workspace":
  audience: persona = engineer

  step register_device:
    kind: empty_state
    target: surface.device_list
    title: "Register your first device"
    body: "Every test session and issue report attaches to a Device. Start by registering the hardware you'll be testing."
    cta_label: "Register Device"
    cta_target: surface.device_create
    complete_on: event entity.Device.created

  step name_device:
    kind: popover
    target: surface.device_create
    title: "Use the device's serial / batch ID"
    body: "Testers will look up devices by name — keep it consistent with the labels in the field-test bag."
    placement: bottom
    complete_on: field_filled surface.device_create.field.name

  step explore_firmware:
    kind: inline_card
    target: surface.firmware_release_list
    title: "Track firmware releases per device"
    body: "Every firmware build cut for testing should land here. Testers reference the release in their session reports."
    cta_label: "Cut Firmware Release"
    cta_target: surface.firmware_release_create
    complete_on: event entity.FirmwareRelease.created

  step closing_banner:
    kind: banner
    target: surface.device_list
    title: "You're set up"
    body: "Hand the device + a tester invite to the team and they'll start filing sessions + issues."
    complete_on: dismiss

  step_order: [register_device, name_device, explore_firmware, closing_banner]

  on_complete:
    redirect: surface.device_list

# ─── Tester journey ───────────────────────────────────────────────

guide tester_onboarding "Your first test session":
  audience: persona = tester

  step welcome_spotlight:
    kind: spotlight
    target: surface.test_session_list
    title: "This is your tester dashboard"
    body: "Every test session you run shows up here. Start a new session whenever you pick up a device."
    placement: center
    complete_on: dismiss

  step start_session:
    kind: empty_state
    target: surface.test_session_list
    title: "Start your first test session"
    body: "Pick the device you've been handed and open a new session. Sessions group the issues you'll file."
    cta_label: "New Session"
    cta_target: surface.test_session_create
    complete_on: event entity.TestSession.created

  step file_issue:
    kind: inline_card
    target: surface.issue_report_list
    title: "Filing an issue"
    body: "When something fails during a session, file an issue report. Attach the session ID + describe steps to reproduce."
    cta_label: "File Issue"
    cta_target: surface.issue_report_create
    complete_on: event entity.IssueReport.created

  step closing_nudge:
    kind: nudge
    target: surface.test_session_list
    title: "Wrap up by closing the session"
    body: "Closing the session signals to engineers that you're done — they'll triage the issues you filed."
    placement: "10000"
    complete_on: dismiss

  step_order: [welcome_spotlight, start_session, file_issue, closing_nudge]

  on_complete:
    redirect: surface.test_session_list

# ─── Manager journey ──────────────────────────────────────────────
# Managers don't register devices — they watch quality and keep fixes
# moving. Oversight + delegation, rooted on the issue and task lists.

guide manager_onboarding "Stay on top of product quality":
  audience: persona = manager

  step quality_watch:
    kind: spotlight
    target: surface.issue_report_list
    title: "Keep an eye on critical issues"
    body: "Manager Ops opens with fleet health and critical issues. Anything critical needs an owner before the build ships."
    placement: center
    complete_on: dismiss

  step delegate_fix:
    kind: empty_state
    target: surface.task_list
    title: "Turn issues into assigned work"
    body: "Create a task for each fix and assign it to an engineer, so nothing critical sits unowned."
    cta_label: "New Task"
    cta_target: surface.task_create
    complete_on: event entity.Task.created

  step track_progress:
    kind: banner
    target: surface.task_list
    title: "Track what the team picks up"
    body: "Come back here to see what's in progress and what's still waiting for an owner."
    complete_on: dismiss

  step_order: [quality_watch, delegate_fix, track_progress]

  on_complete:
    redirect: surface.issue_report_list
