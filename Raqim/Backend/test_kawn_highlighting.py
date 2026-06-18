"""Tests for Kawn OCR integration in ocr_model."""

from __future__ import annotations

import os
from unittest.mock import patch

from PIL import Image

import ocr_model


def test_get_active_ocr_provider_defaults_to_deepseek(monkeypatch):
    monkeypatch.delenv("OCR_PROVIDER", raising=False)
    monkeypatch.setattr(ocr_model, "OCR_PROVIDER", "deepseek")
    assert ocr_model.get_active_ocr_provider() == "deepseek"


def test_get_active_ocr_provider_kawn(monkeypatch):
    monkeypatch.setattr(ocr_model, "OCR_PROVIDER", "kawn")
    assert ocr_model.get_active_ocr_provider() == "kawn"


def test_kawn_highlighting_builds_review_words(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (400, 300), color=(255, 255, 255)).save(image_path)
    output_folder = tmp_path / "uploads"
    output_folder.mkdir()

    fake_result = {
        "model": "baseer/baseer-v2",
        "creditsConsumed": 1,
        "pages": [{"index": 0, "content": "<p>مرحبا بالعالم</p>"}],
    }

    with patch("ocr_model.kawn_process_file", return_value=fake_result):
        pages = ocr_model._ocr_with_kawn_highlighting(image_path, output_folder)

    assert len(pages) == 1
    assert pages[0]["ocr_engine"] == "kawn"
    assert pages[0]["ocr_provider"] == "kawn_api"
    assert any(word["word"] == "مرحبا" for word in pages[0]["text"])
    assert (output_folder / "original_page_1.png").exists()


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    class _MonkeyPatch:
        def setattr(self, target, name, value):
            setattr(target, name, value)

        def delenv(self, name, raising=False):
            os.environ.pop(name, None)

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as tmp:
        test_get_active_ocr_provider_defaults_to_deepseek(mp)
        test_get_active_ocr_provider_kawn(mp)
        test_kawn_highlighting_builds_review_words(Path(tmp), mp)
    print("ok")
