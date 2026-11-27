#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f .runtime/vision_python ]]; then timber_python="$(cat .runtime/vision_python)"; else timber_python="$PWD/.envs/vision_gpu/bin/python"; fi
exec "$timber_python" -B -u watch_queue_09_16.py "$@"
