#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f .runtime/vision_python ]]; then
  timber_python="$(cat .runtime/vision_python)"
else
  timber_python="$PWD/.envs/vision_gpu/bin/python"
fi
if [[ ! -x "$timber_python" ]]; then echo "Existing Python environment missing; no setup attempted."; exit 2; fi
"$timber_python" -B -u queue_09_16.py --prepare
mkdir -p logs
timber_queue_log="$PWD/logs/queue_09_16_$(date -u +%Y%m%dT%H%M%S)_$$.log"
nohup "$timber_python" -B -u queue_09_16.py > "$timber_queue_log" 2>&1 < /dev/null &
timber_queue_pid=$!
printf 'Background queue PID: %s\nLOG: %s\n' "$timber_queue_pid" "$timber_queue_log"
printf 'Batches 09-16 only. Wait for START batch in the log before leaving. Stops after batch 16.\n'
printf 'Auto-follow current batch: bash watch_queue_09_16.sh\n'
