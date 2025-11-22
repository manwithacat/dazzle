#!/bin/bash
cd "$(dirname "$0")"
npx tsc -p ./ 2>&1 | tee /tmp/vscode-build-output.txt
echo "Build output saved to /tmp/vscode-build-output.txt"
cat /tmp/vscode-build-output.txt
