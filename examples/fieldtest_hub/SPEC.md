
# FieldTest Hub – Product Specification

**Project Type**: Distributed beta testing + product quality platform
**Target Users**: Hardware founders, product managers, QA engineers, beta testers
**Deployment**: Multi-tenant app for startups and hardware teams

---

## Project Overview

I need an application that allows early-stage hardware companies to coordinate real-world field testing of physical devices (e.g., wearables, IoT sensors, robotics components). Currently, feedback is scattered across Slack, email, spreadsheets, and ad-hoc forms. As a result, the team often misses critical trends such as battery failures, overheating, or firmware bugs that only appear outside the lab. The system should track devices, assign testers, collect field reports, escalate issues, and link findings to specific batches and firmware versions.

The key outcome is faster product iteration and early detection of systemic failures before mass production.

---

## Core Entities

### **Device**
- **Name** (required)
- **Model** (required)
- **Batch Number** (required)
- **Serial Number** (required, unique)
- **Firmware Version** – e.g., 1.0.3
- **Status** – Active, Recalled, Prototype, Retired
- **Assigned Tester** – optional link
- **Deployed At** – timestamp

### **Tester**
- **Name** (required)
- **Location** (required – city or region)
- **Device Assigned** – optional
- **Skill Level** – Casual, Enthusiast, Engineer
- **Joined At** – timestamp
- **Active** – Yes/No

### **Issue Report**
- **Device** (required)
- **Reported By** (required – Tester or Engineer)
- **Category** – Battery, Connectivity, Mechanical, Overheating, Crash, Other
- **Severity** – Low, Medium, High, Critical
- **Description** – free text
- **Steps to Reproduce** – optional
- **Photo/Video** – optional upload
- **Reported At** – timestamp
- **Status** – Open, Triaged, In Progress, Fixed, Verified, Closed
- **Linked Firmware Version** – optional

### **Test Session**
- **Device** (required)
- **Tester** (required)
- **Duration** – in minutes/hours
- **Environment** – Indoor, Outdoor, Vehicle, Industrial, Other
- **Temperature** – optional numeric
- **Notes** – optional
- **Logged At** – timestamp

### **Firmware Release**
- **Version** (required)
- **Release Notes** – text
- **Release Date** – timestamp
- **Status** – Draft, Released, Deprecated
- **Applies To Batch** – optional link

### **Task**
- **Type** – Debugging, Hardware Replacement, Firmware Update, Recall Request
- **Created By** – Engineer or Manager
- **Assigned To** – optional Tester or Engineer
- **Status** – Open, In Progress, Completed, Cancelled
- **Notes** – optional
- **Created At**, **Updated At** – timestamps

---

## User Stories

### As a tester, I want to:

1. **Log an issue quickly**
   - Capture photo/video evidence
   - Auto-link to the device and firmware

2. **Track the status of my reports**
   - Know if the team has acknowledged or fixed the issue

3. **Record usage sessions**
   - Helps explain context behind failures

### As an engineer or product manager, I want to:

1. **See clusters of similar issues**
   - Detect systemic battery or connectivity failures early

2. **Filter by firmware version or batch**
   - Identify whether a problem affects a specific release

3. **Escalate issues into tasks**
   - Assign work to engineering or testers for verification

4. **Run recalls**
   - Mark devices as Recalled and notify testers

---

## User Interface

### Pages I Need

1. **Device Dashboard**
   - Shows: All devices with status indicators
   - Filters: Batch, firmware, status, assigned tester
   - Actions: Assign tester, change status, open device detail

2. **Device Detail Page**
   - Shows: Full device history and reports
   - Actions: Log issue, start test session, view tasks
   - Fields: Batch, firmware, deployment date, tester

3. **Issue Reporting Form**
   - Purpose: Fast capture of problems
   - Fields: Severity, category, description, media upload
   - Next: Redirect to Issue Detail

4. **Issue Board**
   - Kanban workflow (Open → Triaged → In Progress → Fixed → Verified → Closed)
   - Filters for severity, category, firmware

5. **Firmware Release Page**
   - Version timeline
   - Actions: Create release, update status

6. **Tester Directory**
   - List all testers with activity levels
   - Actions: Assign or unassign devices

---

## What the System Provides Automatically

(Leave unchanged from existing DAZZLE template.)

---

## Example Scenarios

### Scenario 1: Early Battery Failure

1. Three testers report overheating on batch B-2025, firmware 1.0.2
2. System flags a cluster
3. Issue escalated to High severity
4. Engineering creates a Firmware Update task
5. Once deployed, testers verify fix via new Test Sessions

### Scenario 2: Mechanical Recall

1. Devices from batch B-2024 show a latch failure
2. Devices marked Recalled
3. Notifications sent to assigned testers
4. Replacement hardware tasks created
5. Status updated after tester confirmation

---

## Success Criteria

This app is successful if:

- Critical failures are detected before mass production
- Engineering response time improves by 40%
- Field testing generates structured, searchable data
- Firmware regressions are caught within 48 hours

---

## Technical Requirements

### Must Have
- Device ↔ Issue linkage
- File uploads for photos/videos
- Status-based workflows
- Batch and firmware filtering
- Role-based access (Tester, Engineer, Manager)

### Nice to Have
- Geo heatmaps of issues
- Automated severity suggestions
- Firmware push notifications
- QR code device registration

### Out of Scope (For Version 1)
- Full device telematics streaming
- Hardware simulation
- Automated OTA update delivery

---

## Data Relationships

- A **Device** can have many **Issue Reports**
- A **Device** can have many **Test Sessions**
- A **Tester** can be assigned one **Device** at a time
- A **Batch** groups multiple **Devices**
- A **Firmware Release** can affect multiple **Devices**

---

## Next Steps

1. Translate entities into DAZZLE DSL
2. Validate with `dazzle validate`
3. Build prototype with `dazzle build`
4. Test with a small hardware founder cohort
