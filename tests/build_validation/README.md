# DAZZLE Build Validation

Automated testing infrastructure for validating DAZZLE example builds.

## Quick Start

```bash
# Validate all examples
python tests/build_validation/validate_examples.py

# Validate specific example
python tests/build_validation/validate_examples.py --example support_tickets

# Generate JSON report for CI
python tests/build_validation/validate_examples.py --report-format json
```

## What It Tests

### 1. DSL Validation
- Parses DSL files using `dazzle validate`
- Checks for syntax errors
- Validates entity and surface definitions

### 2. AppSpec Building
- Loads project using DAZZLE Python API
- Builds complete AppSpec IR
- Counts entities and surfaces
- Saves AppSpec to `build/appspec.json`

### 3. Structure Validation
- Verifies AppSpec JSON structure
- Checks required fields exist
- Validates entity and surface schemas

## Test Output

### Text Format (default)
```
============================================================
DAZZLE EXAMPLE BUILD VALIDATION REPORT
============================================================

Total Examples: 2
Passed: 2
Failed: 0
Success Rate: 100.0%

Example                        Status     Entities   Surfaces   Time      
----------------------------------------------------------------------
simple_task                    ✓ PASS     1          4          0.25s
support_tickets                ✓ PASS     3          4          0.15s

============================================================
```

### JSON Format (for CI)
```json
{
  "total": 2,
  "passed": 2,
  "failed": 0,
  "success_rate": 100.0,
  "results": [
    {
      "example_name": "simple_task",
      "validation_passed": true,
      "build_passed": true,
      "errors": [],
      "warnings": [],
      "build_time": 0.25,
      "appspec_path": ".../build/appspec.json",
      "entity_count": 1,
      "surface_count": 4
    }
  ]
}
```

## Adding New Examples

1. Create example directory with `dazzle.toml`
2. Add DSL files in configured module paths
3. Run validation: `python tests/build_validation/validate_examples.py`
4. Validation automatically discovers new examples

## CI Integration

The script exits with code 1 if any examples fail, making it suitable for CI/CD:

```yaml
# GitHub Actions example
- name: Validate Examples
  run: python tests/build_validation/validate_examples.py
```

## Architecture

```
tests/build_validation/
  validate_examples.py     # Main validation script
  fixtures/                # Expected outputs (future)
  README.md               # This file
```

### How It Works

1. **Discovery**: Finds all directories with `dazzle.toml`
2. **Validation**: Runs `dazzle validate` CLI command
3. **Building**: Uses DAZZLE Python API to build AppSpec:
   - `load_manifest()` - Load dazzle.toml
   - `discover_dsl_files()` - Find DSL files
   - `parse_modules()` - Parse DSL
   - `build_appspec()` - Build IR
4. **Verification**: Validates AppSpec JSON structure
5. **Reporting**: Generates text or JSON report

## Requirements

- Python 3.9+
- DAZZLE installed (`pip install -e .`)
- Examples with valid `dazzle.toml`

## Future Enhancements

See [BUILD_EVALUATION.md](../../devdocs/BUILD_EVALUATION.md) for planned features:

- LLM context testing
- Backend code generation validation
- Django system checks
- Regression detection
- Performance benchmarking
- CI/CD integration
