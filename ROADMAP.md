# DAZZLE Development Roadmap

**Last Updated**: 2025-11-25
**Current Version**: v0.2.0 Beta (UX Semantic Layer)
**Status**: Beta - Language spec complete, stack implementation in progress

---

## 🎯 Single Source of Truth

This document serves as the **master roadmap** for DAZZLE development. It consolidates all planning documents and provides a high-level view of past, current, and future work.

**For detailed specifications**, see:
- **v0.2.0 Evaluation**: `dev_docs/roadmap_v0_2_0_evaluation.md` (progress assessment)
- **Original v0.2.0 Plan**: `dev_docs/roadmap_v0_2_0.md` (production features - deferred to v0.2.1)
- **Documentation Index**: `docs/DOCUMENTATION_INDEX.md` (all docs)
- **MCP Implementation**: `dev_docs/mcp_v0_2_implementation_summary.md`

---

## 📊 Version History

### ✅ v0.1.0 - Initial Release (November 2025)

**Status**: COMPLETE & RELEASED

**Major Features**:
- Complete DSL parser (800+ lines)
- Full Internal Representation (900+ lines, Pydantic models)
- Module system with dependency resolution and linking
- 6 production stacks (Django Micro, Django API, Express Micro, OpenAPI, Docker, Terraform)
- LLM integration (spec analysis, DSL generation)
- LSP server with VS Code extension
- Comprehensive test suite (59+ tests)
- Homebrew distribution
- CI/CD with GitHub Actions

**Documentation**: Complete DSL reference, IR docs, stack guides

**See**: Release notes in `dev_docs/releases/`

---

### ✅ v0.1.1 - Stack Improvements (November 2025)

**Status**: COMPLETE

**Focus**: Express Micro stack enhancements

**Changes**:
- Enhanced Express Micro stack with better templates
- Improved Express model generation
- Better EJS template structure
- Bug fixes and quality improvements

**See**: `dev_docs/release_v0_1_1_summary.md`

---

## 🎯 v0.2.0 - UX Semantic Layer (December 2025)

**Status**: 🔬 BETA - Language spec complete, shipping mid-December
**Target Release**: December 15, 2025
**Actual Focus**: Fundamental language enhancement (strategic pivot from original plan)

> **📝 Note**: v0.2.0 took a strategic pivot from the original "Testing & Production Features" plan to focus on fundamental DSL language enhancements. Original production features moved to v0.2.1. See `dev_docs/roadmap_v0_2_0_evaluation.md` for detailed analysis.

### What v0.2.0 IS ✅

**UX Semantic Layer** - A fundamental language enhancement that enables semantic specification of user experience without prescribing visual implementation.

#### Core Features (COMPLETE)

**1. Personas** ✅
- Role-based surface/workspace variants
- Scope filtering (who sees what data)
- Field visibility control (show/hide per role)
- Permission controls (read_only per role)
- Purpose customization per persona

**Example**:
```dsl
ux:
  for admin:
    scope: all
    purpose: "Full user management"
    action_primary: user_create

  for member:
    scope: id = current_user.id
    purpose: "View own profile"
    read_only: true
```

**2. Workspaces** ✅
- Composed dashboards from multiple data sources
- Multiple regions with different display modes
- Aggregate metrics and KPIs
- Persona-specific workspace variants
- Display modes: list, grid, timeline, map

**Example**:
```dsl
workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"

  urgent_tasks:
    source: Task
    filter: priority = high
    limit: 5
    action: task_edit

  team_metrics:
    aggregate:
      total: count(Task)
      done: count(Task where status = done)
```

**3. Attention Signals** ✅
- Data-driven alerts and notifications
- Severity levels: critical, warning, notice, info
- Conditional triggers with expressions
- Action associations
- User-facing messages

**Example**:
```dsl
attention critical:
  when: due_date < today and status != done
  message: "Overdue task"
  action: task_edit
```

**4. Information Needs** ✅
- Declarative data requirements
- `show`, `sort`, `filter`, `search` directives
- Empty state messages
- Semantic specification (what, not how)

**5. Purpose Statements** ✅
- Single-line semantic intent
- Documents WHY surfaces/workspaces exist
- Guides stack generators

#### Documentation (COMPLETE) ✅

- **[DSL Reference v0.2](docs/v0.2/DAZZLE_DSL_REFERENCE.md)** (609 lines)
- **[UX Semantic Layer Spec](docs/v0.2/UX_SEMANTIC_LAYER_SPEC.md)** (55K)
- **[Migration Guide v0.1→v0.2](docs/v0.2/MIGRATION_GUIDE.md)** (431 lines)
- **[DSL Grammar v0.2](docs/v0.2/DAZZLE_DSL_GRAMMAR.ebnf)**
- **[DSL Examples v0.2](docs/v0.2/DAZZLE_EXAMPLES.dsl)**
- **[Capabilities Matrix](docs/v0.2/CAPABILITIES_MATRIX.md)**
- **[App-Local Vocabulary](docs/v0.2/APP_LOCAL_VOCABULARY.md)**

#### MCP Server Enhancements (COMPLETE) ✅

- **Semantic Concept Lookup** - `lookup_concept(term)` tool
- **Example Search** - `find_examples(features=[...])` tool
- **Structured Semantic Index** - 16 concepts, JSON format
- **Example Catalog** - Searchable project metadata
- **v0.2-Aware Resources** - All docs reference v0.2

**Files**: `src/dazzle/mcp/semantics.py`, `src/dazzle/mcp/examples.py`

#### Example Projects (IN PROGRESS) 🔄

- ✅ **support_tickets** - Full UX Semantic Layer showcase
- 🔄 **simple_task** - Basic v0.2 features
- 🔄 **fieldtest_hub** - Active development

#### Stack Implementation (PARTIAL) ⚠️

**Current State**:
- ✅ Information needs - Partially implemented
- 🔄 Workspaces - Basic support
- ❌ Personas - Not yet implemented
- ❌ Attention signals - Not yet implemented
- ❌ Purpose statements - Not yet used

**Gap**: Language spec is ahead of stack generator implementation. Full feature parity targeted for v0.2.2.

### What v0.2.0 is NOT ❌

The following features were in the **original v0.2.0 plan** but were **moved to v0.2.1**:

- ❌ Generated tests (Jest, pytest)
- ❌ Database migrations (vs sync)
- ❌ Health check endpoints
- ❌ Security headers (Helmet)
- ❌ Pagination support
- ❌ Database indexes
- ❌ Logging framework

**Rationale**: Strategic decision to enhance DSL language first, then improve code generation quality. See `dev_docs/roadmap_v0_2_0_evaluation.md`.

### Success Criteria for v0.2.0

**Ship when** (Target: Dec 15, 2025):
- ✅ UX Semantic Layer DSL complete
- ✅ Documentation complete
- ✅ MCP enhancements complete
- ✅ Migration guide available
- ✅ At least one example project showcases all features
- 🔄 Basic workspace support in at least one stack
- ✅ Backward compatibility with v0.1

**Post-Release**:
- Gather feedback on UX Semantic Layer
- Identify stack generator priorities
- Plan v0.2.1 and v0.2.2 work

---

## 🚧 v0.2.1 - Production Readiness (February 2026)

**Status**: PLANNED
**Target Release**: February 2026 (8-10 weeks from now)
**Focus**: Testing, migrations, production features (original v0.2.0 plan)

> **📝 Note**: This is the **original v0.2.0 roadmap** content, now moved to v0.2.1.

### Objectives

Make DAZZLE-generated applications production-ready with proper testing, database management, and operational features.

### Priority 1: Generated Tests (HIGH) 🔴

**Objective**: Generate complete test infrastructure for all generated apps

#### Express Micro Stack
- **Test Structure**:
  ```
  tests/
    ├── setup.js
    ├── models/
    │   └── {entity}.test.js
    └── routes/
        └── {entity}.test.js
  ```
- **Dependencies**: Jest, Supertest
- **Coverage**: Model tests, route tests, integration tests
- **Documentation**: How to run and extend tests

#### Django Stacks
- **Test Structure**:
  ```
  tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_views.py
    └── test_api.py
  ```
- **Framework**: pytest + Django TestCase
- **Coverage**: Model tests, view tests, API tests
- **Fixtures**: Auto-generated test data

**Deliverables**:
- Working test suites for all generated apps
- Test templates in stack generators
- CI/CD integration examples
- Documentation: Testing guide

**Estimate**: 2-3 weeks

### Priority 2: Database Migrations (HIGH) 🔴

**Objective**: Replace `sync({force: true})` with proper migration system

**Problem**: Current `npm run init-db` destroys all data - dangerous in production.

#### Express/Sequelize
- Add Sequelize CLI
- Generate initial migrations from entities
- Migration commands (`migrate`, `migrate:undo`, `migrate:status`)
- Update `init-db` to use migrations
- Documentation: Migration workflow

#### Django
- Generate initial migrations automatically
- Migration commands integrated
- Schema versioning
- Rollback support

**Deliverables**:
- Migration files generated with apps
- Safe schema evolution
- Migration documentation
- No more data destruction

**Estimate**: 3-4 weeks

### Priority 3: Health Check Endpoints (MEDIUM) 🟡

**Objective**: Add monitoring and deployment readiness

**Features**:
- `/health` endpoint (basic health check)
- `/health/detailed` endpoint (component status)
- Database connectivity check
- Environment information
- Uptime tracking

**Example**:
```javascript
{
  "status": "healthy",
  "timestamp": "2025-12-01T10:00:00Z",
  "uptime": 3600,
  "database": "connected",
  "environment": "production"
}
```

**Estimate**: 1 week

### Priority 4: Security Headers (MEDIUM) 🟡

**Objective**: Security best practices out of the box

**Features**:
- Helmet.js integration (Express)
- Django security middleware
- Content Security Policy
- XSS protection
- CSRF protection
- Documentation: Security configuration

**Estimate**: 1 week

### Priority 5: Pagination Support (MEDIUM) 🟡

**Objective**: Handle large datasets efficiently

**Features**:
- Pagination in list routes
- Page/limit query parameters
- Total count and page metadata
- Previous/next navigation
- Template updates for pagination UI

**Example**:
```javascript
{
  "data": [...],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 150,
    "totalPages": 8,
    "hasNext": true,
    "hasPrev": false
  }
}
```

**Estimate**: 2 weeks

### Priority 6: Database Indexes (LOW) 🟢

**Objective**: Performance optimization

**Features**:
- Auto-generate indexes on foreign keys
- Index commonly queried fields
- Composite indexes for multi-field queries
- Index naming conventions

**Estimate**: 2 weeks

### Priority 7: Logging Framework (LOW) 🟢

**Objective**: Structured logging for production

**Features**:
- Winston (Express) / Python logging (Django)
- Structured JSON logs
- Log levels (error, warn, info, debug)
- File and console transports
- Request logging middleware

**Estimate**: 2 weeks

### Timeline

**Total Development**: 8-10 weeks
**Testing & QA**: 2 weeks
**Documentation**: 1 week

**Total**: 11-13 weeks (Target: End of February 2026)

### Success Criteria

**v0.2.1 is ready when**:
- ✅ All generated apps include working tests
- ✅ Test coverage > 60% for generated code
- ✅ Database migrations work (no more force sync)
- ✅ Health check endpoints respond correctly
- ✅ Security headers applied by default
- ✅ Pagination works on all list views
- ✅ Database indexes auto-generated
- ✅ Logging framework integrated
- ✅ All features documented
- ✅ Urban Canopy rebuilt and verified with v0.2.1
- ✅ No breaking changes from v0.2.0

---

## 🎨 v0.2.2 - Full UX Semantic Layer Implementation (March 2026)

**Status**: PLANNED
**Target Release**: March 2026 (12-14 weeks from now)
**Focus**: Complete stack generator support for v0.2 DSL features

### Objectives

Achieve **feature parity** between DSL v0.2 language spec and stack generator implementation.

### Priority 1: Persona Implementation (HIGH) 🔴

**Objective**: Full persona support in all stacks

#### Django Micro
- Scope filtering with Django QuerySets
- Permission checks integration
- Field visibility (show/hide)
- Role detection from user context
- Template rendering per persona

#### Express Micro
- Scope filtering in Sequelize queries
- Middleware for role detection
- Conditional rendering in EJS
- Field filtering per role

**Features**:
- `scope:` expressions → filtered queries
- `show:` / `hide:` → template logic
- `read_only:` → form disabling
- `action_primary:` → different CTAs per role
- `show_aggregate:` → role-specific metrics

**Estimate**: 3-4 weeks

### Priority 2: Workspace Rendering (HIGH) 🔴

**Objective**: Complete workspace dashboard generation

**Features**:
- Multi-region layouts
- Display mode support (list, grid, timeline, map)
- Aggregate metric calculation and display
- Persona-specific workspace variants
- Empty state handling
- Action associations

**Stack Support**:
- Django: Dashboard views with multiple regions
- Express: Composite dashboard routes
- Templates: Responsive multi-region layouts

**Estimate**: 2-3 weeks

### Priority 3: Attention Signal Visualization (MEDIUM) 🟡

**Objective**: Render attention signals in UI

**Features**:
- Conditional styling based on `when:` expressions
- Severity-based CSS classes (critical, warning, notice, info)
- User-facing messages
- Action links/buttons
- Icon/color schemes per severity

**Implementation**:
- Evaluate conditions in backend
- Pass signal metadata to templates
- CSS framework integration
- Accessibility (ARIA labels, screen readers)

**Estimate**: 2 weeks

### Priority 4: Information Needs Complete (MEDIUM) 🟡

**Objective**: Full support for all UX directives

**Features**:
- `show:` → field selection
- `sort:` → default ordering with user override
- `filter:` → filter UI components
- `search:` → text search implementation
- `empty:` → empty state messages

**Current Status**: Partial support, needs completion

**Estimate**: 2 weeks

### Priority 5: Purpose-Driven Generation (LOW) 🟢

**Objective**: Use `purpose:` statements to improve generated code

**Features**:
- Purpose statements in code comments
- README generation with purposes
- Help text in UI
- Documentation generation

**Estimate**: 1 week

### Timeline

**Total Development**: 10-12 weeks
**Testing & QA**: 2 weeks
**Documentation**: 1 week

**Total**: 13-15 weeks (Target: End of March 2026)

### Success Criteria

**v0.2.2 is ready when**:
- ✅ Personas fully work in Django and Express
- ✅ Workspaces render correctly with all display modes
- ✅ Attention signals visible in UI
- ✅ All information needs directives implemented
- ✅ Purpose statements used throughout generated code
- ✅ All v0.2 example projects work end-to-end
- ✅ Documentation updated with implementation details
- ✅ Performance benchmarks acceptable
- ✅ No regressions from v0.2.1

---

## 🚀 v0.3.0 - Advanced Features (Q2 2026)

**Status**: FUTURE
**Target**: Q2 2026
**Focus**: Authentication, authorization, real-time

### Planned Features

#### 1. Authentication Generation
- User registration/login
- Password reset flows
- Email verification
- Session management
- OAuth integration
- JWT support

#### 2. Authorization (RBAC)
- Role-based access control
- Permission system
- Policy definitions in DSL
- Integration with personas

#### 3. Real-Time Features
- WebSocket support
- Live updates
- Presence indicators
- Notifications

#### 4. DSL Test Translation
**Foundation**: IR types and parser already complete in v0.1.0

- Read `spec.tests` in stack generators
- Translate TestSpec → Jest tests (Express)
- Translate TestSpec → pytest tests (Django)
- Support all assertion types

**Source**: `dev_docs/test_dsl_specification.md`

### Timeline

**Target**: Q2 2026 (April-June)
**Estimate**: 12-16 weeks total

---

## 🌟 v0.4.0+ - Future Vision

### Additional Stacks
- Next.js + React
- Vue.js + Nuxt
- FastAPI
- Go + Gin
- Ruby on Rails
- Spring Boot

### Platform Support
- Windows distribution (Chocolatey, winget, Scoop)
- Linux packages (.deb, .rpm, Snap, AppImage)
- Container images (Docker Hub)
- Cloud IDE integration (Codespaces, Gitpod)

### IDE Integrations
- JetBrains plugins (IntelliJ, PyCharm)
- Vim/Neovim plugin
- Emacs mode
- Enhanced LSP features

### Advanced DSL Features
- Computed fields
- Hooks/triggers
- Advanced validation rules
- Business logic expressions
- Module encapsulation
- Export declarations

### AI/LLM Enhancements
- Natural language DSL generation
- Code review and suggestions
- Pattern detection and extraction
- Documentation generation
- Test generation from descriptions

---

## 📋 Planning Document Index

### Active Roadmaps
1. **`ROADMAP.md`** (this file) - Master roadmap, single source of truth
2. **`dev_docs/roadmap_v0_2_0_evaluation.md`** - v0.2.0 progress evaluation
3. **`dev_docs/roadmap_v0_2_0.md`** - Original v0.2.0 plan (now v0.2.1)

### Documentation
4. **`docs/README.md`** - Main documentation hub
5. **`docs/DOCUMENTATION_INDEX.md`** - Complete documentation index
6. **`docs/v0.2/DAZZLE_DSL_REFERENCE.md`** - v0.2 language spec
7. **`docs/v0.2/MIGRATION_GUIDE.md`** - v0.1 → v0.2 migration

### Implementation Summaries
8. **`dev_docs/mcp_v0_2_implementation_summary.md`** - MCP enhancements
9. **`dev_docs/docs_consolidation_summary.md`** - Documentation reorg

### Reference Documents
10. **`dev_docs/gap_analysis_2025_11_23.md`** - Current gaps
11. **`dev_docs/test_dsl_specification.md`** - Test DSL planning

### Completed Work
12. **`dev_docs/releases/`** - Release summaries
13. **`dev_docs/development/stages/`** - Stage completion reports

---

## 🎯 Current Priorities (December 2025)

### This Week
1. ✅ Complete v0.2.0 documentation
2. ✅ Ship v0.2.0 Beta (language spec)
3. 🔄 Gather feedback on UX Semantic Layer
4. 🔄 Update roadmap (this document)

### This Month
1. Test v0.2.0 with real projects
2. Start v0.2.1 planning in detail
3. Begin persona implementation prototype
4. Identify critical production gaps

### Next Quarter (Q1 2026)
1. Ship v0.2.1 (Production Readiness)
2. Progress on v0.2.2 (Feature Parity)
3. Plan v0.3.0 features
4. Gather community feedback

---

## 📊 Success Metrics

### Overall Project Health
- ⭐ GitHub stars
- 📥 Homebrew installs
- 💬 Community engagement
- 🐛 Issue resolution time
- 📚 Documentation quality

### v0.2 Series Success
- **v0.2.0**: Language adoption, MCP usage, feedback quality
- **v0.2.1**: Production deployments, test coverage, migration success
- **v0.2.2**: Feature parity achieved, performance metrics, user satisfaction

---

## 🤝 Contributing

**Current Contribution Opportunities**:

### v0.2.0 (Now)
- Test UX Semantic Layer with real projects
- Provide feedback on personas/workspaces
- Write example DSL files
- Report documentation gaps

### v0.2.1 (Next)
- Help implement test generation
- Contribute migration templates
- Security review and testing
- Performance benchmarking

### v0.2.2 (Future)
- Implement persona rendering
- Build workspace layouts
- Design attention signal UI
- Create CSS themes

### Anytime
- Create examples for your domain
- Write tutorials and guides
- Answer community questions
- Improve documentation

**See**: `CONTRIBUTING.md` (to be created)

---

## 📞 Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

---

**Document Owner**: Claude + James
**Review Frequency**: Monthly
**Last Review**: 2025-11-25
**Next Review**: January 2026

---

## 📝 Changelog

### 2025-11-25
- **MAJOR UPDATE**: Revised entire roadmap to reflect v0.2.0 reality
- Added v0.2.0 as "UX Semantic Layer" (actual work done)
- Created v0.2.1 for "Production Readiness" (original v0.2.0 plan)
- Created v0.2.2 for "Full UX Semantic Layer Implementation"
- Updated success criteria and timelines
- Added decision rationale and evaluation reference
- Updated current priorities and contribution opportunities

### 2025-11-23
- Original roadmap created
- v0.2.0 planned as "Testing & Production Features"
- v0.3.0 planned as "DSL Test Translation"
