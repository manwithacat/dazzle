# Urban Canopy – Product Specification

**Project Type**: Public-facing + municipal staff tool  
**Target Users**: Volunteer tree stewards, municipal arborists, environmental NGOs  
**Deployment**: Multi-user, citizen portal + staff admin workflows

---

## Project Overview

I need an application that empowers neighbourhood volunteers to monitor the health of street trees while enabling municipal arborists to triage issues efficiently. The key problem is that most cities rely on slow, periodic surveys, causing early-warning signs (disease, drought, soil compaction) to be missed. Users should be able to contribute observations, view mapped trees, claim stewardship, and manage maintenance actions with minimal friction.

---

## Core Features

### What I Need to Track

#### **Tree**
- **Species** (required) – Botanical species name  
- **Location** (required) – Coordinates or street address  
- **Condition Status** – Healthy, Moderate Stress, Severe Stress, Dead  
- **Soil Condition** – Compact, Loose, Mulched, Unknown  
- **Last Inspection Date** – Auto timestamp  
- **Steward Assigned** – Optional Volunteer relationship  

#### **Observation**
- **Tree** (required) – Observed tree  
- **Observer** (required) – Volunteer or Arborist  
- **Moisture Level** – Low / Medium / High  
- **Leaf Condition** – Normal / Yellowing / Browning / Spotting  
- **Insect Signs** – Yes/No + optional notes  
- **Photo** – optional upload  
- **Submitted At** – Auto timestamp  

#### **Maintenance Task**
- **Type** – Watering, Mulching, Pruning Request, Soil Aeration, Disease Inspection  
- **Created By** – Volunteer or Arborist  
- **Assigned To** – optional Volunteer or Staff  
- **Status** – Open, In Progress, Completed, Cancelled  
- **Notes** – optional  
- **Created At**, **Updated At** – timestamps  

#### **Volunteer**
- **Name** (required)  
- **Preferred Area** – optional  
- **Skills** – Beginner, Intermediate, Trained Arborist  
- **Active** – Yes/No  
- **Joined At** – timestamp  

---

## User Stories

### As a volunteer, I want to:

1. **Claim a tree to steward**
   - Gives me responsibility and continuity  
   - Ensures effort isn't duplicated  

2. **Submit health observations**
   - Quick, mobile-friendly data entry  
   - Helps track gradual improvement or decline  

3. **Complete maintenance tasks**
   - Mark tasks as completed  
   - Keeps the broader effort coordinated  

### As a municipal arborist, I want to:

1. **View a map of trees needing attention**
   - Filter by severity indicators and overdue inspections  
   - Prioritise high-risk cases  

2. **Convert observations into tasks**
   - Trigger pruning requests or disease inspections  
   - Builds traceable workflow history  

---

## User Interface

### Pages I Need

1. **Tree Map Page**
   - Shows: All trees as map markers, colour-coded by condition  
   - Actions: Filter by species, condition, steward status  
   - Features: Click to open Tree Detail  

2. **Tree Detail Page**
   - Purpose: View full health record  
   - Fields: Species, last observations, steward, soil condition  
   - Actions: Add observation, create tasks  
   - Next: Return to map  

3. **Observation Form**
   - Purpose: Quick citizen input  
   - Fields: Leaf condition, moisture, insect signs, optional photo  
   - Next step: Redirect to Tree Detail  

4. **Task Board**
   - Shows: Kanban (Open → In Progress → Completed)  
   - Actions: Assign tasks, update status  

---

## What the System Provides Automatically

(Leave unchanged from existing DAZZLE template.)

---

## Example Scenarios

### Scenario 1: A First-Time Volunteer

1. Opens the app and browses the map  
2. Claims a tree near their home  
3. Logs an observation with moisture level and a photo  
4. System flags Moderate Stress  
5. A suggested task (“Watering”) is created  
6. Volunteer completes the task later in the week  

### Scenario 2: Arborist Responding to a Cluster

1. Filters trees by “Yellowing Leaves”  
2. Identifies a geographical cluster  
3. Creates bulk disease-inspection tasks  
4. Assigns them to trained volunteers  
5. Reviews outcomes through observation photos  

---

## Success Criteria

This app is successful if:

- Volunteers log one observation per stewarded tree per month  
- Arborists reduce triage time by 30%  
- Severe-stress cases decline due to earlier interventions  
- Citizens find the workflow simple and mobile-friendly  

---

## Technical Requirements

### Must Have
- Geolocation field  
- Photo uploads  
- Mobile-friendly forms  
- Map-based browsing  
- Robust relationships (Tree ↔ Observations, Tree ↔ Tasks, Volunteer ↔ Trees)  

### Nice to Have
- Notifications for overdue inspections  
- Seasonal species-specific care guidance  
- Batch creation of tasks  

### Out of Scope (For Version 1)
- Real-time IoT soil sensors  
- User messaging  
- Native mobile applications  

---

## Notes for Development

### Data Relationships

- A **Tree** can have many **Observations**  
- A **Tree** can have many **Tasks**  
- A **Volunteer** can be assigned many **Tasks**  
- A **Tree** may optionally have one **Steward (Volunteer)**  

### Status Definitions

**Condition Status**  
- **Healthy** – No action needed  
- **Moderate Stress** – Monitor frequently  
- **Severe Stress** – Requires urgent intervention  
- **Dead** – Mark for removal  

---

## Working with AI Assistants to Build This

(Keep from original template.)

---

## Next Steps

1. Begin translating entities into DAZZLE DSL  
2. Validate with `dazzle validate`  
3. Build prototype with `dazzle build`  
4. Iterate based on UI and workflow testing  