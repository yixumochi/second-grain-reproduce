#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
bash scripts/python.sh -u scripts/run_batch.py --all "$@" 2>&1 | tee "logs/batch_$STAMP.log"
