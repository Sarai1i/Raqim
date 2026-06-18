"""Tests for the Kawn Baseer OCR API client."""

from __future__ import annotations

import io
import sys
import types
from unittest.mock import MagicMock, patch

# Stub heavy OCR deps before importing kawn_ocr in isolation.
if "requests" not in sys.modules:
    pass

import kawn_ocr


def test_upload_requires_api_key(monkeypatch):
    monkeypatch.setattr(kawn_ocr, "KAWN_API_KEY", "")
    try:
        kawn_ocr.upload_file(__file__)
        raise AssertionError("expected KawnOCRError")
    except kawn_ocr.KawnOCRError as exc:
        assert "KAWN_API_KEY" in str(exc)


def test_process_file_happy_path(monkeypatch, tmp_path):
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"png")

    monkeypatch.setattr(kawn_ocr, "KAWN_API_KEY", "test-key")
    monkeypatch.setattr(kawn_ocr, "KAWN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(kawn_ocr, "KAWN_POLL_TIMEOUT_SECONDS", 5)

    responses = [
        types.SimpleNamespace(status_code=202, json=lambda: {"fileId": "file-123"}),
        types.SimpleNamespace(status_code=200, json=lambda: {"status": "processing"}),
        types.SimpleNamespace(status_code=200, json=lambda: {"status": "completed"}),
        types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "fileId": "file-123",
                "model": "baseer/baseer-v2",
                "pages": [{"index": 0, "content": "<p>نص تجريبي</p>"}],
                "creditsConsumed": 1,
            },
        ),
    ]

    with patch("kawn_ocr.requests.post", return_value=responses[0]) as post_mock:
        with patch("kawn_ocr.requests.get", side_effect=responses[1:]) as get_mock:
            result = kawn_ocr.process_file(sample)

    assert result["model"] == "baseer/baseer-v2"
    assert result["pages"][0]["content"] == "<p>نص تجريبي</p>"
    assert post_mock.called
    assert get_mock.call_count == 3


def test_process_file_failed_status(monkeypatch, tmp_path):
    sample = tmp_path / "doc.png"
    sample.write_bytes(b"png")

    monkeypatch.setattr(kawn_ocr, "KAWN_API_KEY", "test-key")
    monkeypatch.setattr(kawn_ocr, "KAWN_POLL_INTERVAL_SECONDS", 0)

    with patch("kawn_ocr.requests.post", return_value=types.SimpleNamespace(status_code=202, json=lambda: {"fileId": "x"})):
        with patch(
            "kawn_ocr.requests.get",
            return_value=types.SimpleNamespace(status_code=200, json=lambda: {"status": "failed"}),
        ):
            try:
                kawn_ocr.process_file(sample)
                raise AssertionError("expected KawnOCRError")
            except kawn_ocr.KawnOCRError as exc:
                assert "فشلت معالجة" in str(exc)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    class _MonkeyPatch:
        def setattr(self, target, name, value):
            setattr(target, name, value)

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as tmp:
        test_upload_requires_api_key(mp)
        test_process_file_happy_path(mp, Path(tmp))
        test_process_file_failed_status(mp, Path(tmp))
    print("ok")
