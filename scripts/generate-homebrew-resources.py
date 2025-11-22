#!/usr/bin/env python3
"""
Generate Homebrew formula resources from pyproject.toml dependencies.

This script:
1. Reads dependencies from pyproject.toml
2. Downloads packages from PyPI
3. Calculates SHA256 checksums
4. Generates Homebrew resource blocks
"""

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path


def get_package_info(package_name, version=None):
    """Get package info from PyPI."""
    url = f"https://pypi.org/pypi/{package_name}/json"

    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())

            if version:
                release = data['releases'].get(version)
                if not release:
                    print(f"Warning: Version {version} not found for {package_name}", file=sys.stderr)
                    return None
            else:
                # Get latest version
                version = data['info']['version']
                release = data['releases'][version]

            # Find source distribution (.tar.gz)
            for file_info in release:
                if file_info['packagetype'] == 'sdist' and file_info['filename'].endswith('.tar.gz'):
                    return {
                        'name': package_name,
                        'version': version,
                        'url': file_info['url'],
                        'sha256': file_info['digests']['sha256'],
                        'filename': file_info['filename']
                    }

            print(f"Warning: No source distribution found for {package_name} {version}", file=sys.stderr)
            return None

    except Exception as e:
        print(f"Error fetching {package_name}: {e}", file=sys.stderr)
        return None


def parse_dependency(dep_string):
    """Parse dependency string like 'package>=1.0.0' into (name, version)."""
    # Remove extras like [dev]
    dep_string = re.sub(r'\[.*?\]', '', dep_string)

    # Extract package name and version spec
    match = re.match(r'([a-zA-Z0-9_-]+)([><=!~]=?.*)?', dep_string.strip())
    if match:
        package_name = match.group(1)
        version_spec = match.group(2)

        # For Homebrew, we want exact versions
        # If version specified, try to extract it
        version = None
        if version_spec:
            # Try to extract version number
            version_match = re.search(r'(\d+\.\d+\.\d+)', version_spec)
            if version_match:
                version = version_match.group(1)

        return package_name, version

    return None, None


def generate_resource_block(info):
    """Generate Homebrew resource block."""
    if not info:
        return ""

    # Convert package name to formula-safe name
    safe_name = info['name'].replace('-', '_').replace('.', '_')

    return f'''  resource "{info['name']}" do
    url "{info['url']}"
    sha256 "{info['sha256']}"
  end
'''


def main():
    # Read pyproject.toml
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / 'pyproject.toml'

    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} not found", file=sys.stderr)
        sys.exit(1)

    print("Reading dependencies from pyproject.toml...")

    # Simple TOML parsing for dependencies
    dependencies = []
    with open(pyproject_path) as f:
        in_dependencies = False
        for line in f:
            line = line.strip()

            if line.startswith('dependencies = ['):
                in_dependencies = True
                continue

            if in_dependencies:
                if line == ']':
                    break

                # Extract dependency from quoted string
                match = re.search(r'"([^"]+)"', line)
                if match:
                    dependencies.append(match.group(1))

    print(f"Found {len(dependencies)} dependencies\n")

    # Generate resources
    print("Fetching package info from PyPI...\n")
    resources = []

    for dep in dependencies:
        package_name, version = parse_dependency(dep)
        if not package_name:
            continue

        print(f"Processing {package_name}...", end=' ')
        info = get_package_info(package_name, version)

        if info:
            print(f"✓ {info['version']} ({info['sha256'][:8]}...)")
            resources.append(info)
        else:
            print("✗ Failed")

    print(f"\nGenerated {len(resources)} resource blocks\n")
    print("=" * 70)
    print("Add these to homebrew/dazzle.rb:")
    print("=" * 70)
    print()

    for info in resources:
        print(generate_resource_block(info))

    print("=" * 70)
    print(f"\nDone! Generated {len(resources)}/{len(dependencies)} resources")


if __name__ == '__main__':
    main()
