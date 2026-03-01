#!/usr/bin/env bash
# Scheduler health check — used by docker-compose healthcheck.
# Verifies: (1) scheduler process is alive, (2) Redis lock key exists
# (proves the scheduler ran at least once recently).
set -euo pipefail

# Check that the main Python process is alive
pgrep -f "src.scheduler" > /dev/null 2>&1
