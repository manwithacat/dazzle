#!/usr/bin/env bash
# Verify PyPI wheel URLs are valid (checks that URLs exist)

set -e

for file in "$@"; do
    urls=$(grep -oE 'https://files.pythonhosted.org/[^"]+\.whl' "$file" 2>/dev/null || true)
    for url in $urls; do
        echo "Checking $url..."
        if ! curl -sIf "$url" > /dev/null; then
            echo "ERROR: Invalid URL: $url"
            exit 1
        fi
    done
done
