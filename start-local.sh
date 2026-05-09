#!/usr/bin/env bash
# Start Claudia with a local LM Studio model instead of Anthropic's API.
#
# Prerequisites:
#   - LM Studio installed and running (lms server start)
#   - A model loaded in LM Studio
#
# Usage:
#   ./start-local.sh
#   ./start-local.sh qwen2.5-coder-32b-instruct
#   PORT=1234 ./start-local.sh qwen2.5-coder-32b-instruct

PORT="${PORT:-1234}"

export ANTHROPIC_BASE_URL="http://localhost:${PORT}"
export ANTHROPIC_API_KEY=""
export ANTHROPIC_AUTH_TOKEN="lm-studio"

echo "Claudia -> LM Studio (http://localhost:${PORT})"

if [ -n "$1" ]; then
    claude --model "$1"
else
    claude
fi
