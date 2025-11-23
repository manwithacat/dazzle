# DAZZLE Feature Compatibility Matrix

**Version**: 0.1.0
**Last Updated**: 2025-11-23

This matrix shows which DSL features are supported by which stacks and what's planned for future versions.

---

## Surface Modes × Stacks

| Surface Mode | Django Micro | Django API | Express Micro | OpenAPI | Docker | Terraform | Status |
|--------------|:------------:|:----------:|:-------------:|:-------:|:------:|:---------:|--------|
| `list` | ✓ | ✓ | ✓ | ✓ | N/A | N/A | **Stable** |
| `view` | ✓ | ✓ | ✓ | ✓ | N/A | N/A | **Stable** |
| `create` | ✓ | ✓ | ✓ | ✓ | N/A | N/A | **Stable** |
| `edit` | ✓ | ✓ | ✓ | ✓ | N/A | N/A | **Stable** |
| `map` | ✗ | ✗ | ✗ | ✗ | N/A | N/A | ⏳ Planned v0.2 |
| `kanban` | ✗ | ✗ | ✗ | ✗ | N/A | N/A | ⏳ Planned v0.2 |
| `calendar` | ✗ | ✗ | ✗ | ✗ | N/A | N/A | ⏳ Planned v0.3 |
| `chart` | ✗ | ✗ | ✗ | ✗ | N/A | N/A | ⏳ Planned v0.3 |

**Legend**: ✓ Supported | ✗ Not supported | N/A Not applicable | ⏳ Planned

---

## Field Types × Stacks

| Field Type | Django Micro | Django API | Express Micro | OpenAPI | Notes |
|------------|:------------:|:----------:|:-------------:|:-------:|-------|
| `str(N)` | ✓ | ✓ | ✓ | ✓ | VARCHAR(N) |
| `text` | ✓ | ✓ | ✓ | ✓ | TEXT |
| `int` | ✓ | ✓ | ✓ | ✓ | INTEGER |
| `decimal(P,S)` | ✓ | ✓ | ✓ | ✓ | DECIMAL |
| `float` | ✓ | ✓ | ✓ | ✓ | FLOAT |
| `bool` | ✓ | ✓ | ✓ | ✓ | BOOLEAN |
| `date` | ✓ | ✓ | ✓ | ✓ | DATE |
| `time` | ✓ | ✓ | ✓ | ✓ | TIME |
| `datetime` | ✓ | ✓ | ✓ | ✓ | TIMESTAMP |
| `uuid` | ✓ | ✓ | ✓ | ✓ | UUID/CHAR(36) |
| `email` | ✓ | ✓ | ✓ | ✓ | Validated string |
| `url` | ✓ | ✓ | ✓ | ✓ | Validated string |
| `enum[...]` | ✓ | ✓ | ✓ | ✓ | ENUM or VARCHAR |
| `ref Entity` | ✓ | ✓ | ✓ | ✓ | Foreign key |
| `json` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| `file` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| `image` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |

---

## Constraints × Stacks

| Constraint | Django Micro | Django API | Express Micro | OpenAPI | Notes |
|------------|:------------:|:----------:|:-------------:|:-------:|-------|
| `required` | ✓ | ✓ | ✓ | ✓ | NOT NULL |
| `optional` | ✓ | ✓ | ✓ | ✓ | NULL |
| `unique` | ✓ | ✓ | ✓ | ✓ | UNIQUE constraint |
| `pk` | ✓ | ✓ | ✓ | ✓ | Primary key |
| `auto_add` | ✓ | ✓ | ✓ | ✓ | Set on creation |
| `auto_update` | ✓ | ✓ | ✓ | ✓ | Update on save |
| `min(N)` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| `max(N)` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| `regex(pattern)` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| `custom(validator)` | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.3 |

---

## Relationships × Stacks

| Relationship Type | Django Micro | Django API | Express Micro | OpenAPI | Notes |
|-------------------|:------------:|:----------:|:-------------:|:-------:|-------|
| One-to-Many (`ref`) | ✓ | ✓ | ✓ | ✓ | Foreign key |
| Many-to-One (`ref`) | ✓ | ✓ | ✓ | ✓ | Same as above |
| Many-to-Many | ✗ | ✗ | ✗ | ✗ | **Workaround**: Junction entity |
| One-to-One | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| Self-referential | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| Polymorphic | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.3 |

---

## Integration Features × Stacks

| Feature | Django Micro | Django API | Express Micro | OpenAPI | Notes |
|---------|:------------:|:----------:|:-------------:|:-------:|-------|
| REST API | ✓ | ✓ | ✓ | ✓ | Auto-generated |
| Admin Interface | ✓ | ✓ | ✓ | N/A | Django Admin / AdminJS |
| Authentication | ✓ | ✓ | ✓ | ✓ | Basic auth ready |
| Authorization | ⚠️ | ⚠️ | ⚠️ | N/A | Manual customization |
| File Uploads | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| Search | ✗ | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| Filtering | ⚠️ | ⚠️ | ⚠️ | N/A | Basic only |
| Pagination | ✓ | ✓ | ✓ | N/A | Auto-enabled |
| Sorting | ⚠️ | ⚠️ | ⚠️ | N/A | Basic only |

**Legend**: ⚠️ Basic/Limited | ✗ Not yet available

---

## Experience Features (Workflows) × Stacks

| Feature | Django Micro | Django API | Express Micro | Status |
|---------|:------------:|:----------:|:-------------:|--------|
| Basic steps | ⚠️ | ⚠️ | ⚠️ | Limited support |
| Transitions | ⚠️ | ⚠️ | ⚠️ | Limited support |
| Conditional flows | ✗ | ✗ | ✗ | ⏳ Planned v0.2 |
| Parallel tasks | ✗ | ✗ | ✗ | ⏳ Planned v0.3 |
| Approvals | ✗ | ✗ | ✗ | ⏳ Planned v0.3 |

---

## Infrastructure × Stacks

| Feature | Docker | Terraform | Notes |
|---------|:------:|:---------:|-------|
| Database setup | ✓ | ✓ | SQLite/PostgreSQL |
| Web server | ✓ | ✓ | Gunicorn/PM2 |
| Environment vars | ✓ | ✓ | .env support |
| Health checks | ✓ | ✓ | Basic endpoints |
| Auto-scaling | ✗ | ⚠️ | Terraform: Manual config |
| Load balancing | ✗ | ✓ | Terraform: AWS ALB |
| Monitoring | ✗ | ✗ | ⏳ Planned v0.3 |
| Logging | ⚠️ | ⚠️ | Basic only |

---

## Stack-Specific Capabilities

### Django Micro Modular

✓ **Supported**:
- Full Django project structure
- Models with migrations
- Django Admin interface
- Class-based views (ListView, DetailView, CreateView, UpdateView)
- Bootstrap-styled templates
- SQLite database
- Form validation
- URL routing

✗ **Not Supported**:
- REST API (use `django_api` stack)
- Custom map views
- File upload UI
- Advanced search
- Custom permissions

⏳ **Planned**:
- Django Signals support (v0.2)
- Custom validators (v0.2)
- Management commands (v0.2)

### Django API

✓ **Supported**:
- Django REST Framework
- Serializers
- ViewSets
- API routing
- OpenAPI schema generation
- CORS configuration
- Token authentication

✗ **Not Supported**:
- Web UI (use `django_micro_modular` stack)
- GraphQL (use manual implementation)
- WebSockets

⏳ **Planned**:
- JWT authentication (v0.2)
- Rate limiting (v0.2)
- API versioning (v0.3)

### Express Micro

✓ **Supported**:
- Express.js server
- Sequelize ORM models
- EJS templates
- AdminJS interface
- SQLite database
- RESTful routes

✗ **Not Supported**:
- React/Vue frontend
- TypeScript (JavaScript only)
- WebSockets

⏳ **Planned**:
- TypeScript support (v0.2)
- Passport.js integration (v0.2)

### OpenAPI

✓ **Supported**:
- OpenAPI 3.0 spec
- Schemas from entities
- Paths from surfaces
- Component references
- Basic security schemes

✗ **Not Supported**:
- Server implementation
- Advanced auth flows
- Webhooks

⏳ **Planned**:
- Full security schemes (v0.2)
- Webhooks (v0.2)
- Examples and descriptions (v0.2)

---

## Known Limitations (v0.1.0)

### What You Can't Do Yet

1. **Geospatial Features**
   - No `mode: map` surfaces
   - No GPS coordinate types
   - No proximity search
   - **Workaround**: Manual Django/Leaflet integration

2. **File Handling**
   - No `file` or `image` field types
   - No upload UI generation
   - **Workaround**: Add Django FileField manually

3. **Advanced Relationships**
   - No many-to-many direct syntax
   - No polymorphic associations
   - **Workaround**: Create junction entities

4. **Complex UIs**
   - No kanban board mode
   - No calendar view mode
   - No chart/graph generation
   - **Workaround**: Manual template customization

5. **Search & Filtering**
   - No full-text search
   - No advanced filtering UI
   - **Workaround**: Django filters package

6. **Permissions**
   - No declarative permission model
   - **Workaround**: Django permissions system

---

## Workarounds Guide

### Need a Map View?

**DSL (basic entity)**:
```dsl
entity Tree:
  id: uuid pk
  name: str(200) required
  latitude: decimal(9,6) required
  longitude: decimal(9,6) required
```

**Post-generation**:
1. Add `django-leaflet` to requirements.txt
2. Create custom template with map
3. Add view in Django

### Need File Uploads?

**DSL (placeholder field)**:
```dsl
entity Document:
  id: uuid pk
  title: str(200) required
  # file_path: str(500)  # Add after generation
```

**Post-generation**:
1. Add `file` field to Django model
2. Configure `MEDIA_ROOT` in settings
3. Update form to handle uploads

### Need Many-to-Many?

**DSL (junction entity)**:
```dsl
entity Student:
  id: uuid pk
  name: str(100) required

entity Course:
  id: uuid pk
  name: str(100) required

entity Enrollment:
  id: uuid pk
  student: ref Student required
  course: ref Course required
  enrolled_at: datetime auto_add
```

### Need Custom Validation?

**Post-generation**:
1. Edit Django model
2. Add `clean()` method
3. Raise `ValidationError` for custom rules

---

## Feature Request Process

Found a limitation? Want a feature?

1. Check if it's planned in this matrix
2. Open GitHub issue with:
   - Use case description
   - Example DSL you'd like to write
   - Current workaround (if any)
3. Vote on existing issues

---

## Version Roadmap

### v0.2.0 (Planned Q1 2026)
- Map surface mode
- Kanban surface mode
- File/image field types
- Many-to-many relationships
- JSON field type
- Search and filtering DSL
- Custom validators

### v0.3.0 (Planned Q2 2026)
- Calendar surface mode
- Chart/graph generation
- Advanced workflows
- Permissions DSL
- Monitoring and logging
- WebSocket support

### v1.0.0 (Planned Q4 2026)
- Production-ready all features
- Performance optimizations
- Enterprise features
- Full documentation
- Professional support

---

**Questions?** Check the [DSL Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md) or open an issue.

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
