#!/usr/bin/env bash
# Thin wrapper — delegates to launch.py (interactive Python launcher).
# Usage: ./start-local.sh [--port 1234]
python3 "$(dirname "$0")/launch.py" "$@"
