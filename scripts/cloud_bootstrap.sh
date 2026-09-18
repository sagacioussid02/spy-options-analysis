#!/usr/bin/env bash
# Idempotent environment bootstrap for scheduled cloud runs (and a fresh clone).
# Usage: scripts/cloud_bootstrap.sh   (from anywhere; cd's to the repo root)
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt
.venv/bin/python - <<'EOF'
import sys, importlib
mods = ["anthropic", "mcp", "langgraph", "psycopg", "yfinance", "pandas", "numpy"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(f"bootstrap ok  python={sys.version.split()[0]}  missing={missing or 'none'}")
sys.exit(1 if missing else 0)
EOF
