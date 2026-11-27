#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $# -ne 1 ]]; then echo "Usage: bash export_batch_v3.sh 01"; exit 2; fi
exec bash run_batch_v3.sh "$1" --export-only
