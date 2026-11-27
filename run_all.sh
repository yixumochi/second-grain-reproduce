#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ " $* " != *" --manifest "* && " $* " != *" --manifest="* ]]; then
  echo "Usage: bash run_all.sh --manifest path/to/all_manifest.json"
  echo "The repository does not include the 762-listing manifest. Pass the local file explicitly."
  exit 2
fi
mkdir -p logs
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
bash scripts/python.sh -u scripts/run_batch.py --all "$@" 2>&1 | tee "logs/batch_$STAMP.log"
