#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/python.sh -u scripts/run_batch.py --ids 117692 120235 111575 "$@"
