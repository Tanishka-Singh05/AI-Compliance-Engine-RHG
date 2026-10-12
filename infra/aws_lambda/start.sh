#!/bin/bash
set -euo pipefail

# Optional entrypoint: start OPA in the background, then exec the container CMD.
# The scan Lambda uses `ace.lambda_handler.handler`, which starts OPA in-process
# (see services/ace/lambda_handler.py); this script is kept for the alternative
# `start.sh`-driven entrypoint.
/usr/local/bin/opa run --server \
  --addr=localhost:8181 \
  --bundle=./ace/policies \
  &
exec "$@"
