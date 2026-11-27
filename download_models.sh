#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# These are model weights only. No seller images are fetched.
bash scripts/python.sh scripts/download_models.py --accept-downloads
# DeepLSD is optional: one bounded download; existing verified weight is reused.
bash scripts/python.sh scripts/download_deeplsd.py || echo 'DeepLSD unavailable; recorded OpenCV LSD fallback remains enabled.'
