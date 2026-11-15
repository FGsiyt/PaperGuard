#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -c './requirements-lock.txt' -e './backend[test]'
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m paperguard init
printf '%s\n' 'Start: .venv/bin/python -m paperguard serve'
