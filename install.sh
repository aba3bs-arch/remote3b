#!/bin/bash
set -euo pipefail

echo "== AM-Connect setup =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required"
  exit 1
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env. Edit SECRET_KEY before production use."
fi

echo
echo "Start the server:"
echo "  source venv/bin/activate"
echo "  python server/main.py"
echo
echo "Open the dashboard:"
echo "  http://localhost:8000"
