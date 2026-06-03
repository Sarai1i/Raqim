#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/Raqim/Backend
mkdir -p logs
if [ -f /home/ubuntu/Raqim/Backend/.env ]; then
  set -a; source /home/ubuntu/Raqim/Backend/.env; set +a
fi

# رقيم يعمل الآن على Tesseract المحلي بدل Qari، مع تفعيل العربية والإنجليزية.
export QARI_OCR_ENABLED=false
export QARI_OCR_FALLBACK_TO_TESSERACT=false
export OCR_TESSERACT_LANG="ara+eng"
export OCR_TESSERACT_CONFIG="--oem 3 --psm 6"
export PYTHONUNBUFFERED=1
export FLASK_DEBUG=false

# طبقة اقتراحات التصحيح بالذكاء الاصطناعي. لا تغيّر OCR ولا تطبق التصحيح تلقائيًا.
export LLM_SUGGESTIONS_ENABLED="${LLM_SUGGESTIONS_ENABLED:-false}"
export LLM_SUGGESTIONS_API_BASE_URL="${LLM_SUGGESTIONS_API_BASE_URL:-${OPENAI_API_BASE:-}}"
export LLM_SUGGESTIONS_API_KEY="${LLM_SUGGESTIONS_API_KEY:-${OPENAI_API_KEY:-}}"
export LLM_SUGGESTIONS_MODEL_NAME="${LLM_SUGGESTIONS_MODEL_NAME:-gpt-5-nano}"
export LLM_SUGGESTIONS_TIMEOUT_SECONDS="${LLM_SUGGESTIONS_TIMEOUT_SECONDS:-20}"

exec python3 app.py
