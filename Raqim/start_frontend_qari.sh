#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/Raqim/my-app

export REACT_APP_API_BASE_URL="${REACT_APP_API_BASE_URL:-https://5000-im9qnwfwo18v9xqv1pp1y-d1b986e7.sg1.manus.computer}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-3000}"
export BROWSER=none
export DISABLE_ESLINT_PLUGIN="${DISABLE_ESLINT_PLUGIN:-true}"

exec npm start
