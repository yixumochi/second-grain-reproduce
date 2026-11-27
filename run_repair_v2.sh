#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f .runtime/vision_python ]]; then
  echo 'Existing pilot environment pointer missing: .runtime/vision_python. Stop; do not rerun setup.'
  exit 2
fi
REPAIR_PY="$(cat .runtime/vision_python)"
if [[ ! -x "$REPAIR_PY" ]]; then echo "Existing Python unavailable: $REPAIR_PY"; exit 2; fi
mkdir -p logs
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Keep the venv path exactly as recorded. Do not readlink/resolve this binary.
"$REPAIR_PY" -B -u pilot-repair-v2/run.py "$@" 2>&1 | tee "logs/pilot_repair_v2_$(date -u +%Y%m%dT%H%M%SZ).log"
