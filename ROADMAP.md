# DAZZLE Development Roadmap

**Last Updated**: 2025-11-23
**Current Version**: v0.1.0 (Released November 2025)
**Status**: Production-ready, actively maintained

---

## 🎯 Single Source of Truth

This document serves as the **master roadmap** for DAZZLE development. It consolidates all planning documents and provides a high-level view of past, current, and future work.

**For detailed specifications**, see:
- **Immediate Next Steps**: `dev_docs/NEXT_STAGES_SPEC.md` (post-v0.1.0 tasks)
- **v0.2.0 Features**: `dev_docs/roadmap_v0_2_0.md` (next release planning)
- **Test DSL Feature**: `dev_docs/test_dsl_specification.md` (test infrastructure roadmap)
- **Architecture Plans**: `dev_docs/architecture/` (long-term design patterns)

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

**Capabilities**:
- Parse DSL files with entities, surfaces, experiences, services, integrations
- Validate and link multi-file DSL projects
- Generate production-ready code for multiple frameworks
- Real-time IDE integration
- LLM-assisted specification analysis

**Documentation**: Complete DSL reference, IR docs, stack guides

**See**: Release notes in `dev_docs/releases/`

---

### 🚧 v0.1.1 - Stack Improvements (November 2025)

**Status**: COMPLETE

**Focus**: Express Micro stack enhancements

**Changes**:
- Enhanced Express Micro stack with better templates
- Improved Express model generation
- Better EJS template structure
- Bug fixes and quality improvements

**See**: `dev_docs/release_v0_1_1_summary.md`

---

## 🎯 Current Work (Post-v0.1.0)

### Immediate Priorities

**Source**: `dev_docs/NEXT_STAGES_SPEC.md`

#### Phase 1: Critical Documentation 🔴
**Priority**: IMMEDIATE (6-8 hours)

- [ ] Update CLAUDE.md to reflect v0.1.0 reality
- [ ] Create capabilities matrix for all stacks
- [ ] Write comprehensive getting started guide
- [ ] Create quick reference cards

**Why**: AI assistants and contributors currently get outdated guidance

#### Phase 2: Fix Test Suite 🟡
**Priority**: HIGH (4-5 hours)

- [ ] Fix pytest collection errors (3 tests not collecting)
- [ ] Move `dev_docs/test_quick_wins.py` → `tests/unit/`
- [ ] Add tests for `dazzle inspect` command
- [ ] Add tests for vocabulary expansion
- [ ] Verify all 59+ tests pass

**Why**: Clean test suite is critical for contributions and CI/CD

#### Phase 3: Implementation Polish 🟡
**Priority**: MEDIUM (5-7 hours)

- [ ] Complete integration action parsing (remove stubs)
- [ ] Add OpenAPI security schemes
- [ ] Enhance error messages with suggestions
- [ ] Add performance benchmarks

**Why**: Production polish for real-world usage

#### Phase 4: Developer Experience 🟢
**Priority**: LOW (6-7 hours)

- [ ] Add example gallery
- [ ] Create video tutorials
- [ ] Write migration guides
- [ ] Community contribution guidelines

**Why**: Lower barrier to entry for new users

**Total Estimated Effort**: 21-27 hours
**Critical Path** (Phases 1-2): 10-13 hours

---

## 🔮 v0.2.0 - Testing & Production Features (Q1 2026)

**Status**: PLANNED
**Target**: Q1 2026
**Focus**: Testing infrastructure, migrations, production readiness

**Source**: `dev_docs/roadmap_v0_2_0.md`

### Priority 1: Generated Tests (HIGH)

**Objective**: Generate framework tests for generated code quality

**Express Micro Stack**:
- Generate Jest test structure (models/, routes/)
- Model validation tests
- Route integration tests with supertest
- Test configuration and setup files
- npm test scripts

**Django Stacks**:
- Generate pytest test structure
- Model tests with Django TestCase
- View/API tests
- Test fixtures and factories
- Django test commands

**Deliverables**:
- Working test suites for all generated apps
- Test templates and patterns
- Documentation for running/extending tests

**Out of Scope**: DSL-to-test translation (deferred to v0.3.0)

### Priority 2: Database Migrations (HIGH)

**Objective**: Proper migration handling vs sync

**Features**:
- Django: Generate initial migrations
- Express/Sequelize: Migration files
- Migration commands in generated apps
- Schema versioning
- Migration documentation

### Priority 3: Monitoring & Health Checks (MEDIUM)

**Objective**: Production observability

**Features**:
- Health check endpoints
- Metrics collection hooks
- Logging configuration
- Error tracking integration points

### Priority 4: Security Enhancements (MEDIUM)

**Objective**: Security best practices

**Features**:
- CSRF protection (Django)
- XSS prevention
- SQL injection prevention
- Secure defaults in generated code
- Security audit documentation

### Priority 5: Developer Experience (LOW)

**Objective**: Better DX for generated apps

**Features**:
- Hot reload configuration
- Better error pages
- Development vs production configs
- Sample data generation
- README files for generated apps

**Timeline**: 4-6 weeks development + 2 weeks testing

---

## 🚀 v0.3.0 - DSL Test Translation (Q2 2026)

**Status**: FUTURE
**Target**: Q2 2026
**Focus**: Activate test DSL infrastructure

**Source**: `dev_docs/test_dsl_specification.md`

### Major Features

#### 1. DSL Test Translation
**Foundation**: IR types and parser already complete in v0.1.0

- Read `spec.tests` in stack generators
- Translate TestSpec → Jest tests (Express)
- Translate TestSpec → pytest tests (Django)
- Support all assertion types
- Handle setup steps and relationships
- Validate test references

#### 2. Complete Test Support

**Assertions**:
- Field assertions (equals, contains, greater_than, etc.)
- Status assertions (success/error)
- Count assertions
- Error message assertions
- Collection assertions (first, last)

**Setup**:
- Object creation in setup blocks
- Variable references across test
- Relationship handling

**Actions**:
- Create, update, delete, get operations
- Filter and search support
- Order by support

#### 3. Multi-Stack Test Generation

- Same test DSL → Django tests
- Same test DSL → Express tests
- Future: Other stacks (Go, FastAPI, Next.js)

**Dependencies**:
- v0.2.0 test infrastructure must exist
- Stack generators need plugin architecture

**Timeline**: 3-4 weeks development + 1 week testing

---

## 🌟 v0.4.0+ - Future Enhancements

### Domain Patterns (Vocabulary Phase 2C)

**Status**: Foundation implemented in v0.1.0
**Next Steps**: Additional patterns

**Complete** (Nov 2025):
- ✅ soft_delete_behavior
- ✅ status_workflow_pattern
- ✅ multi_tenant_isolation

**Planned**:
- [ ] crud_operations
- [ ] audit_trail
- [ ] file_upload
- [ ] search_filter
- [ ] pagination
- [ ] rate_limiting
- [ ] caching

### Additional Stacks

**Community-Driven**:
- Next.js + React
- Vue.js + Nuxt
- FastAPI
- Go + Gin
- Ruby on Rails
- Spring Boot

### Advanced Features

**Pattern Detection**:
- Automatic CRUD pattern recognition
- Business logic extraction
- Relationship inference

**Export Declarations** (v2.0):
- Module encapsulation
- Public/private interfaces
- Explicit exports

**Port-Based Composition** (v2.0):
- Graph-theoretic module composition
- Formal verification
- Mathematical guarantees

---

## 📋 Planning Document Index

### Active Planning
1. **`ROADMAP.md`** (this file) - Master roadmap, single source of truth
2. **`dev_docs/NEXT_STAGES_SPEC.md`** - Immediate next steps (post-v0.1.0)
3. **`dev_docs/roadmap_v0_2_0.md`** - v0.2.0 feature planning
4. **`dev_docs/test_dsl_specification.md`** - Test DSL 2-phase implementation

### Reference Documents
5. **`dev_docs/gap_analysis_2025_11_23.md`** - Current gaps and improvements
6. **`dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md`** - Design Pattern DSL evaluation
7. **`dev_docs/domain_patterns_phase2_implementation.md`** - Domain patterns summary
8. **`dev_docs/vocabulary_design_summary.md`** - Vocabulary system overview

### Completed Work
9. **`dev_docs/releases/`** - Release summaries and notes
10. **`dev_docs/development/stages/`** - Stage 1-7 completion reports

---

## 🎯 Decision Making Framework

When planning new features, consider:

1. **Is it in scope for current version?**
   - v0.2.0: Testing, migrations, production features
   - v0.3.0+: DSL test translation, advanced patterns

2. **Does it require new IR types?**
   - If yes: Coordinate with parser and linker updates
   - If no: Can be stack-specific

3. **Is it cross-stack or stack-specific?**
   - Cross-stack: Add to IR, update all stacks
   - Stack-specific: Implement in one stack, document pattern

4. **What's the testing strategy?**
   - Unit tests required
   - Integration tests for end-to-end
   - Example DSL files updated

5. **Documentation impact?**
   - DSL reference updated?
   - Stack capabilities updated?
   - User guide updated?

---

## 📊 Success Metrics

### v0.2.0 Success Criteria
- [ ] All generated apps include working tests
- [ ] Test coverage > 60% for generated code
- [ ] Migrations work out of the box
- [ ] Production deployments have health checks
- [ ] Security audit passes
- [ ] Urban Canopy successfully uses v0.2.0

### v0.3.0 Success Criteria
- [ ] Test DSL examples all generate working tests
- [ ] DSL tests run alongside generated tests
- [ ] Test translation works for Django + Express
- [ ] Documentation complete for test DSL
- [ ] Community examples use test DSL

---

## 🤝 Contributing

**Current Contribution Focus**:
- Phase 1 (Documentation): Help update CLAUDE.md and guides
- Phase 2 (Testing): Fix pytest collection, add tests
- Community stacks: Implement for your favorite framework
- Examples: Create real-world DSL examples

**See**:
- `CONTRIBUTING.md` (to be created in Phase 4)
- GitHub Issues for current priorities
- Discussions for feature proposals

---

## 📞 Contacts & Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory

---

**Document Owner**: Claude + James
**Review Frequency**: Monthly
**Next Review**: December 2025
