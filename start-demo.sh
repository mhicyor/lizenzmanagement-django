#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
unset DEMO_READ_ONLY
python manage.py migrate --no-input
python -m demo.seed
export DEMO_READ_ONLY=1
exec gunicorn lizenz_web.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 60 --access-logfile -
