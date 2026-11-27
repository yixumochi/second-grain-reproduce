#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $# -lt 1 ]]; then echo "Usage: bash run_batch_v3.sh 01 [--retry-failed | --pages-only]"; exit 2; fi
if [[ -f .runtime/vision_python ]]; then
  timber_python="$(cat .runtime/vision_python)"
else
  timber_python="$PWD/.envs/vision_gpu/bin/python"
fi
if [[ ! -x "$timber_python" ]]; then echo "Existing verified vision environment not found: $timber_python. No setup was restarted."; exit 2; fi
export PYTHONDONTWRITEBYTECODE=1
exec "$timber_python" -B -u batch-evidence-v3/run.py "$@"
