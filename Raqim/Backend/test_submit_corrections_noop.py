import sys
import types

ocr_stub = types.ModuleType("ocr_model")
ocr_stub.configure_tesseract = lambda *_args, **_kwargs: None
ocr_stub.ocr_with_highlighting = lambda *_args, **_kwargs: []
ocr_stub.DeepSeekOCRError = RuntimeError
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

from app import app

payload = {
    "filename": "manual-test.txt",
    "corrections": [
        {
            "page_number": 1,
            "text": [
                {"index": 0, "word": "كلمة", "corrected_word": "كلمة"},
                {"index": 1, "word": "سليمة", "corrected_word": ""},
            ],
        }
    ],
}

with app.test_client() as client:
    response = client.post("/submit_corrections", json=payload)
    print("status_code=", response.status_code)
    print("json=", response.get_json())
    assert response.status_code == 200
    assert response.get_json()["inserted_count"] == 0
