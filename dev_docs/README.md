# DAZZLE Developer Documentation

This directory contains internal development documentation for the DAZZLE project.

**Last Updated**: November 25, 2025

---

## 📁 Directory Structure

```
dev_docs/
├── releases/          # Release summaries and announcements
├── homebrew/          # Homebrew quick start and checklist
├── development/       # Implementation plans
│   └── plans/        # Active roadmaps
├── llm/              # LLM integration documentation
├── specs/            # Feature specifications
├── features/         # Feature implementation docs
├── architecture/     # Architecture and design docs
└── archived/         # Historical documentation
    ├── 2025-11-development/   # Stage/phase completion reports
    ├── 2025-11-sessions/      # Development session summaries
    ├── implementation-summaries/
    ├── vscode-extension-history/
    ├── homebrew-history/
    └── llm-implementation/
```

---

## 📦 Current Release (v0.1.1)

- [**v0.1.1 Release Summary**](release_v0_1_1_summary.md)
- [**Bug Fixes Summary**](BUG_FIXES_CONSOLIDATED_SUMMARY.md)
- [**v0.2.0 Roadmap**](roadmap_v0_2_0.md)

### v0.1.0 (Initial Release)

- [**Release Announcement**](releases/2025-11-22-release-announcement.md)
- [**Release Summary**](releases/2025-11-22-v0.1.0-release-summary.md)

---

## 🚀 Quick Links

### For New Contributors

| Topic | Document |
|-------|----------|
| Development history | [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md) |
| Project roadmap | [development/plans/IMPLEMENTATION_PLAN.md](development/plans/IMPLEMENTATION_PLAN.md) |
| Gap analysis | [gap_analysis_2025_11_23.md](gap_analysis_2025_11_23.md) |

### Active Documentation

| Topic | Document |
|-------|----------|
| VS Code Extension | [VSCODE_EXTENSION.md](VSCODE_EXTENSION.md) |
| LLM Quick Start | [llm/LLM_QUICK_START.md](llm/LLM_QUICK_START.md) |
| LLM Integration | [llm/LLM_INTEGRATION.md](llm/LLM_INTEGRATION.md) |
| Homebrew Setup | [homebrew/HOMEBREW_QUICKSTART.md](homebrew/HOMEBREW_QUICKSTART.md) |
| Release Checklist | [homebrew/HOMEBREW_RELEASE_CHECKLIST.md](homebrew/HOMEBREW_RELEASE_CHECKLIST.md) |
| Dev Environment | [dual_version_workflow.md](dual_version_workflow.md) |

### Design & Architecture

| Topic | Document |
|-------|----------|
| Vocabulary Design | [vocabulary_design_summary.md](vocabulary_design_summary.md) |
| Domain Patterns | [architecture/domain_patterns_catalog.md](architecture/domain_patterns_catalog.md) |
| Stack Guide | [architecture/stack_interpretation_guide.md](architecture/stack_interpretation_guide.md) |
| Vocabulary Spec | [architecture/dazzle_app_local_vocab_spec_v1.md](architecture/dazzle_app_local_vocab_spec_v1.md) |
| Design Philosophy | [architecture/vocabulary_design_philosophy.md](architecture/vocabulary_design_philosophy.md) |

### LLM Design Philosophy

| Topic | Document |
|-------|----------|
| DSL as Choke Point | [llm/LLM_INTERACTIONS/LLM_DSL_AS_CHOKE_POINT.md](llm/LLM_INTERACTIONS/LLM_DSL_AS_CHOKE_POINT.md) |
| Spec Paradox | [llm/LLM_INTERACTIONS/LLM_DSL_SPEC_PARADOX.md](llm/LLM_INTERACTIONS/LLM_DSL_SPEC_PARADOX.md) |
| File-Based IPC | [llm/LLM_INTERACTIONS/LLM_FILE_BASED_IPC_PATTERN.md](llm/LLM_INTERACTIONS/LLM_FILE_BASED_IPC_PATTERN.md) |
| Analysis Workflow | [llm/LLM_INTERACTIONS/LLM_SPEC_ANALYSIS_WORKFLOW.md](llm/LLM_INTERACTIONS/LLM_SPEC_ANALYSIS_WORKFLOW.md) |

### Feature Specifications

| Topic | Document |
|-------|----------|
| Infrastructure Backend | [specs/DAZZLE_INFRA_BACKEND_SPEC.md](specs/DAZZLE_INFRA_BACKEND_SPEC.md) |
| VS Code Spec | [specs/DAZZLE_VSCODE_SPEC.md](specs/DAZZLE_VSCODE_SPEC.md) |
| LLM Instrumentation | [specs/DAZZLE_LLM_INSTRUMENTATION_SPEC.md](specs/DAZZLE_LLM_INSTRUMENTATION_SPEC.md) |
| Service Profiles | [specs/DAZZLE_SERVICE_PROFILES_SPEC.md](specs/DAZZLE_SERVICE_PROFILES_SPEC.md) |
| Stacks Spec | [specs/DAZZLE_STACKS_SPEC.md](specs/DAZZLE_STACKS_SPEC.md) |
| Test Infrastructure | [specs/TEST_INFRASTRUCTURE_SPEC.md](specs/TEST_INFRASTRUCTURE_SPEC.md) |

### Features

| Topic | Document |
|-------|----------|
| Quick Wins (v0.1.0) | [features/quick_wins_v0_1_implemented.md](features/quick_wins_v0_1_implemented.md) |
| AppSpec Normalization | [features/appspec_normalisation_v1.md](features/appspec_normalisation_v1.md) |
| Micro Stack | [features/MICRO_STACK_SPEC.md](features/MICRO_STACK_SPEC.md) |
| Build Evaluation | [features/BUILD_EVALUATION.md](features/BUILD_EVALUATION.md) |

---

## 📋 Planning Documents

| Document | Purpose |
|----------|---------|
| [NEXT_STAGES_SPEC.md](NEXT_STAGES_SPEC.md) | Detailed specs for upcoming work |
| [roadmap_v0_2_0.md](roadmap_v0_2_0.md) | v0.2.0 release planning |
| [gap_analysis_2025_11_23.md](gap_analysis_2025_11_23.md) | Current gaps and improvements |
| [test_dsl_specification.md](test_dsl_specification.md) | Test DSL design |
| [roadmap_consolidation_summary.md](roadmap_consolidation_summary.md) | Roadmap consolidation |

---

## 📚 Historical Documentation

Historical completion reports and session summaries from the November 2025 development sprint are preserved in `archived/`:

- **Stage Completion Reports**: `archived/2025-11-development/stages/`
- **Phase Completion Reports**: `archived/2025-11-development/phases/`
- **Session Summaries**: `archived/2025-11-sessions/`
- **Implementation Docs**: `archived/implementation-summaries/`

For a consolidated summary, see [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md).

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| Active documentation files | ~35 |
| Archived files | ~40 |
| Feature specifications | 6 |
| Current release | v0.1.1 |

---

## 🔗 Related Documentation

- [Main README](../README.md) - Project overview
- [User Documentation](../docs/README.md) - End-user guides
- [DSL Reference](../docs/DAZZLE_DSL_REFERENCE_0_1.md) - DSL syntax
- [VS Code Extension](../extensions/vscode/README.md) - IDE setup

---

**For questions about these docs, open an issue on GitHub.**
