# Implicit Features and System Routes

## The Problem

DAZZLE backends generate implicit features that users don't explicitly define in their DSL:
- **Admin interfaces** (Django Admin, AdminJS)
- **Authentication routes** (login, logout)
- **System pages** (home, 404, 500)
- **API documentation** (Swagger/OpenAPI viewers)

**The Gap**: Users write DSL for their business logic, but have no way to:
1. Know these features exist
2. Access them via clickable UI
3. Control their behavior
4. Customize their appearance

## Current Solution (Implemented)

### 1. Automatic Navigation Generation

Both `django_micro` and `express_micro` backends now automatically surface implicit routes:

**Navigation Bar:**
```html
<nav>
  <ul>
    <li><a href="/task">Tasks</a></li>        <!-- From DSL surfaces -->
    <li><a href="/admin">Admin</a></li>        <!-- System route -->
  </ul>
</nav>
```

**Home Page:**
```html
<h3>Available Resources</h3>
<div class="card">
  <h2>Tasks</h2>
  <a href="/task">View Tasks</a>
</div>

<h3>System Tools</h3>
<div class="card">
  <h2>Admin Dashboard</h2>
  <a href="/admin">Open Admin</a>
</div>
```

### 2. Visual Distinction

System routes are visually separated from user-defined resources:
- **Navigation**: Border separator between app routes and system routes
- **Home page**: Distinct section ("System Tools") with different card styling
- **Card styling**: Blue left border for system features

### 3. Backend Implementation

**Django Micro** (`_generate_nav_links`):
```python
def _generate_nav_links(self) -> str:
    lines = []

    # User-defined entity links
    for entity in self.spec.domain.entities:
        lines.append(f'<li><a href="{entity_url}">{entity_label}</a></li>')

    # System routes
    lines.append('<li><a href="/admin/">Admin</a></li>')

    return '\n'.join(lines)
```

**Express Micro** (`_get_layout_template`):
```javascript
nav_links = []

// User-defined routes
for entity in entities:
    nav_links.append('<li><a href="/{entity}">{label}</a></li>')

// System routes
nav_links.append('<li><a href="/admin">Admin</a></li>')
```

---

## Future Enhancement: DSL Extensions

### Proposal 1: System Surface Declaration

Allow explicit control over implicit features:

```dsl
app simple_task "Simple Task Manager"

# Implicit features become explicit
system admin:
  enabled: true              # Default: true
  path: "/admin"             # Default: varies by backend
  title: "Admin Dashboard"
  in_navigation: true        # Default: true
  require_auth: true         # Default: true if auth enabled
```

### Proposal 2: Navigation Control

Let users customize what appears in navigation:

```dsl
navigation:
  include_system_routes: true    # Show admin, etc.
  include_home: true             # Show home link
  order: [                       # Explicit ordering
    "task_list",
    "user_list",
    "admin"
  ]
  sections:
    - name: "Content"
      items: ["task_list", "user_list"]
    - name: "System"
      items: ["admin"]
```

### Proposal 3: Feature Flags

High-level control over generated features:

```dsl
app simple_task "Simple Task Manager":
  features:
    admin_interface: true       # Generate admin routes
    api_docs: false            # Skip OpenAPI viewer
    auth: false                # No login/logout
    home_page: true            # Generate home page
```

### Proposal 4: Surface Modes Extension

Add `system` mode for explicitly declaring system surfaces:

```dsl
# Existing modes: list, view, create, edit, custom
# New mode: system

surface admin "Admin Dashboard":
  mode: system
  path: "/admin"
  external: true              # Links to existing route, doesn't generate code
  description: "Manage all data and settings"
  icon: "settings"
```

---

## Design Principles

### 1. **Progressive Disclosure**
- Beginners get sensible defaults (admin is auto-included)
- Advanced users can customize via DSL extensions
- No breaking changes to existing DSL

### 2. **Explicit Over Implicit**
- System routes are visible in navigation
- Home page explains what each system tool does
- Generated code includes comments about implicit features

### 3. **Flexibility Without Complexity**
- Simple case: Everything works automatically
- Advanced case: Fine-grained control via DSL
- No need to specify everything just to change one thing

### 4. **Backend Consistency**
- All backends surface implicit features the same way
- Django Admin, AdminJS, and future backends follow same patterns
- Navigation structure is consistent across stacks

---

## Current Implementation Status

### ✅ Implemented (v1)

**Django Micro Backend:**
- Navigation includes admin link
- Home page includes admin card
- Visual separation between app and system routes
- Admin link works out of the box

**Express Micro Backend:**
- Navigation includes AdminJS link
- Home page includes admin card
- Visual separation between app and system routes
- AdminJS link works out of the box

### 🚧 Future Work

**DSL Extensions:**
- System surface declaration
- Navigation customization
- Feature flags
- Surface mode: system

**Additional System Routes:**
- Login/logout (when auth is added)
- API documentation viewer (for API backends)
- Health check/status page
- Deployment info page

**Backend Coverage:**
- Django API backend (REST framework browsable API)
- Next.js frontend (client-side routing)
- Future backends (FastAPI, Laravel, etc.)

---

## Examples

### Current: Auto-Generated (No DSL Changes)

**DSL:**
```dsl
entity Task:
  title: str(200)

surface task_list:
  uses entity Task
  mode: list
```

**Generated Navigation:**
```
Home | Tasks | Admin
```

**Generated Home Page:**
```
Available Resources:
  [Tasks] View Tasks | Create New

System Tools:
  [Admin Dashboard] Open Admin
```

### Future: Customized (With DSL Extensions)

**DSL:**
```dsl
entity Task:
  title: str(200)

surface task_list:
  uses entity Task
  mode: list

# Explicit control
system admin:
  title: "Control Panel"
  path: "/dashboard"
  in_navigation: false     # Hide from nav, only on home

navigation:
  sections:
    - name: "Tasks"
      items: ["task_list"]
```

**Generated Navigation:**
```
Home | Tasks
```

**Generated Home Page:**
```
Available Resources:
  [Tasks] View Tasks | Create New

System Tools:
  [Control Panel] Open Dashboard
```

---

## Benefits

### For Non-Technical Founders
- Discover features they didn't know about
- Understand what's available in their app
- Access admin without reading docs

### For Developers
- Predictable structure across backends
- Easy to find and use admin interfaces
- Control via DSL if needed

### For DAZZLE Ecosystem
- Consistent UX across all generated apps
- Clear separation of concerns
- Foundation for future system features (auth, monitoring, etc.)

---

## Recommendations

### Immediate (Already Done)
1. ✅ Auto-include admin in navigation
2. ✅ Add admin card to home page
3. ✅ Visual distinction for system routes

### Short Term (Next Release)
1. Document implicit features in SPEC.md
2. Add system routes section to README
3. Show admin interface in demo videos

### Medium Term (Future DSL Version)
1. Add `system` surface mode
2. Add `navigation` configuration block
3. Add feature flags to app declaration

### Long Term (As Features Grow)
1. Plugin system for custom system routes
2. Dashboard builder for system pages
3. Role-based access control for system features

---

## Questions for Consideration

1. **Should admin be opt-in or opt-out?**
   - Current: Always included, always visible
   - Alternative: `include_admin: true` in DSL

2. **Should we generate a superuser automatically?**
   - Django: Need to run `createsuperuser`
   - Alternative: Generate with default credentials in dev mode

3. **How to handle multiple admin interfaces?**
   - Django Admin + Django REST Framework browsable API
   - Do we show both? Consolidate? Let user choose?

4. **Should system routes be themeable separately?**
   - Currently inherit app theme
   - Could have system-specific styles

5. **How verbose should home page be?**
   - Current: Explains what admin does
   - Alternative: Just show icon/link, assume users know

---

## Related Documentation

- **SPEC.md**: How to document implicit features for founders
- **Backend Development Guide**: How backends should surface system routes
- **Navigation Best Practices**: UX guidelines for generated apps

---

## Changelog

**2025-11-21**: Initial implementation
- Added admin links to navigation (django_micro, express_micro)
- Added admin card to home page (both backends)
- Visual separation between app and system routes
- Created this documentation
