#!/usr/bin/env python3
"""
DAZZLE Example Build Validation

Tests all example projects to ensure they build successfully
and meet quality standards.
"""

import os
import subprocess
import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class BuildResult:
    """Result of validating a single example"""
    example_name: str
    validation_passed: bool
    build_passed: bool
    errors: List[str]
    warnings: List[str]
    build_time: float
    appspec_path: Optional[str]
    entity_count: int = 0
    surface_count: int = 0


class ExampleValidator:
    """Validates DAZZLE example projects"""
    
    def __init__(self, examples_dir: Path):
        self.examples_dir = examples_dir
        self.results: List[BuildResult] = []

    def discover_examples(self) -> List[Path]:
        """Find all directories with dazzle.toml"""
        examples = []
        for item in self.examples_dir.iterdir():
            if item.is_dir():
                toml_path = item / "dazzle.toml"
                if toml_path.exists():
                    examples.append(item)
        return sorted(examples)

    def validate_dsl(self, example_path: Path) -> Tuple[bool, List[str]]:
        """Run dazzle validate on example"""
        try:
            result = subprocess.run(
                ["dazzle", "validate", "--manifest", "dazzle.toml"],
                cwd=example_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            errors = []
            if result.returncode != 0:
                # Capture both stdout and stderr
                error_msg = result.stderr.strip() or result.stdout.strip()
                if error_msg:
                    errors.append(error_msg)
                else:
                    errors.append(f"Validation failed with exit code {result.returncode}")
            return result.returncode == 0, errors
        except subprocess.TimeoutExpired:
            return False, ["Validation timed out after 30 seconds"]
        except FileNotFoundError:
            return False, ["dazzle command not found - is DAZZLE installed?"]
        except Exception as e:
            return False, [f"Validation error: {str(e)}"]

    def build_appspec_python(self, example_path: Path) -> Tuple[bool, Optional[Path], List[str], int, int]:
        """Build AppSpec using Python API
        
        Returns: (success, appspec_path, errors, entity_count, surface_count)
        """
        try:
            # Import DAZZLE core modules
            from dazzle.core.manifest import load_manifest
            from dazzle.core.fileset import discover_dsl_files
            from dazzle.core.parser import parse_modules
            from dazzle.core.linker import build_appspec
            
            # Load manifest
            manifest_path = example_path / "dazzle.toml"
            mf = load_manifest(manifest_path)
            
            # Discover and parse DSL files
            dsl_files = discover_dsl_files(example_path, mf)
            modules = parse_modules(dsl_files)
            
            # Build AppSpec
            appspec = build_appspec(modules, mf.project_root)
            
            # Create build directory
            build_dir = example_path / "build"
            build_dir.mkdir(exist_ok=True)
            appspec_path = build_dir / "appspec.json"
            
            # Save AppSpec to JSON
            appspec_dict = appspec.model_dump(mode="json")
            with open(appspec_path, 'w') as f:
                json.dump(appspec_dict, f, indent=2)
            
            # Count entities and surfaces
            entity_count = len(appspec.domain.entities)
            surface_count = len(appspec.surfaces)
            
            return True, appspec_path, [], entity_count, surface_count
            
        except Exception as e:
            error_msg = f"AppSpec build error: {str(e)}"
            # Include traceback for debugging
            import traceback
            error_detail = traceback.format_exc()
            return False, None, [error_msg, error_detail], 0, 0

    def validate_appspec(
        self, 
        appspec_path: Path, 
        example_name: str
    ) -> Tuple[bool, List[str]]:
        """Validate AppSpec structure and content"""
        errors = []
        
        try:
            with open(appspec_path) as f:
                appspec = json.load(f)

            # Check required top-level fields
            if "name" not in appspec:
                errors.append("Missing required field: name")
            if "domain" not in appspec:
                errors.append("Missing required field: domain")

            # Validate domain structure
            if "domain" in appspec:
                domain = appspec["domain"]
                
                # Check entities
                if "entities" not in domain:
                    errors.append("Domain missing 'entities' field")
                elif not isinstance(domain["entities"], list):
                    errors.append("Domain entities should be a list")
                else:
                    # Validate each entity
                    for i, entity in enumerate(domain["entities"]):
                        if not isinstance(entity, dict):
                            errors.append(f"Entity {i} is not a dict")
                            continue
                        if "name" not in entity:
                            errors.append(f"Entity {i} missing 'name' field")
                        if "fields" not in entity:
                            errors.append(f"Entity {i} missing 'fields' field")

            # Validate surfaces (at top level, not in domain)
            if "surfaces" in appspec:
                if not isinstance(appspec["surfaces"], list):
                    errors.append("surfaces should be a list")
                else:
                    # Validate each surface
                    for i, surface in enumerate(appspec["surfaces"]):
                        if not isinstance(surface, dict):
                            errors.append(f"Surface {i} is not a dict")
                            continue
                        if "name" not in surface:
                            errors.append(f"Surface {i} missing 'name' field")
                        if "entity_ref" not in surface:
                            errors.append(f"Surface {i} missing 'entity_ref' field")
                        if "mode" not in surface:
                            errors.append(f"Surface {i} missing 'mode' field")

            return len(errors) == 0, errors

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in AppSpec: {e}")
            return False, errors
        except Exception as e:
            errors.append(f"AppSpec validation error: {e}")
            return False, errors

    def validate_example(self, example_path: Path) -> BuildResult:
        """Validate a single example"""
        start_time = time.time()
        
        example_name = example_path.name
        all_errors = []
        all_warnings = []

        print(f"\n{'='*60}")
        print(f"Validating: {example_name}")
        print(f"{'='*60}")

        # Step 1: Validate DSL (using CLI for quick check)
        print("→ Validating DSL files...")
        dsl_valid, dsl_errors = self.validate_dsl(example_path)
        if not dsl_valid:
            all_errors.extend(dsl_errors)
            print(f"  ✗ DSL validation failed")
            for error in dsl_errors[:3]:  # Limit error output
                print(f"    ERROR: {error}")
            if len(dsl_errors) > 3:
                print(f"    ... and {len(dsl_errors) - 3} more errors")
            return BuildResult(
                example_name=example_name,
                validation_passed=False,
                build_passed=False,
                errors=all_errors,
                warnings=all_warnings,
                build_time=time.time() - start_time,
                appspec_path=None
            )
        print(f"  ✓ DSL validation passed")

        # Step 2: Build AppSpec (using Python API)
        print("→ Building AppSpec...")
        build_success, appspec_path, build_errors, entity_count, surface_count = \
            self.build_appspec_python(example_path)
        
        if not build_success:
            all_errors.extend(build_errors)
            print(f"  ✗ AppSpec build failed")
            for error in build_errors[:3]:  # Limit error output
                # Only print first line of each error
                first_line = error.split('\n')[0]
                print(f"    ERROR: {first_line}")
            if len(build_errors) > 3:
                print(f"    ... and {len(build_errors) - 3} more errors")
            return BuildResult(
                example_name=example_name,
                validation_passed=True,
                build_passed=False,
                errors=all_errors,
                warnings=all_warnings,
                build_time=time.time() - start_time,
                appspec_path=None
            )
        print(f"  ✓ AppSpec built: {appspec_path.relative_to(example_path)}")
        print(f"    Entities: {entity_count}")
        print(f"    Surfaces: {surface_count}")

        # Step 3: Validate AppSpec structure
        print("→ Validating AppSpec structure...")
        appspec_valid, appspec_errors = self.validate_appspec(appspec_path, example_name)
        
        if not appspec_valid:
            all_errors.extend(appspec_errors)
            print(f"  ✗ AppSpec validation failed")
            for error in appspec_errors[:3]:
                print(f"    ERROR: {error}")
            if len(appspec_errors) > 3:
                print(f"    ... and {len(appspec_errors) - 3} more errors")
        else:
            print(f"  ✓ AppSpec structure valid")

        build_time = time.time() - start_time
        success = dsl_valid and build_success and appspec_valid
        status_icon = "✓" if success else "✗"
        print(f"\n{status_icon} Completed in {build_time:.2f}s")

        return BuildResult(
            example_name=example_name,
            validation_passed=dsl_valid,
            build_passed=success,
            errors=all_errors,
            warnings=all_warnings,
            build_time=build_time,
            appspec_path=str(appspec_path) if appspec_path else None,
            entity_count=entity_count,
            surface_count=surface_count
        )

    def run_all(self) -> List[BuildResult]:
        """Validate all examples"""
        examples = self.discover_examples()
        
        if not examples:
            print(f"No examples found in {self.examples_dir}")
            return []
            
        print(f"Found {len(examples)} example(s) to validate")

        for example_path in examples:
            result = self.validate_example(example_path)
            self.results.append(result)

        return self.results

    def generate_report(self, format: str = "text") -> str:
        """Generate validation report"""
        if format == "json":
            return self._generate_json_report()
        else:
            return self._generate_text_report()

    def _generate_text_report(self) -> str:
        """Generate human-readable text report"""
        report = []
        report.append("\n" + "="*60)
        report.append("DAZZLE EXAMPLE BUILD VALIDATION REPORT")
        report.append("="*60 + "\n")

        if not self.results:
            report.append("No examples were validated.")
            return "\n".join(report)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.build_passed)
        failed = total - passed

        report.append(f"Total Examples: {total}")
        report.append(f"Passed: {passed}")
        report.append(f"Failed: {failed}")
        report.append(f"Success Rate: {passed/total*100:.1f}%\n")

        # Summary table
        report.append(f"{'Example':<30} {'Status':<10} {'Entities':<10} {'Surfaces':<10} {'Time':<10}")
        report.append("-" * 70)
        
        for result in self.results:
            status = "✓ PASS" if result.build_passed else "✗ FAIL"
            entities = str(result.entity_count) if result.build_passed else "-"
            surfaces = str(result.surface_count) if result.build_passed else "-"
            report.append(
                f"{result.example_name:<30} {status:<10} {entities:<10} {surfaces:<10} {result.build_time:.2f}s"
            )

        # Detailed errors
        if failed > 0:
            report.append("\n" + "="*60)
            report.append("DETAILED ERRORS")
            report.append("="*60 + "\n")
            
            for result in self.results:
                if not result.build_passed:
                    report.append(f"❌ {result.example_name}:")
                    for error in result.errors[:3]:  # Limit to 3 errors
                        # Only show first line of each error
                        first_line = error.split('\n')[0]
                        report.append(f"   {first_line}")
                    if len(result.errors) > 3:
                        report.append(f"   ... and {len(result.errors) - 3} more errors")
                    report.append("")

        report.append("\n" + "="*60)
        return "\n".join(report)

    def _generate_json_report(self) -> str:
        """Generate machine-readable JSON report"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.build_passed)
        
        report = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "success_rate": (passed / total * 100) if total > 0 else 0,
            "results": [asdict(r) for r in self.results]
        }
        return json.dumps(report, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate DAZZLE example builds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate all examples
  %(prog)s

  # Validate specific example
  %(prog)s --example support_tickets

  # Generate JSON report
  %(prog)s --report-format json

  # Specify custom examples directory
  %(prog)s --examples-dir /path/to/examples
        """
    )
    
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=None,
        help="Path to examples directory (default: auto-detect from script location)"
    )
    parser.add_argument(
        "--example",
        type=str,
        help="Validate specific example only"
    )
    parser.add_argument(
        "--report-format",
        choices=["text", "json"],
        default="text",
        help="Report output format (default: text)"
    )

    args = parser.parse_args()

    # Auto-detect examples directory if not specified
    if args.examples_dir is None:
        # Assume script is in tests/build_validation/
        script_dir = Path(__file__).parent
        repo_root = script_dir.parent.parent
        args.examples_dir = repo_root / "examples"

    if not args.examples_dir.exists():
        print(f"Error: Examples directory not found: {args.examples_dir}")
        return 1

    validator = ExampleValidator(args.examples_dir)

    if args.example:
        # Validate single example
        example_path = args.examples_dir / args.example
        if not example_path.exists():
            print(f"Error: Example not found: {example_path}")
            return 1
        if not (example_path / "dazzle.toml").exists():
            print(f"Error: Not a DAZZLE project (no dazzle.toml): {example_path}")
            return 1
        result = validator.validate_example(example_path)
        validator.results.append(result)
    else:
        # Validate all examples
        validator.run_all()

    # Generate and print report
    report = validator.generate_report(args.report_format)
    print(report)

    # Exit with error if any builds failed
    failed = sum(1 for r in validator.results if not r.build_passed)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
