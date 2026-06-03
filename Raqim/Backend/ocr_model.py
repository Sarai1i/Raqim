"""OCR engine for Raqim with Qari OCR support.

This module keeps the interface expected by ``Backend/app.py``:

- ``configure_tesseract(tesseract_cmd)`` configures the Tesseract executable.
- ``ocr_with_highlighting(file_path, output_folder)`` converts PDF/image input into
  page images and returns OCR words with bounding boxes and confidence highlighting.

Tesseract OCR is the active OCR engine for Raqim. It is configured to use both
Arabic and English when the language packs are available, and it returns the
word-level bounding boxes and confidence values required by the existing Raqim
review workflow: yellow highlighting for low-confidence words and synchronized
word-to-box selection on the source document. Qari support is kept in this file
as an optional provider, but it is disabled by default.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List

from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
from pytesseract import Output


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_DPI = int(os.getenv("OCR_PDF_DPI", "220"))
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "80"))

# Qari settings are kept optional only. Raqim now defaults to Tesseract so user
# files are processed locally with Arabic+English language packs and without
# depending on the public Hugging Face ZeroGPU quota.
QARI_OCR_ENABLED = os.getenv("QARI_OCR_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
QARI_OCR_PROVIDER = os.getenv("QARI_OCR_PROVIDER", "space").strip().lower()
QARI_OCR_FALLBACK_TO_TESSERACT = os.getenv("QARI_OCR_FALLBACK_TO_TESSERACT", "false").lower() in {"1", "true", "yes", "on"}
QARI_SPACE_ID = os.getenv("QARI_SPACE_ID", "oddadmix/Arabic-OCR-Models-Demos")
QARI_SPACE_API_NAME = os.getenv("QARI_SPACE_API_NAME", "/perform_ocr")
QARI_SPACE_MODEL_CHOICE = os.getenv("QARI_SPACE_MODEL_CHOICE", "Qari OCR 0.2.2.1")
QARI_APPROX_CONFIDENCE = float(os.getenv("QARI_APPROX_CONFIDENCE", "95"))

# Documented model identifiers for deployments with enough GPU memory. The current
# implementation uses the Space/API path by default because local inference was too
# heavy for this demo machine. These variables are intentionally kept here so the
# engine can be configured consistently later.
QARI_LOCAL_MODEL_NAME = os.getenv("QARI_LOCAL_MODEL_NAME", "NAMAA-Space/Qari-OCR-v0.3-VL-2B-Instruct")
QARI_LATEST_MODEL_NAME = os.getenv("QARI_LATEST_MODEL_NAME", "NAMAA-Space/Qari-OCR-0.4.0-VL-4B-Instruct")


_GRADIO_CLIENT = None


def configure_tesseract(tesseract_cmd: str | None = None) -> None:
    """Configure the Tesseract executable used by the active OCR path."""

    candidate = tesseract_cmd or os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if candidate:
        pytesseract.pytesseract.tesseract_cmd = candidate


def _available_tesseract_languages() -> set[str]:
    try:
        langs = pytesseract.get_languages(config="")
        return set(langs or [])
    except Exception:
        return set()


def _preferred_language() -> str:
    configured_lang = os.getenv("OCR_TESSERACT_LANG", "").strip()
    if configured_lang:
        return configured_lang

    langs = _available_tesseract_languages()
    if {"ara", "eng"}.issubset(langs):
        return "ara+eng"
    if "ara" in langs:
        return "ara"
    if "eng" in langs:
        return "eng"
    return "eng"


def _prepare_output_folder(output_folder: str | os.PathLike[str]) -> Path:
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)

    for old_page in folder.glob("original_page_*.png"):
        try:
            old_page.unlink()
        except OSError:
            pass
    return folder


def _load_pages(file_path: str | os.PathLike[str]) -> List[Image.Image]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return [page.convert("RGB") for page in convert_from_path(str(path), dpi=DEFAULT_DPI)]

    if suffix in SUPPORTED_IMAGE_EXTENSIONS:
        with Image.open(path) as image:
            return [image.convert("RGB")]

    raise ValueError(f"Unsupported OCR file type: {suffix or 'unknown'}")


def _normalize_for_ocr(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return ImageOps.autocontrast(gray)


def _clean_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _clean_word(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _safe_confidence(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _word_item(word: str, confidence: float, x: int, y: int, w: int, h: int, width: int, height: int, index: int) -> Dict:
    highlighted = confidence < DEFAULT_CONFIDENCE_THRESHOLD if confidence >= 0 else True
    return {
        "index": index,
        "word": word,
        "original_word": word,
        "corrected_word": "",
        "confidence": round(confidence, 2) if confidence >= 0 else 0,
        "highlighted": highlighted,
        "wasHighlighted": highlighted,
        "corrected": False,
        "bounding_box": {
            "x": int(max(x, 0)),
            "y": int(max(y, 0)),
            "w": int(max(w, 1)),
            "h": int(max(h, 1)),
            "original_width": int(width),
            "original_height": int(height),
        },
    }


def _get_gradio_client():
    global _GRADIO_CLIENT
    if _GRADIO_CLIENT is None:
        from gradio_client import Client

        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if hf_token:
            _GRADIO_CLIENT = Client(QARI_SPACE_ID, token=hf_token)
        else:
            _GRADIO_CLIENT = Client(QARI_SPACE_ID)
    return _GRADIO_CLIENT


def _qari_space_text(image: Image.Image) -> str:
    """Extract Arabic page text through a Hugging Face Space running Qari OCR."""

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        temp_path = tmp.name
    try:
        image.convert("RGB").save(temp_path, format="PNG")
        from gradio_client import handle_file

        client = _get_gradio_client()
        output = client.predict(
            handle_file(temp_path),
            QARI_SPACE_MODEL_CHOICE,
            api_name=QARI_SPACE_API_NAME,
        )
        return _clean_text(output)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _qari_local_text(_image: Image.Image) -> str:
    """Placeholder for local Qari inference on GPU-capable deployments.

    The model identifiers are kept configurable above. For this sandbox demo, local
    inference repeatedly stalled because the 2B/4B VLM had to offload weights to CPU
    and disk. Raising here allows the automatic fallback policy to choose the stable
    Space path or Tesseract path instead of hanging the Flask worker.
    """

    raise RuntimeError(
        "Local Qari OCR inference is disabled in this constrained demo. "
        f"Use QARI_OCR_PROVIDER=space, or deploy {QARI_LOCAL_MODEL_NAME} / {QARI_LATEST_MODEL_NAME} on a GPU host."
    )


def _qari_page_text(image: Image.Image) -> str:
    if QARI_OCR_PROVIDER in {"space", "hf_space", "gradio"}:
        return _qari_space_text(image)
    if QARI_OCR_PROVIDER in {"local", "transformers"}:
        return _qari_local_text(image)
    if QARI_OCR_PROVIDER == "off":
        raise RuntimeError("Qari OCR is disabled by QARI_OCR_PROVIDER=off")
    raise RuntimeError(f"Unsupported Qari OCR provider: {QARI_OCR_PROVIDER}")


def _qari_words_from_text(text: str, width: int, height: int) -> List[Dict]:
    """Create approximate RTL word boxes for Qari's plain-text output.

    This is used only as a safe fallback. The preferred Qari review path below
    keeps Qari's text, but borrows word-level boxes and confidence values from
    the legacy Tesseract layout pass so the old Raqim review behavior remains:
    clicking a word points to the corresponding box on the page, and low
    confidence words remain yellow.
    """

    text = _clean_text(text)
    if not text:
        return []

    lines = text.split("\n")
    margin_x = max(18, width // 35)
    margin_y = max(18, height // 35)
    line_height = max(26, min(54, height // max(len(lines) + 3, 6)))
    char_width = max(8, min(18, width // 85))
    gap = max(6, width // 180)

    words: List[Dict] = []
    y = margin_y
    for line in lines:
        tokens = [token for token in line.split() if token]
        if not tokens:
            y += line_height
            continue

        x_cursor = width - margin_x
        for token in tokens:
            token_width = max(24, min(width - (2 * margin_x), len(token) * char_width + 12))
            if x_cursor - token_width < margin_x:
                y += line_height
                x_cursor = width - margin_x
            x = x_cursor - token_width
            words.append(
                _word_item(
                    word=token,
                    confidence=QARI_APPROX_CONFIDENCE,
                    x=x,
                    y=y,
                    w=token_width,
                    h=max(20, int(line_height * 0.78)),
                    width=width,
                    height=height,
                    index=len(words),
                )
            )
            x_cursor = x - gap
        y += line_height

    return words


def _normalize_token_for_alignment(token: str) -> str:
    """Normalize OCR tokens for loose Qari/Tesseract layout alignment."""

    token = str(token or "").strip().lower()
    token = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", token)
    token = token.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
    }))
    token = re.sub(r"[^\w\u0600-\u06ff]+", "", token)
    return token


def _sort_layout_words_for_arabic_reading_order(layout_words: List[Dict]) -> List[Dict]:
    """Sort OCR layout boxes by visual Arabic reading order: top-to-bottom, right-to-left."""

    indexed_words = []
    heights = []
    for original_index, word in enumerate(layout_words or []):
        bbox = word.get("bounding_box", {}) or {}
        y = int(bbox.get("y", 0) or 0)
        h = int(bbox.get("h", 1) or 1)
        heights.append(h)
        indexed_words.append({"word": word, "original_index": original_index, "y": y, "h": h, "x": int(bbox.get("x", 0) or 0)})

    if not indexed_words:
        return []

    typical_height = median(heights)
    line_tolerance = max(6, typical_height * 0.65)
    lines = []

    for entry in sorted(indexed_words, key=lambda item: (item["y"], item["x"])):
        target_line = None
        for line in lines:
            if abs(entry["y"] - line["y"]) <= line_tolerance:
                target_line = line
                break
        if target_line is None:
            lines.append({"y": entry["y"], "items": [entry]})
        else:
            target_line["items"].append(entry)
            target_line["y"] = sum(item["y"] for item in target_line["items"]) / len(target_line["items"])

    sorted_words = []
    for line in sorted(lines, key=lambda item: item["y"]):
        sorted_words.extend(item["word"] for item in sorted(line["items"], key=lambda item: (-item["x"], item["original_index"])))

    return sorted_words


def _merge_qari_text_with_layout(qari_text: str, layout_words: List[Dict], width: int, height: int) -> List[Dict]:
    """Use Qari words as the displayed OCR text and legacy boxes/confidence as layout.

    Qari's public OCR endpoint returns page text without reliable word-level
    bounding boxes. Raqim's old review UI depends on those boxes and confidence
    values. This function therefore performs a lightweight alignment: each Qari
    token is matched to the nearest remaining legacy layout token when possible,
    otherwise it consumes the next available layout box. The displayed word stays
    from Qari; only the box and confidence come from the old layout pass.
    """

    qari_tokens = [token for token in _clean_text(qari_text).split() if token]
    if not qari_tokens:
        return []

    if not layout_words:
        return _qari_words_from_text(qari_text, width, height)

    layout_words = _sort_layout_words_for_arabic_reading_order(layout_words)

    merged: List[Dict] = []
    cursor = 0
    max_lookahead = 18

    for qari_token in qari_tokens:
        qari_norm = _normalize_token_for_alignment(qari_token)
        chosen_index = None

        if qari_norm:
            search_end = min(len(layout_words), cursor + max_lookahead)
            for i in range(cursor, search_end):
                layout_norm = _normalize_token_for_alignment(layout_words[i].get("word", ""))
                if layout_norm and (layout_norm == qari_norm or layout_norm in qari_norm or qari_norm in layout_norm):
                    chosen_index = i
                    break

        if chosen_index is None and cursor < len(layout_words):
            chosen_index = cursor

        if chosen_index is not None and chosen_index < len(layout_words):
            source = layout_words[chosen_index]
            confidence = _safe_confidence(source.get("confidence"))
            bbox = source.get("bounding_box", {}) or {}
            merged_word = _word_item(
                word=qari_token,
                confidence=confidence,
                x=int(bbox.get("x", 0)),
                y=int(bbox.get("y", 0)),
                w=int(bbox.get("w", 1)),
                h=int(bbox.get("h", 1)),
                width=int(bbox.get("original_width", width)),
                height=int(bbox.get("original_height", height)),
                index=len(merged),
            )
            # Preserve the old yellow-highlight behavior from the layout OCR pass.
            merged_word["highlighted"] = bool(source.get("highlighted", merged_word["highlighted"]))
            merged_word["wasHighlighted"] = bool(source.get("wasHighlighted", merged_word["highlighted"]))
            merged.append(merged_word)
            cursor = chosen_index + 1
        else:
            fallback = _qari_words_from_text(qari_token, width, height)[0]
            fallback["index"] = len(merged)
            fallback["confidence"] = 0
            fallback["highlighted"] = True
            fallback["wasHighlighted"] = True
            merged.append(fallback)

    return merged


def _ocr_page_tesseract(image: Image.Image) -> List[Dict]:
    width, height = image.size
    ocr_image = _normalize_for_ocr(image)
    lang = _preferred_language()
    config = os.getenv("OCR_TESSERACT_CONFIG", "--oem 3 --psm 6")

    data = pytesseract.image_to_data(ocr_image, lang=lang, config=config, output_type=Output.DICT)

    words: List[Dict] = []
    total = len(data.get("text", []))
    for i in range(total):
        text = _clean_word(data["text"][i])
        if not text:
            continue

        confidence = _safe_confidence(data.get("conf", [])[i])
        if confidence < 0:
            continue

        words.append(
            _word_item(
                word=text,
                confidence=confidence,
                x=int(data.get("left", [0])[i] or 0),
                y=int(data.get("top", [0])[i] or 0),
                w=int(data.get("width", [1])[i] or 1),
                h=int(data.get("height", [1])[i] or 1),
                width=width,
                height=height,
                index=len(words),
            )
        )

    if not words:
        plain_text = _clean_word(pytesseract.image_to_string(ocr_image, lang=lang, config=config))
        if plain_text:
            words = _qari_words_from_text(plain_text, width, height)
            for word in words:
                word["confidence"] = 0
                word["highlighted"] = True
                word["wasHighlighted"] = True

    return words


def _ocr_page(image: Image.Image) -> tuple[List[Dict], Dict]:
    width, height = image.size

    if QARI_OCR_ENABLED:
        try:
            qari_text = _qari_page_text(image)
            layout_words = _ocr_page_tesseract(image)
            words = _merge_qari_text_with_layout(qari_text, layout_words, width, height)
            if words:
                highlighted_count = sum(1 for word in words if word.get("highlighted"))
                print(
                    f"✅ Qari OCR extracted {len(words)} review words using provider={QARI_OCR_PROVIDER}; "
                    f"legacy layout boxes={len(layout_words)}, highlighted={highlighted_count}."
                )
                return words, {
                    "ocr_engine": "qari",
                    "ocr_engine_label": "Qari OCR",
                    "ocr_provider": QARI_OCR_PROVIDER,
                    "qari_attempted": True,
                    "fallback_used": False,
                    "fallback_reason": "",
                }
            raise RuntimeError("Qari OCR returned empty text")
        except Exception as qari_error:
            fallback_reason = str(qari_error)
            print(f"⚠️ Qari OCR failed; fallback_to_tesseract={QARI_OCR_FALLBACK_TO_TESSERACT}: {fallback_reason}")
            if not QARI_OCR_FALLBACK_TO_TESSERACT:
                raise

            return _ocr_page_tesseract(image), {
                "ocr_engine": "tesseract",
                "ocr_engine_label": "Tesseract fallback",
                "ocr_provider": "tesseract",
                "qari_attempted": True,
                "fallback_used": True,
                "fallback_reason": fallback_reason,
            }

    lang = _preferred_language()
    return _ocr_page_tesseract(image), {
        "ocr_engine": "tesseract",
        "ocr_engine_label": f"Tesseract ({lang})",
        "ocr_provider": "tesseract",
        "qari_attempted": False,
        "fallback_used": False,
        "fallback_reason": "",
    }


def ocr_with_highlighting(file_path: str | os.PathLike[str], output_folder: str | os.PathLike[str]) -> List[Dict]:
    """Run OCR and return page-level words with review-compatible boxes."""

    output_dir = _prepare_output_folder(output_folder)
    pages = _load_pages(file_path)

    results: List[Dict] = []
    for page_number, image in enumerate(pages, start=1):
        preview_path = output_dir / f"original_page_{page_number}.png"
        image.save(preview_path, format="PNG")

        page_words, engine_info = _ocr_page(image)
        results.append(
            {
                "page_number": page_number,
                "image_path": str(preview_path),
                "text": page_words,
                "ocr_engine": engine_info.get("ocr_engine", "unknown"),
                "ocr_engine_label": engine_info.get("ocr_engine_label", "غير معروف"),
                "ocr_provider": engine_info.get("ocr_provider", "unknown"),
                "qari_attempted": engine_info.get("qari_attempted", False),
                "fallback_used": engine_info.get("fallback_used", False),
                "fallback_reason": engine_info.get("fallback_reason", ""),
            }
        )

    return results
