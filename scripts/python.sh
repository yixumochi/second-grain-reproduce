#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .runtime/vision_python ]]; then echo 'First run: bash setup.sh'; exit 2; fi
PY="$(cat .runtime/vision_python)"
exec "$PY" "$@"
