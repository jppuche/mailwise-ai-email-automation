#!/usr/bin/env bash
# Celery worker health check — used by docker-compose healthcheck.
# Pings the worker via celery inspect and checks for a pong response.
set -euo pipefail

celery -A src.tasks.celery_app inspect ping -d "celery@${HOSTNAME}" 2>/dev/null | grep -q "pong"
