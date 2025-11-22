# Build Evaluation Test Infrastructure

## Overview

This document outlines test infrastructure for validating DAZZLE example builds and ensuring that fresh LLM instances can successfully pick up project context and execute sensible build processes.

## Goals

1. **Automated Build Validation** - Verify all examples build successfully
2. **LLM Context Testing** - Ensure project documentation/structure is sufficient for LLM comprehension
3. **Build Quality Assessment** - Validate that generated code meets quality standards
4. **Regression Prevention** - Catch breaking changes in examples or core framework

## Test Infrastructure Components

### 1. Build Validation Script

**Location**: `tests/build_validation/validate_examples.py`

**Purpose**: Automated testing of all example projects

**Features**:
- Discovers all example projects (by presence of `dazzle.toml`)
- Validates DSL files
- Builds AppSpec for each example
- Optionally generates backend code
- Validates generated code structure
- Runs Django checks on generated projects

**Usage**:
```bash
# Validate all examples
python tests/build_validation/validate_examples.py

# Validate specific example
python tests/build_validation/validate_examples.py --example support_tickets

# Full build with code generation
python tests/build_validation/validate_examples.py --full-build

# Generate report
python tests/build_validation/validate_examples.py --report-format json
```

### 2. LLM Context Evaluation

**Location**: `tests/build_validation/llm_context_test.py`

**Purpose**: Test if LLM can understand and build projects from scratch

**Approach**:
1. Start with fresh LLM session (no history)
2. Provide only:
   - Example directory path
   - Task: "Build this DAZZLE project"
   - Available documentation
3. Evaluate if LLM:
   - Discovers `dazzle.toml` and `.dsl` files
   - Runs validation
   - Executes build
   - Handles errors appropriately
   - Produces working output

**Success Criteria**:
- LLM finds and reads `dazzle.toml`
- LLM discovers DSL files in configured paths
- LLM runs `dazzle validate` before build
- LLM executes appropriate build command
- LLM validates build output
- Build completes without human intervention

### 3. Build Quality Metrics

**What to Validate**:

#### AppSpec Validation
- All entities parsed correctly
- All surfaces defined properly
- Relationships mapped correctly
- Field types are valid
- Constraints preserved

#### Generated Code Validation (if applicable)
- Django models created for each entity
- Migrations generated
- Admin interfaces configured
- URLs configured
- Views created for surfaces
- Forms generated for create/edit surfaces

#### Code Quality Checks
- Python syntax valid (`python -m py_compile`)
- Django system checks pass (`manage.py check`)
- No missing imports
- Proper formatting (optional: black, ruff)

### 4. Test Fixtures and Expected Outputs

**Location**: `tests/build_validation/fixtures/`

**Structure**:
```
fixtures/
  support_tickets/
    expected_appspec.json    # Expected AppSpec structure
    expected_models.py       # Expected model definitions
    expected_entities.txt    # List of expected entities
    expected_surfaces.txt    # List of expected surfaces
```

**Validation**:
- Compare actual AppSpec with expected structure
- Verify all expected entities/surfaces present
- Check field counts and types
- Validate relationships

## Implementation Plan

### Phase 1: Core Validation Infrastructure

**Tasks**:
1. Create `tests/build_validation/` directory structure
2. Implement `validate_examples.py`:
   - Example discovery
   - DSL validation
   - AppSpec building
   - Error collection and reporting
3. Add test fixtures for `support_tickets` example
4. Create CI/CD integration (GitHub Actions)

**Deliverables**:
- Working validation script
- Test fixtures for at least one example
- Documentation on adding new examples

### Phase 2: LLM Context Testing

**Tasks**:
1. Design LLM evaluation protocol
2. Create minimal context package (what files/docs LLM receives)
3. Implement `llm_context_test.py`:
   - Session initialization
   - Task prompt generation
   - Action tracking
   - Success/failure detection
4. Define success criteria metrics
5. Test with multiple examples

**Deliverables**:
- LLM context test harness
- Success criteria rubric
- Context evaluation report

### Phase 3: Quality Metrics and Reporting

**Tasks**:
1. Implement code generation validation
2. Add Django checks integration
3. Create comprehensive reporting:
   - JSON output for CI
   - HTML report for humans
   - Diff reporting for regressions
4. Add performance metrics (build time, file sizes)
5. Create dashboard visualization

**Deliverables**:
- Quality metrics framework
- Multi-format reporting
- Performance benchmarks

### Phase 4: Continuous Integration

**Tasks**:
1. GitHub Actions workflow for PR validation
2. Nightly full build tests
3. Example regression detection
4. Automated issue creation for failures
5. Documentation updates

**Deliverables**:
- CI/CD pipelines
- Regression detection system
- Automated alerts

## Test Script Implementation

See `tests/build_validation/validate_examples.py` for full implementation.

**Key Features**:
- Automatic example discovery
- DSL validation via CLI
- AppSpec building and validation
- Error collection and reporting
- JSON and text output formats
- CI/CD friendly exit codes

## LLM Context Test Design

### Minimal Context Package

**What LLM Receives**:
```
examples/support_tickets/
  dazzle.toml
  dsl/
    app.dsl
  README.md (optional, for context)

docs/
  CLI_REFERENCE.md
  DSL_SYNTAX.md
```

**Task Prompt**:
```
You are given a DAZZLE project at path: examples/support_tickets/

Your task is to:
1. Understand the project structure
2. Validate the DSL files
3. Build the AppSpec
4. Report the results

You have access to the DAZZLE CLI and documentation.
```

### Success Evaluation

**Automated Checks**:
- [ ] LLM reads `dazzle.toml`
- [ ] LLM discovers DSL files location
- [ ] LLM runs `dazzle validate`
- [ ] LLM handles validation errors (if any)
- [ ] LLM runs appropriate build command
- [ ] LLM verifies build output exists
- [ ] Build completes successfully
- [ ] No hallucinated commands or paths

**Quality Metrics**:
- **Time to completion**: How long does LLM take?
- **Tool calls**: How many tool invocations needed?
- **Error recovery**: Does LLM recover from errors?
- **Documentation usage**: Does LLM reference docs?

## CI/CD Integration

### GitHub Actions Workflow

**File**: `.github/workflows/validate-examples.yml`

```yaml
name: Validate Examples

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
  schedule:
    # Run nightly at 2am UTC
    - cron: '0 2 * * *'

jobs:
  validate-examples:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install DAZZLE
        run: |
          pip install -e .

      - name: Validate Examples
        run: |
          python tests/build_validation/validate_examples.py --report-format json > report.json

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: validation-report
          path: report.json

      - name: Check Results
        run: |
          python -c "import json; report = json.load(open('report.json')); exit(0 if report['failed'] == 0 else 1)"
```

## Success Criteria

### Example Validation Passes When:
1. ✓ DSL files parse without errors
2. ✓ AppSpec builds successfully
3. ✓ AppSpec contains all expected entities/surfaces
4. ✓ Generated code (if applicable) passes Django checks
5. ✓ No regressions from previous builds

### LLM Context Test Passes When:
1. ✓ LLM completes build without human intervention
2. ✓ LLM uses correct DAZZLE CLI commands
3. ✓ LLM handles errors appropriately
4. ✓ LLM validates output
5. ✓ Build produces correct AppSpec
6. ✓ No hallucinated commands or incorrect assumptions

## Next Steps

1. **Immediate**: Create `tests/build_validation/` directory structure
2. **This Week**: Implement core validation script
3. **Next Sprint**: Add LLM context testing framework
4. **Ongoing**: Integrate into CI/CD pipeline

## Related Documentation

- DAZZLE CLI Reference
- DSL Syntax Guide
- Contributing Guidelines
- Testing Best Practices
