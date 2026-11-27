#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $# -lt 1 ]]; then echo "Usage: bash run_batch_v31.sh 01 --repair-first | 01 --light-only | 02"; exit 2; fi
if [[ -f .runtime/vision_python ]]; then timber_python="$(cat .runtime/vision_python)"; else timber_python="$PWD/.envs/vision_gpu/bin/python"; fi
if [[ ! -x "$timber_python" ]]; then echo "Verified vision environment missing. No setup/download was attempted."; exit 2; fi
export PYTHONDONTWRITEBYTECODE=1
exec "$timber_python" -B -u batch-evidence-v3/maintenance/run_v31.py "$@"
