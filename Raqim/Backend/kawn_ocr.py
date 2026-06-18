"""Kawn Baseer OCR API client for Raqim."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


class KawnOCRError(RuntimeError):
    """Raised when the Kawn Baseer OCR API fails."""


KAWN_API_BASE_URL = os.getenv("KAWN_API_BASE_URL", "https://api.kawn.ai").rstrip("/")
KAWN_API_KEY = os.getenv("KAWN_API_KEY", "").strip()
KAWN_OCR_MODEL = os.getenv("KAWN_OCR_MODEL", "baseer/baseer-v2")
KAWN_POLL_INTERVAL_SECONDS = float(os.getenv("KAWN_POLL_INTERVAL_SECONDS", "2"))
KAWN_POLL_TIMEOUT_SECONDS = float(os.getenv("KAWN_POLL_TIMEOUT_SECONDS", "600"))
KAWN_REQUEST_TIMEOUT_SECONDS = float(os.getenv("KAWN_REQUEST_TIMEOUT_SECONDS", "120"))


def _headers() -> Dict[str, str]:
    if not KAWN_API_KEY:
        raise KawnOCRError(
            "مفتاح Kawn API غير مضبوط. عيّن KAWN_API_KEY في ملف .env عند استخدام OCR_PROVIDER=kawn."
        )
    return {"x-api-key": KAWN_API_KEY}


def _format_api_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or payload
    except ValueError:
        detail = response.text.strip()
    detail_text = str(detail).strip() if detail else response.reason
    return f"خطأ من Kawn OCR (HTTP {response.status_code}): {detail_text}"


def upload_file(
    file_path: str | os.PathLike[str],
    model: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Upload a file and return the Kawn ``fileId``."""
    path = Path(file_path)
    if not path.is_file():
        raise KawnOCRError(f"الملف غير موجود: {path}")

    model_name = model or KAWN_OCR_MODEL
    data: Dict[str, str] = {"model": model_name}
    if options:
        data["options"] = json.dumps(options)

    url = f"{KAWN_API_BASE_URL}/v1/ocr"
    with path.open("rb") as handle:
        files = {"file": (path.name, handle)}
        try:
            response = requests.post(
                url,
                headers=_headers(),
                files=files,
                data=data,
                timeout=KAWN_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise KawnOCRError(f"تعذر الاتصال بـ Kawn OCR: {exc}") from exc

    if response.status_code != 202:
        raise KawnOCRError(_format_api_error(response))

    file_id = (response.json() or {}).get("fileId")
    if not file_id:
        raise KawnOCRError("استجابة Kawn OCR لا تحتوي على fileId.")
    return str(file_id)


def poll_status(file_id: str) -> str:
    """Return Kawn processing status: pending, processing, completed, or failed."""
    url = f"{KAWN_API_BASE_URL}/v1/ocr/{file_id}/status"
    try:
        response = requests.get(url, headers=_headers(), timeout=KAWN_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise KawnOCRError(f"تعذر التحقق من حالة Kawn OCR: {exc}") from exc

    if response.status_code != 200:
        raise KawnOCRError(_format_api_error(response))

    status = str((response.json() or {}).get("status") or "").strip().lower()
    if status not in {"pending", "processing", "completed", "failed"}:
        raise KawnOCRError(f"حالة Kawn OCR غير معروفة: {status or 'empty'}")
    return status


def fetch_results(file_id: str) -> Dict[str, Any]:
    """Fetch OCR results. Kawn deletes them after a successful response."""
    url = f"{KAWN_API_BASE_URL}/v1/ocr/{file_id}/results"
    try:
        response = requests.get(url, headers=_headers(), timeout=KAWN_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise KawnOCRError(f"تعذر جلب نتائج Kawn OCR: {exc}") from exc

    if response.status_code != 200:
        raise KawnOCRError(_format_api_error(response))
    return response.json() or {}


def process_file(file_path: str | os.PathLike[str]) -> Dict[str, Any]:
    """Upload, poll until complete, and fetch OCR results."""
    file_id = upload_file(file_path)
    print(f"☁️ Kawn OCR: uploaded {Path(file_path).name} → fileId={file_id}")

    deadline = time.time() + KAWN_POLL_TIMEOUT_SECONDS
    while True:
        status = poll_status(file_id)
        print(f"☁️ Kawn OCR status: {status}")
        if status == "completed":
            break
        if status == "failed":
            raise KawnOCRError("فشلت معالجة الملف على Kawn Baseer OCR.")
        if time.time() >= deadline:
            raise KawnOCRError(
                f"انتهت مهلة انتظار Kawn OCR ({int(KAWN_POLL_TIMEOUT_SECONDS)} ثانية)."
            )
        time.sleep(KAWN_POLL_INTERVAL_SECONDS)

    results = fetch_results(file_id)
    if not results.get("pages"):
        raise KawnOCRError("Kawn OCR أعاد استجابة بدون صفحات.")
    return results
