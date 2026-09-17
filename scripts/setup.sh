#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
npm ci
npm --prefix apps/web ci
npm --prefix apps/web run build
printf '\n启动：.venv/bin/python scripts/manage.py start\n'
