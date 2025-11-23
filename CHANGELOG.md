# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] - 2025-11-23

### Fixed

**express_micro stack**:
- **CRITICAL**: Added graceful fallback for AdminJS on incompatible Node.js versions (v25+)
- **CRITICAL**: Added Node.js version constraints to package.json (`>=18.0.0 <25.0.0`)
- **HIGH**: Fixed missing `title` variable in all route handlers (detail, form, delete views)
- **HIGH**: Fixed admin interface not being mounted in server.js
- **HIGH**: Improved error handling with contextual logging in all routes
- **MEDIUM**: Removed deprecated `--backend` flag from generated README.md

### Added

**express_micro stack**:
- Environment variable support with dotenv
- Generated `.env.example` file with all configuration options
- Contextual error messages for better debugging
- Error logging with `console.error()` in all catch blocks

### Changed

**express_micro stack**:
- Server now loads `.env` file automatically on startup
- Admin interface only shows URL in console if successfully loaded
- Error messages now more user-friendly ("Please try again later")
- README regeneration instructions simplified

---

## [0.3.0] - Planned

### Planned Features

**Pattern Support** (Phase 1):
- Add `@pattern` annotation syntax to DSL for explicit architectural pattern modeling
- Support 5 core patterns: repository, service, ports_and_adapters, cqrs, observer
- Implement pattern-aware code generation in django_micro_modular and express_micro stacks
- Pattern annotations are optional - apps work without them
- Documentation: Pattern usage guide and examples

**Design Pattern DSL Evaluation**:
- Comprehensive evaluation of proposed Design Pattern DSL (DP-DSL) layer completed
- Full implementation roadmap defined across v0.3.0 - v0.5.0
- Phased approach: Pattern Annotations (v0.3.0) → DP-DSL Prototype (v0.4.0) → Full DP-DSL (v0.5.0)
- See `dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md` for complete analysis and roadmap

**Additional Planned**:
- Enhanced pattern detection and architectural linting
- Stack compatibility matrix for pattern support
- Pattern-based example projects
- Design spike: ports-and-adapters implementation for UserRegistration use case

**Status**: Under evaluation for Q1 2026 release

---

## [0.2.0] - Planned

### Planned Features

**Testing Infrastructure** (Priority 1):
- Generate Jest/pytest test structure for all CRUD operations
- Model tests with fixtures and validation
- Route/endpoint tests with supertest/pytest-django
- Test coverage reporting

**Database Migrations** (Priority 2):
- Replace `sync({force: true})` with proper migration system
- Sequelize CLI integration for express_micro
- Django migrations already supported in django stacks
- Migration history and rollback support

**Production Features** (Priority 3-7):
- Health check endpoint with database connectivity checks
- Security headers (helmet/django-csp)
- Pagination support for list views
- Auto-generated database indexes on foreign keys
- Logging framework (winston/python logging)

**Timeline**: 7-8 weeks estimated
**Status**: See `dev_docs/roadmap_v0_2_0.md` for detailed specifications

---

## [0.1.0] - 2025-11-22

### Added

**Core Features**:
- Complete DSL parser supporting entities, surfaces, experiences, services, integrations, tests
- Internal Representation (IR) with full Pydantic type system (900+ lines)
- Module system with dependency resolution, cycle detection, topological sorting
- Linker with symbol table building and cross-reference validation
- Comprehensive validation and linting system
- Pattern detection (CRUD, integrations, experience flows)

**Stacks** (6 production-ready):
- `django_micro_modular`: Django apps with admin, forms, views, templates
- `django_api`: Django REST Framework with OpenAPI integration
- `express_micro`: Node.js/Express with Sequelize ORM and AdminJS
- `openapi`: OpenAPI 3.0 specification generation
- `docker`: Docker Compose multi-service orchestration
- `terraform`: AWS infrastructure (ECS, RDS, VPC, ALB)

**CLI Commands**:
- `init`: Initialize new project
- `validate`: Parse, link, and validate DSL
- `lint`: Extended validation with naming conventions
- `build`: Generate code from AppSpec
- `inspect`: Show module interfaces and patterns
- `analyze-spec`: Parse natural language specifications with LLM
- `clone`: Clone example projects
- `demo`: Create demo project
- `example`: Build in-place examples

**LLM Integration**:
- Spec analysis (natural language → structured requirements)
- DSL generation (requirements → .dsl files)
- Interactive Q&A for clarifications
- Cost estimation and safety checks
- Support for Anthropic Claude and OpenAI GPT

**IDE & Tooling**:
- LSP server with real-time diagnostics, hover, completions, go-to-definition
- VS Code extension with syntax highlighting and validation
- Test suite with 59+ tests (unit, integration, LLM)

**Examples**:
- `simple_task`: Minimal starter project (1 entity, 4 surfaces)
- `support_tickets`: Production-like complexity (3 entities, relationships, workflows)

### Documentation
- Complete DSL reference (`docs/DAZZLE_DSL_REFERENCE_0_1.md`)
- EBNF grammar (`docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf`)
- IR documentation (`docs/DAZZLE_IR_0_1.md`)
- VS Code extension user guide
- Stack development guides

---

