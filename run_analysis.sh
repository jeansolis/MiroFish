#!/bin/bash
# MiroFish Stock Analysis Runner
# Usage: ./run_analysis.sh TICKER [ROUNDS]
# Example: ./run_analysis.sh ASST 20

# ─── Configuration ───────────────────────────────────────────────────────
export OPENROUTER_API_KEY="YOUR_OPENROUTER_KEY_HERE"
export MIROFISH_PASSWORD="YOUR_APP_PASSWORD_HERE"
export MIROFISH_URL="https://miro-fish-miro-fish-app.03ledn.easypanel.host"

# ─── Run ─────────────────────────────────────────────────────────────────
TICKER=${1:-ASST}
ROUNDS=${2:-20}

echo "Analyzing $TICKER with $ROUNDS rounds..."

pip install requests -q 2>/dev/null

python stock_pipeline.py "$TICKER" \
  --rounds "$ROUNDS" \
  --mirofish-url "$MIROFISH_URL"
