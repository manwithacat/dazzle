# Contact Manager - Product Specification

> **Document Status**: Refined specification ready for DSL conversion
> **Complexity Level**: Beginner+
> **DSL Features Demonstrated**: dual_pane_flow stage, intent declaration, domain/pattern tags, indexes

---

## Vision Statement

A personal contact management app that lets users efficiently browse and manage their professional and personal contacts. The dual-pane interface enables quick scanning of contacts while viewing full details without navigation, making it ideal for networking and relationship management.

---

## User Personas

### Primary: Networking Professional
- **Role**: Sales rep, recruiter, consultant, or small business owner
- **Need**: Quick access to contact details during calls or meetings
- **Pain Point**: Switching between list and detail views loses context
- **Goal**: See contact overview and details simultaneously

---

## Domain Model

### Entity: Contact

A person in the user's professional or personal network.

| Field | Type | Required | Default | Business Rules |
|-------|------|----------|---------|----------------|
| `id` | UUID | Yes | Auto | Immutable primary key |
| `first_name` | String(100) | Yes | - | Person's first name |
| `last_name` | String(100) | Yes | - | Person's last name (sortable) |
| `email` | Email | Yes | - | Primary email, must be unique |
| `phone` | String(20) | No | - | Phone number with formatting |
| `company` | String(200) | No | - | Company or organization |
| `job_title` | String(150) | No | - | Role or job title |
| `notes` | Text | No | - | Free-form notes about the contact |
| `is_favorite` | Boolean | Yes | `false` | Starred/favorite marker |
| `created_at` | DateTime | Yes | Auto | Immutable creation timestamp |
| `updated_at` | DateTime | Yes | Auto | Last modification timestamp |

**Indexes**:
- `email` - Unique lookup by email address
- `last_name, first_name` - Efficient alphabetical sorting

**Validation Rules**:
- Email must be valid format and unique
- First name and last name are required
- Phone format is flexible (stored as string)

---

## User Interface Specification

### Primary Pattern: Dual-Pane Flow

The application uses a **master-detail** pattern:
- **Left pane**: Scrollable list of contacts for browsing
- **Right pane**: Full details of the currently selected contact
- **Mobile**: Stacked view with detail sliding over list

### Workspace: Contacts

**Purpose**: Browse contacts and view details without navigation

**Layout**: Split-pane interface (`stage: "dual_pane_flow"`)

#### Left Pane: Contact List
| Column | Source | Behavior |
|--------|--------|----------|
| Avatar | First letter of name | Circular colored avatar |
| Name | `first_name + last_name` | Primary identifier |
| Company | `company` | Secondary text |
| Favorite | `is_favorite` | Star indicator |

**Interactions**:
- Click contact to show details in right pane
- Sort by last name (default), can toggle to first name
- Search by name, email, company
- Limit 20 contacts visible at a time

#### Right Pane: Contact Detail
| Field | Display |
|-------|---------|
| Full Name | `first_name` + `last_name` as heading |
| Email | Linked, clickable |
| Phone | Linked for mobile tap-to-call |
| Company | Company name |
| Job Title | Role at company |
| Notes | Full text area |
| Favorite | Toggle button |
| Timestamps | Created/updated in footer |

**Actions**: Edit, Delete, Add to Favorites

---

## User Stories & Acceptance Criteria

### US-1: Browse Contact List
**As a** user
**I want to** see all my contacts in a scrollable list
**So that** I can quickly find who I'm looking for

**Acceptance Criteria**:
- [ ] Contacts displayed in alphabetical order by last name
- [ ] Each contact shows name and company
- [ ] Favorite contacts show star indicator
- [ ] List scrolls independently of detail pane
- [ ] Can search/filter contacts by name

**Test Flow**:
```
1. Navigate to contacts workspace
2. Verify contacts listed alphabetically
3. Scroll through list
4. Verify search filters results
```

---

### US-2: View Contact Details
**As a** user
**I want to** see full contact information when I select someone
**So that** I can get all their details quickly

**Acceptance Criteria**:
- [ ] Clicking contact shows full details in right pane
- [ ] All fields displayed with appropriate formatting
- [ ] Email is clickable (mailto link)
- [ ] Phone is clickable on mobile (tel link)
- [ ] Selection persists while browsing

**Test Flow**:
```
1. Navigate to contacts workspace
2. Click on a contact in the list
3. Verify details appear in right pane
4. Verify email and phone are interactive
```

---

### US-3: Create New Contact
**As a** user
**I want to** add a new contact to my list
**So that** I can track new connections

**Acceptance Criteria**:
- [ ] Create button visible in list header
- [ ] Form requires first name, last name, and email
- [ ] Email uniqueness validated
- [ ] After save, new contact appears in list

**Test Flow**:
```
1. Click "Add Contact" button
2. Enter: first_name="Alice", last_name="Smith", email="alice@test.com"
3. Click Save
4. Verify contact appears in list alphabetically
```

---

### US-4: Edit Contact
**As a** user
**I want to** update contact information
**So that** I can keep my contacts current

**Acceptance Criteria**:
- [ ] Edit button in detail pane
- [ ] All fields editable
- [ ] Changes reflected immediately after save
- [ ] updated_at timestamp updates

---

### US-5: Favorite Contacts
**As a** user
**I want to** mark contacts as favorites
**So that** I can find important contacts quickly

**Acceptance Criteria**:
- [ ] Star/favorite toggle in detail view
- [ ] Favorites show star in list
- [ ] Can filter to show only favorites

---

## Archetype Selection

This app uses the **DUAL_PANE_FLOW** archetype:

| Criterion | Value | Threshold | Pass? |
|-----------|-------|-----------|-------|
| List weight | 0.6 | ≥ 0.3 | Yes |
| Detail weight | 0.7 | ≥ 0.3 | Yes |

**Result**: DUAL_PANE_FLOW selected for master-detail layout.

---

## Technical Notes

### DSL Features Demonstrated
- **Entity with email field**: Unique email validation
- **Indexes**: Multi-column index for sorting performance
- **Workspace with dual signals**: List + Detail pattern
- **Display mode**: `display: detail` creates DETAIL_VIEW signal
- **Signal weighting**: Archetype auto-selection based on weights

### Building on simple_task
This example adds:
1. Unique field constraints (`email unique`)
2. Database indexes for performance
3. Workspace-level layout patterns (DUAL_PANE_FLOW)
4. Signal weighting for archetype selection

### Out of Scope (Beginner+ Example)
- Contact groups/tags
- Import/export
- Duplicate detection
- Contact merging
- Profile photos (file upload)
- Multiple phone numbers/emails

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| List-to-detail navigation | 0ms | Same-page selection |
| Contact search | < 100ms | Filter response time |
| Email click-to-compose | < 500ms | mailto activation |

---

*This specification is designed to be converted to DAZZLE DSL. See `dsl/app.dsl` for the implementation.*
