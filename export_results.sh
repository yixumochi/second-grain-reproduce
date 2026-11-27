#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/python.sh scripts/export_results.py "$@"
