# Start Claudia with a local LM Studio model instead of Anthropic's API.
#
# Prerequisites:
#   - LM Studio installed and running (lms server start)
#   - A model loaded in LM Studio
#
# Usage:
#   .\start-local.ps1
#   .\start-local.ps1 -Model "qwen2.5-coder-32b-instruct"
#   .\start-local.ps1 -Port 1234 -Model "qwen2.5-coder-32b-instruct"

param(
    [string]$Model = "",
    [int]$Port = 1234
)

$env:ANTHROPIC_BASE_URL   = "http://localhost:$Port"
$env:ANTHROPIC_API_KEY    = ""
$env:ANTHROPIC_AUTH_TOKEN = "lm-studio"

Write-Host "Claudia -> LM Studio (http://localhost:$Port)" -ForegroundColor Cyan

if ($Model -ne "") {
    claude --model $Model
} else {
    claude
}
