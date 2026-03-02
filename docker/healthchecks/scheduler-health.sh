#!/bin/sh
# Scheduler health check — used by docker-compose healthcheck.
# Verifies the main Python process (PID 1) is alive and is the scheduler.
# Uses /proc filesystem instead of pgrep (not available in python:3.12-slim).
set -e

# PID 1 is the scheduler process in the container
test -f /proc/1/cmdline && grep -qa "src.scheduler" /proc/1/cmdline
