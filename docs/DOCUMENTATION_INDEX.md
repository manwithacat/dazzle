# DAZZLE Documentation Index

**Last Updated**: 2025-11-23
**DAZZLE Version**: v0.1.1
**Purpose**: Complete index of all DAZZLE documentation

---

## Quick Start

**New Users - Start Here**:
1. [`INSTALLATION.md`](INSTALLATION.md) - Install DAZZLE via Homebrew, pip, or pipx
2. [`README.md`](README.md) - Project overview and quick start
3. [`DAZZLE_DSL_QUICK_REFERENCE.md`](DAZZLE_DSL_QUICK_REFERENCE.md) - DSL syntax at a glance
4. [../examples/simple_task/](../examples/simple_task/) - Minimal starter project

**Comprehensive Learning Path**:
1. Installation → Quick Reference → Full DSL Reference → Build First App → IDE Integration

---

## Core Documentation (`docs/`)

### Language & Syntax

| Document | Description | Audience |
|----------|-------------|----------|
| [`DAZZLE_DSL_REFERENCE_0_1.md`](DAZZLE_DSL_REFERENCE_0_1.md) | Complete DSL syntax reference | All users |
| [`DAZZLE_DSL_QUICK_REFERENCE.md`](DAZZLE_DSL_QUICK_REFERENCE.md) | One-page DSL cheat sheet | All users |
| `DAZZLE_DSL_GRAMMAR_0_1.ebnf` | Formal EBNF grammar | Advanced users, contributors |

### Internal Representation

| Document | Description | Audience |
|----------|-------------|----------|
| [`DAZZLE_IR_0_1.md`](DAZZLE_IR_0_1.md) | IR structure and type system | Stack developers, contributors |

### Features & Capabilities

| Document | Description | Audience |
|----------|-------------|----------|
| [`CAPABILITIES_MATRIX.md`](CAPABILITIES_MATRIX.md) | What each stack can generate | All users |
| [`FEATURE_COMPATIBILITY_MATRIX.md`](FEATURE_COMPATIBILITY_MATRIX.md) | Feature support across stacks | All users |
| [`APP_LOCAL_VOCABULARY.md`](APP_LOCAL_VOCABULARY.md) | App-local vocabulary system | Advanced users |

### Installation & Setup

| Document | Description | Audience |
|----------|-------------|----------|
| [`INSTALLATION.md`](INSTALLATION.md) | Installation methods and troubleshooting | New users |
| [`README.md`](README.md) | Project overview and quick start | New users |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | How to contribute to DAZZLE | Contributors |

### IDE Integration

| Document | Description | Audience |
|----------|-------------|----------|
| [`IDE_INTEGRATION.md`](IDE_INTEGRATION.md) | IDE support overview | All users |
| [`vscode_extension_user_guide.md`](vscode_extension_user_guide.md) | Complete VS Code extension guide | VS Code users |
| [`vscode_extension_quick_reference.md`](vscode_extension_quick_reference.md) | VS Code extension quick ref | VS Code users |

---

## Development Documentation (`dev_docs/`)

### Release Information

| Document | Description | For Version |
|----------|-------------|-------------|
| [`release_v0_1_1_summary.md`](../dev_docs/release_v0_1_1_summary.md) | v0.1.1 release summary and checklist | v0.1.1 |
| [`releases/2025-11-22-v0.1.0-release-summary.md`](../dev_docs/releases/2025-11-22-v0.1.0-release-summary.md) | v0.1.0 official release | v0.1.0 |
| [`releases/2025-11-22-release-announcement.md`](../dev_docs/releases/2025-11-22-release-announcement.md) | v0.1.0 announcement | v0.1.0 |
| [`releases/2025-11-22-stack-consolidation.md`](../dev_docs/releases/2025-11-22-stack-consolidation.md) | Stack terminology refactoring | v0.1.0 |

### Roadmaps & Planning

| Document | Description | Status |
|----------|-------------|--------|
| [`roadmap_v0_2_0.md`](../dev_docs/roadmap_v0_2_0.md) | v0.2.0 features and timeline | Planned |
| [`architecture/dp_dsl_evaluation_and_roadmap.md`](../dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md) | Design Pattern DSL evaluation | Planned v0.3.0+ |
| [`NEXT_STAGES_SPEC.md`](../dev_docs/NEXT_STAGES_SPEC.md) | Future development stages | Planning |
| [`gap_analysis_2025_11_23.md`](../dev_docs/gap_analysis_2025_11_23.md) | Current gaps and improvements | Analysis |

### Bug Fixes & Issues

| Document | Description | Status |
|----------|-------------|--------|
| [`BUG_FIXES_CONSOLIDATED_SUMMARY.md`](../dev_docs/BUG_FIXES_CONSOLIDATED_SUMMARY.md) | **ALL bug fixes consolidated** | ✅ Complete |
| [`BUG_003_DECIMAL_FIELDS_FIXED.md`](../dev_docs/BUG_003_DECIMAL_FIELDS_FIXED.md) | Decimal field parameters fix (Django) | ✅ Fixed |
| [`CRITICAL_BUGS_FIXED_SUMMARY.md`](../dev_docs/CRITICAL_BUGS_FIXED_SUMMARY.md) | URLs and view naming fixes (Django) | ✅ Fixed |
| [`express_micro_comprehensive_improvements.md`](../dev_docs/express_micro_comprehensive_improvements.md) | 7 Express stack improvements | ✅ Fixed |
| [`express_micro_fixes_summary.md`](../dev_docs/express_micro_fixes_summary.md) | Express fixes summary | ✅ Fixed |
| [`express_micro_template_bug_fix.md`](../dev_docs/express_micro_template_bug_fix.md) | Template variable fix | ✅ Fixed |

**Note**: Start with [`BUG_FIXES_CONSOLIDATED_SUMMARY.md`](../dev_docs/BUG_FIXES_CONSOLIDATED_SUMMARY.md) for complete overview of all fixes.

### Architecture & Design

| Document | Description | Purpose |
|----------|-------------|---------|
| [`architecture/dp_dsl_evaluation_and_roadmap.md`](../dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md) | Design Pattern DSL evaluation | v0.3.0+ planning |
| [`architecture/dazzle_second_bottleneck_dp_dsl_practical_recs_v1.md`](../dev_docs/architecture/dazzle_second_bottleneck_dp_dsl_practical_recs_v1.md) | DP-DSL proposal | v0.3.0+ planning |
| [`architecture/dazzle_app_local_vocab_spec_v1.md`](../dev_docs/architecture/dazzle_app_local_vocab_spec_v1.md) | App-local vocabulary spec | Implemented |
| [`architecture/app_local_vocab_evaluation.md`](../dev_docs/architecture/app_local_vocab_evaluation.md) | Vocabulary evaluation | Analysis |
| [`architecture/vocabulary_design_philosophy.md`](../dev_docs/architecture/vocabulary_design_philosophy.md) | Vocabulary design principles | Reference |
| [`architecture/domain_patterns_catalog.md`](../dev_docs/architecture/domain_patterns_catalog.md) | Pattern catalog | Reference |
| [`architecture/stack_interpretation_guide.md`](../dev_docs/architecture/stack_interpretation_guide.md) | How stacks interpret DSL | Stack developers |
| [`architecture/backend-architecture.md`](../dev_docs/architecture/backend-architecture.md) | Backend architecture overview | Contributors |
| [`architecture/implicit-features.md`](../dev_docs/architecture/implicit-features.md) | Implicit vs explicit features | Design reference |

### Feature Implementation

| Document | Description | Status |
|----------|-------------|--------|
| [`features/quick_wins_v0_1_implemented.md`](../dev_docs/features/quick_wins_v0_1_implemented.md) | Quick wins implemented | ✅ v0.1.0 |
| [`vocabulary_phase1_implementation.md`](../dev_docs/vocabulary_phase1_implementation.md) | Vocabulary implementation | ✅ Implemented |
| [`vocabulary_design_summary.md`](../dev_docs/vocabulary_design_summary.md) | Vocabulary design summary | Reference |
| [`vocabulary_example_libraries.md`](../dev_docs/vocabulary_example_libraries.md) | Example vocabulary libraries | Reference |
| [`init_command_implementation_summary.md`](../dev_docs/init_command_implementation_summary.md) | Init command improvements | ✅ Implemented |
| [`init_command_ux_improvement.md`](../dev_docs/init_command_ux_improvement.md) | Init UX improvements | ✅ Implemented |
| [`version_command_implementation_summary.md`](../dev_docs/version_command_implementation_summary.md) | Version command | ✅ v0.1.1 |
| [`example_command_enhancement.md`](../dev_docs/example_command_enhancement.md) | Example command | ✅ Implemented |

### Stack-Specific Documentation

| Document | Description | Stack |
|----------|-------------|-------|
| [`django_api_swagger_enhancement.md`](../dev_docs/django_api_swagger_enhancement.md) | OpenAPI/Swagger integration | django_api |
| [`openapi_backend_analysis.md`](../dev_docs/openapi_backend_analysis.md) | OpenAPI stack analysis | openapi |

### IDE & Tooling

| Document | Description | Status |
|----------|-------------|--------|
| [`vscode_extension_evaluation.md`](../dev_docs/vscode_extension_evaluation.md) | Extension evaluation | Complete |
| [`vscode_extension_migration_summary.md`](../dev_docs/vscode_extension_migration_summary.md) | Migration to official extension | ✅ v0.1.0 |
| [`vscode_extension_recommendations.md`](../dev_docs/vscode_extension_recommendations.md) | Improvement recommendations | Reference |
| [`vscode_extension_diagnostic_improvements.md`](../dev_docs/vscode_extension_diagnostic_improvements.md) | Diagnostic improvements | ✅ v0.4.2 |
| [`vscode_claude_integration.md`](../dev_docs/vscode_claude_integration.md) | Claude integration | Reference |
| [`claude_vscode_integration_implementation.md`](../dev_docs/claude_vscode_integration_implementation.md) | Implementation details | ✅ v0.4.2 |

### LLM Integration

| Document | Description | Purpose |
|----------|-------------|---------|
| [`llm/LLM_INTEGRATION_COMPLETE.md`](../dev_docs/llm/LLM_INTEGRATION_COMPLETE.md) | LLM integration completion | ✅ v0.1.0 |
| [`llm/LLM_INTEGRATION_SUMMARY.md`](../dev_docs/llm/LLM_INTEGRATION_SUMMARY.md) | Integration summary | Reference |
| [`llm/LLM_QUICK_START.md`](../dev_docs/llm/LLM_QUICK_START.md) | Quick start guide | Users |
| [`llm/LLM_INTERACTIONS/LLM_DSL_AS_CHOKE_POINT.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_DSL_AS_CHOKE_POINT.md) | DSL as bottleneck analysis | Design |
| [`llm/LLM_INTERACTIONS/LLM_DSL_SPEC_PARADOX.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_DSL_SPEC_PARADOX.md) | Spec paradox analysis | Design |
| [`llm/LLM_INTERACTIONS/LLM_FILE_BASED_IPC_PATTERN.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_FILE_BASED_IPC_PATTERN.md) | File-based IPC pattern | Design |
| [`llm/LLM_INTERACTIONS/LLM_INTEGRATION_IMPLEMENTATION.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_INTEGRATION_IMPLEMENTATION.md) | Implementation details | Reference |
| [`llm/LLM_INTERACTIONS/LLM_SPEC_ANALYSIS_WORKFLOW.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_SPEC_ANALYSIS_WORKFLOW.md) | Spec analysis workflow | Reference |
| [`llm/LLM_INTERACTIONS/LLM_TESTING_DOCUMENTATION.md`](../dev_docs/llm/LLM_INTERACTIONS/LLM_TESTING_DOCUMENTATION.md) | LLM testing docs | Testing |

### Homebrew Distribution

| Document | Description | Status |
|----------|-------------|--------|
| [`homebrew/HOMEBREW_DISTRIBUTION_COMPLETE.md`](../dev_docs/homebrew/HOMEBREW_DISTRIBUTION_COMPLETE.md) | Distribution completion | ✅ v0.1.0 |
| [`homebrew/HOMEBREW_QUICKSTART.md`](../dev_docs/homebrew/HOMEBREW_QUICKSTART.md) | Quick start guide | Users |
| [`homebrew/HOMEBREW_RELEASE_CHECKLIST.md`](../dev_docs/homebrew/HOMEBREW_RELEASE_CHECKLIST.md) | Release checklist | Maintainers |
| [`homebrew/HOMEBREW_TESTING_GUIDE.md`](../dev_docs/homebrew/HOMEBREW_TESTING_GUIDE.md) | Testing guide | Maintainers |
| [`homebrew/HOMEBREW_TESTING_STATUS.md`](../dev_docs/homebrew/HOMEBREW_TESTING_STATUS.md) | Testing status | Reference |
| [`homebrew/2025-11-22-formula-comparison.md`](../dev_docs/homebrew/2025-11-22-formula-comparison.md) | Formula comparison | Reference |
| [`homebrew/2025-11-22-optimization-analysis.md`](../dev_docs/homebrew/2025-11-22-optimization-analysis.md) | Optimization analysis | Reference |

### Development History (v0.1.0 Completion)

| Document | Description | Phase/Stage |
|----------|-------------|-------------|
| [`development/stages/STAGE1_COMPLETION.md`](../dev_docs/development/stages/STAGE1_COMPLETION.md) | Core DSL and parser | Stage 1 |
| [`development/stages/STAGE2_COMPLETION.md`](../dev_docs/development/stages/STAGE2_COMPLETION.md) | Multi-module system | Stage 2 |
| [`development/stages/STAGE3_COMPLETION.md`](../dev_docs/development/stages/STAGE3_COMPLETION.md) | Stack implementation | Stage 3 |
| [`development/stages/STAGE4_COMPLETION.md`](../dev_docs/development/stages/STAGE4_COMPLETION.md) | Example projects | Stage 4 |
| [`development/stages/STAGE5_COMPLETION.md`](../dev_docs/development/stages/STAGE5_COMPLETION.md) | LSP and IDE support | Stage 5 |
| [`development/stages/STAGE6_COMPLETION.md`](../dev_docs/development/stages/STAGE6_COMPLETION.md) | LLM integration | Stage 6 |
| [`development/stages/STAGE7_COMPLETION.md`](../dev_docs/development/stages/STAGE7_COMPLETION.md) | Distribution and docs | Stage 7 |

### Specifications

| Document | Description | Purpose |
|----------|-------------|---------|
| [`specs/DAZZLE_STACKS_SPEC.md`](../dev_docs/specs/DAZZLE_STACKS_SPEC.md) | Stack system specification | Stack developers |
| [`specs/DAZZLE_VSCODE_SPEC.md`](../dev_docs/specs/DAZZLE_VSCODE_SPEC.md) | VS Code extension spec | Extension developers |
| [`specs/DAZZLE_INFRA_BACKEND_SPEC.md`](../dev_docs/specs/DAZZLE_INFRA_BACKEND_SPEC.md) | Infrastructure backend spec | Stack developers |
| [`specs/DAZZLE_LLM_INSTRUMENTATION_SPEC.md`](../dev_docs/specs/DAZZLE_LLM_INSTRUMENTATION_SPEC.md) | LLM instrumentation spec | LLM developers |
| [`specs/DAZZLE_SERVICE_PROFILES_SPEC.md`](../dev_docs/specs/DAZZLE_SERVICE_PROFILES_SPEC.md) | Service profiles spec | Reference |
| [`specs/TEST_INFRASTRUCTURE_SPEC.md`](../dev_docs/specs/TEST_INFRASTRUCTURE_SPEC.md) | Test infrastructure spec | Testing |

### Other Development Docs

| Document | Description | Purpose |
|----------|-------------|---------|
| [`dual_version_workflow.md`](../dev_docs/dual_version_workflow.md) | Dev vs Homebrew workflow | Contributors |
| [`urban_canopy_feedback_response.md`](../dev_docs/urban_canopy_feedback_response.md) | Urban Canopy testing feedback | Analysis |
| [`README.md`](../dev_docs/README.md) | Dev docs overview | Contributors |

---

## Examples (`examples/`)

### Starter Projects

| Example | Complexity | Description | Use For |
|---------|-----------|-------------|---------|
| [`simple_task/`](../examples/simple_task/) | Minimal | 1 entity, 4 surfaces | Learning DSL basics |
| [`support_tickets/`](../examples/support_tickets/) | Moderate | 3 entities, workflows, integrations | Real-world patterns |
| [`urban_canopy/`](../examples/urban_canopy/) | Complex | 4 entities, geolocation, partial CRUD | Testing, verification |
| [`vocab_demo/`](../examples/vocab_demo/) | Reference | Vocabulary system demo | Advanced features |

### Example Documentation

| Document | Description |
|----------|-------------|
| [`examples/README.md`](../examples/README.md) | Examples overview and usage |

---

## Extension Documentation (`extensions/vscode/`)

| Document | Description | Audience |
|----------|-------------|----------|
| [`README.md`](../extensions/vscode/README.md) | Extension overview | VS Code users |
| [`CLAUDE_INTEGRATION_QUICK_START.md`](../extensions/vscode/CLAUDE_INTEGRATION_QUICK_START.md) | Claude integration guide | Advanced users |

---

## Configuration & Project Files

| File | Purpose | Location |
|------|---------|----------|
| `dazzle.toml` | Project manifest | Project root |
| `.claude/CLAUDE.md` | AI assistant guidance | Project root |
| `CHANGELOG.md` | Version history | Project root |
| `CONTRIBUTING.md` | Contribution guidelines | Project root |
| `README.md` | Main project README | Project root |
| `pyproject.toml` | Python package config | Project root |

---

## Documentation By Use Case

### I want to...

**Learn DAZZLE**:
1. Start: [`INSTALLATION.md`](INSTALLATION.md)
2. Then: [`README.md`](README.md)
3. Then: [`DAZZLE_DSL_QUICK_REFERENCE.md`](DAZZLE_DSL_QUICK_REFERENCE.md)
4. Practice: [`examples/simple_task/`](../examples/simple_task/)
5. Deep dive: [`DAZZLE_DSL_REFERENCE_0_1.md`](DAZZLE_DSL_REFERENCE_0_1.md)

**Build My First App**:
1. [`INSTALLATION.md`](INSTALLATION.md) - Install
2. [`examples/simple_task/`](../examples/simple_task/) - Clone example
3. [`DAZZLE_DSL_QUICK_REFERENCE.md`](DAZZLE_DSL_QUICK_REFERENCE.md) - Modify DSL
4. [`CAPABILITIES_MATRIX.md`](CAPABILITIES_MATRIX.md) - Choose stack

**Use VS Code Extension**:
1. [`vscode_extension_user_guide.md`](vscode_extension_user_guide.md) - Complete guide
2. [`vscode_extension_quick_reference.md`](vscode_extension_quick_reference.md) - Quick ref
3. [`IDE_INTEGRATION.md`](IDE_INTEGRATION.md) - IDE overview

**Develop a Stack**:
1. [`DAZZLE_IR_0_1.md`](DAZZLE_IR_0_1.md) - Understand IR
2. [`../dev_docs/specs/DAZZLE_STACKS_SPEC.md`](../dev_docs/specs/DAZZLE_STACKS_SPEC.md) - Stack spec
3. [`../dev_docs/architecture/stack_interpretation_guide.md`](../dev_docs/architecture/stack_interpretation_guide.md) - Interpretation guide
4. Look at existing stacks in `src/dazzle/stacks/`

**Contribute to DAZZLE**:
1. [`../CONTRIBUTING.md`](../CONTRIBUTING.md) - Guidelines
2. [`../dev_docs/dual_version_workflow.md`](../dev_docs/dual_version_workflow.md) - Dev setup
3. [`../dev_docs/development/stages/`](../dev_docs/development/stages/) - Architecture understanding

**Understand Bug Fixes**:
1. [`../dev_docs/BUG_FIXES_CONSOLIDATED_SUMMARY.md`](../dev_docs/BUG_FIXES_CONSOLIDATED_SUMMARY.md) - All fixes
2. [`CHANGELOG.md`](../CHANGELOG.md) - Version history

**Plan for v0.2.0**:
1. [`../dev_docs/roadmap_v0_2_0.md`](../dev_docs/roadmap_v0_2_0.md) - Complete roadmap

**Plan for v0.3.0+**:
1. [`../dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md`](../dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md) - Pattern DSL

---

## Documentation Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete and current |
| 🔄 | In progress |
| 📅 | Planned |
| 📝 | Draft |
| 🗄️ | Historical/archived |
| ⚠️ | Needs update |

### Current Status

**User Documentation**: ✅ Complete for v0.1.1
**Development Documentation**: ✅ Complete for v0.1.1
**Bug Fix Documentation**: ✅ Consolidated
**Roadmap Documentation**: ✅ v0.2.0 and v0.3.0 planned
**Architecture Documentation**: ✅ Current with proposed enhancements

---

## Contributing to Documentation

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for:
- Documentation style guide
- How to propose documentation changes
- Documentation review process

---

## Changelog

| Date | Change | By |
|------|--------|-----|
| 2025-11-23 | Created comprehensive documentation index | DAZZLE Team |
| 2025-11-23 | Added consolidated bug fix summary reference | DAZZLE Team |
| 2025-11-23 | Updated for v0.1.1 release | DAZZLE Team |

---

**Maintained By**: DAZZLE Core Team
**Last Review**: 2025-11-23
**Next Review**: v0.2.0 release
