# MiroFish Stock Analysis Runner
# Usage: .\run_analysis.ps1 ASST 20

param(
    [string]$Ticker = "ASST",
    [int]$Rounds = 20
)

# ─── Configuration ───────────────────────────────────────────────────────
$env:OPENROUTER_API_KEY = "YOUR_OPENROUTER_KEY_HERE"
$env:MIROFISH_PASSWORD  = "YOUR_APP_PASSWORD_HERE"
$env:MIROFISH_URL       = "https://miro-fish-miro-fish-app.03ledn.easypanel.host"

# ─── Run ─────────────────────────────────────────────────────────────────
Write-Host "Analyzing $Ticker with $Rounds rounds..."

pip install requests -q 2>$null

python stock_pipeline.py $Ticker `
  --rounds $Rounds `
  --mirofish-url $env:MIROFISH_URL
