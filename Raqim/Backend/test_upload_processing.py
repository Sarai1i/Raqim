import io
import sys
import time
import types

from PIL import Image

ocr_stub = types.ModuleType("ocr_model")


class _FakeDeepSeekOCRError(RuntimeError):
    pass


def _fake_ocr_success(_file_path, _output_folder):
    return [
        {
            "page_number": 1,
            "image_path": "uploads/original_page_1.png",
            "text": [
                {
                    "index": 0,
                    "word": "فهرس",
                    "original_word": "فهرس",
                    "corrected_word": "",
                    "confidence": 95,
                    "highlighted": False,
                    "wasHighlighted": False,
                    "corrected": False,
                    "bounding_box": {
                        "x": 10,
                        "y": 10,
                        "w": 50,
                        "h": 20,
                        "original_width": 100,
                        "original_height": 100,
                    },
                }
            ],
            "ocr_engine": "deepseek",
            "ocr_engine_label": "DeepSeek-OCR-2 (test)",
            "ocr_provider": "deepseek_local",
        }
    ]


ocr_stub.ocr_with_highlighting = _fake_ocr_success
ocr_stub.DeepSeekOCRError = _FakeDeepSeekOCRError
sys.modules["ocr_model"] = ocr_stub

try:
    import google.generativeai  # noqa: F401
except Exception:
    google_module = types.ModuleType("google")
    genai_stub = types.ModuleType("google.generativeai")
    genai_stub.configure = lambda *_args, **_kwargs: None

    class _DummyGenerativeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate_content(self, *_args, **_kwargs):
            return types.SimpleNamespace(text="")

    genai_stub.GenerativeModel = _DummyGenerativeModel
    genai_stub.types = types.SimpleNamespace(GenerationConfig=lambda **kwargs: kwargs)
    google_module.generativeai = genai_stub
    sys.modules["google"] = google_module
    sys.modules["google.generativeai"] = genai_stub

import app as app_module
from app import app


def _reset_processing_state():
    app_module.processing_complete = False
    app_module.processing_failed = False
    app_module.processing_error = ""
    app_module.ocr_results = []
    app_module.ocr_engine_status = {
        "engine": "pending",
        "label": "بانتظار المعالجة",
        "provider": "deepseek_local",
    }


def _make_png_upload():
    image = Image.new("RGB", (640, 480), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _wait_for_terminal_status(client, timeout_seconds=5.0):
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        response = client.get("/processing_status")
        assert response.status_code != 503
        last_payload = response.get_json()
        if last_payload["status"] in {"done", "failed"}:
            return response.status_code, last_payload
        time.sleep(0.05)
    raise AssertionError(f"processing did not finish in time; last={last_payload}")


def test_upload_processing_status_not_503():
    _reset_processing_state()
    app_module.ocr_with_highlighting = _fake_ocr_success

    with app.test_client() as client:
        upload_response = client.post(
            "/upload",
            data={"file": (_make_png_upload(), "TOC.png")},
            content_type="multipart/form-data",
        )
        assert upload_response.status_code == 200

        status_code, payload = _wait_for_terminal_status(client)
        assert status_code == 200
        assert payload["status"] == "done"
        assert payload["ocr_engine"]["engine"] == "deepseek"


def test_processing_status_failed_returns_200_not_503():
    _reset_processing_state()

    def _raise_deepseek_error(*_args, **_kwargs):
        raise _FakeDeepSeekOCRError(
            "فشل DeepSeek-OCR-2 بسبب إعدادات صورة غير مدعومة (param_img)."
        )

    app_module.ocr_with_highlighting = _raise_deepseek_error

    with app.test_client() as client:
        upload_response = client.post(
            "/upload",
            data={"file": (_make_png_upload(), "TOC.png")},
            content_type="multipart/form-data",
        )
        assert upload_response.status_code == 200

        status_code, payload = _wait_for_terminal_status(client)
        assert status_code == 200
        assert payload["status"] == "failed"
        assert "DeepSeek-OCR-2" in payload["error"]
        assert "Tesseract" not in payload["error"]


if __name__ == "__main__":
    test_upload_processing_status_not_503()
    test_processing_status_failed_returns_200_not_503()
    print("ok")
