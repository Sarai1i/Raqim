"""OCR engine for Raqim with DeepSeek-OCR-2 support.

This module exposes DeepSeek-OCR-2 as Raqim's only OCR engine:

- ``ocr_with_highlighting(file_path, output_folder)`` converts PDF/image input into
  page images and returns OCR words with bounding boxes and confidence highlighting.

DeepSeek-OCR-2 is the active OCR engine for Raqim. It is a vision-language model
that returns the page text (and HTML tables). Since it does not emit word-level
bounding boxes, an approximate-box builder reconstructs RTL word boxes (and tagged
table cells) so the Raqim review workflow keeps working.

Note: the model uses custom code (``trust_remote_code=True``), is loaded lazily on
first use, and requires an NVIDIA GPU. Configure it via the
``DEEPSEEK_OCR_MODEL_NAME`` environment variable.
"""

from __future__ import annotations

import os
import re
import tempfile
import json
from pathlib import Path
from typing import Dict, List

from pdf2image import convert_from_path
from PIL import Image


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_DPI = int(os.getenv("OCR_PDF_DPI", "300"))
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "80"))

# DeepSeek-OCR-2 is the active OCR engine. It is loaded lazily on first use and
# needs an NVIDIA GPU. All settings are configurable via environment variables.
DEEPSEEK_OCR_MODEL_NAME = os.getenv("DEEPSEEK_OCR_MODEL_NAME", "deepseek-ai/DeepSeek-OCR-2")
# Prompt modes (see the official model card):
#   document with layout : "<image>\n<|grounding|>Convert the document to markdown. "
#   plain text only       : "<image>\nFree OCR. "
DEEPSEEK_OCR_PROMPT = os.getenv("DEEPSEEK_OCR_PROMPT", "<image>\n<|grounding|>Convert the document to markdown. ")
DEEPSEEK_OCR_BASE_SIZE = int(os.getenv("DEEPSEEK_OCR_BASE_SIZE", "1024"))
DEEPSEEK_OCR_IMAGE_SIZE = int(os.getenv("DEEPSEEK_OCR_IMAGE_SIZE", "768"))
DEEPSEEK_OCR_CROP_MODE = os.getenv("DEEPSEEK_OCR_CROP_MODE", "true").lower() in {"1", "true", "yes", "on"}
# DeepSeek does not emit per-word confidence; approximate boxes use this value.
DEEPSEEK_APPROX_CONFIDENCE = float(os.getenv("DEEPSEEK_APPROX_CONFIDENCE", "95"))
# DeepSeek grounding coordinates are normalized to this scale (0..N).
DEEPSEEK_COORD_SCALE = float(os.getenv("DEEPSEEK_COORD_SCALE", "1000.0"))

_DEEPSEEK_OCR = None


class DeepSeekOCRError(RuntimeError):
    """Raised when DeepSeek-OCR-2 inference fails."""


def configure_tesseract(tesseract_cmd: str | None = None) -> None:
    """Deprecated no-op. Tesseract was removed; DeepSeek-OCR-2 is the only OCR engine."""

    return None


def _resolve_deepseek_infer_settings(image: Image.Image) -> Dict[str, int | bool]:
    """Return safe DeepSeek infer() settings that avoid the model's param_img bug.

    DeepSeek's visual encoder only supports token grids of 144 (768px tiles) and
    256 (1024px global view). Using base_size=1280 with crop_mode=True triggers:
    ``cannot access local variable 'param_img' where it is not associated with a value``.
    """
    base_size = int(DEEPSEEK_OCR_BASE_SIZE)
    image_size = int(DEEPSEEK_OCR_IMAGE_SIZE)
    crop_mode = bool(DEEPSEEK_OCR_CROP_MODE)

    if crop_mode:
        if base_size != 1024:
            print(
                f"⚠️ DeepSeek crop_mode requires base_size=1024; "
                f"overriding DEEPSEEK_OCR_BASE_SIZE={base_size} → 1024."
            )
            base_size = 1024
        if image_size != 768:
            print(
                f"⚠️ DeepSeek crop_mode requires image_size=768; "
                f"overriding DEEPSEEK_OCR_IMAGE_SIZE={image_size} → 768."
            )
            image_size = 768
    else:
        if base_size not in {512, 640, 768, 1024, 1280}:
            print(f"⚠️ Unsupported DEEPSEEK_OCR_BASE_SIZE={base_size}; using 1024.")
            base_size = 1024
        if image_size not in {512, 640, 768, 1024}:
            print(f"⚠️ Unsupported DEEPSEEK_OCR_IMAGE_SIZE={image_size}; using 768.")
            image_size = 768

    width, height = image.size
    if crop_mode and max(width, height) > 768:
        # Large pages need tiling; keep the validated crop profile above.
        pass

    return {
        "base_size": base_size,
        "image_size": image_size,
        "crop_mode": crop_mode,
    }


def _format_deepseek_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "param_img" in message:
        return (
            "فشل DeepSeek-OCR-2 بسبب إعدادات صورة غير مدعومة (param_img). "
            "استخدم DEEPSEEK_OCR_BASE_SIZE=1024 وDEEPSEEK_OCR_IMAGE_SIZE=768 مع crop_mode، "
            "أو عطّل DEEPSEEK_OCR_CROP_MODE=false."
        )
    if "CUDA" in message.upper() or "cuda" in message:
        return f"تعذر تشغيل DeepSeek-OCR-2 على GPU: {message}"
    return f"تعذر تشغيل DeepSeek-OCR-2: {message}"


def _run_deepseek_infer(model, tokenizer, image_path: str, out_dir: str, image: Image.Image) -> str:
    """Run model.infer with validated settings and a safe crop_mode retry."""
    import contextlib
    import io as _io

    primary = _resolve_deepseek_infer_settings(image)
    attempts = [primary]
    if primary["crop_mode"]:
        attempts.append({**primary, "crop_mode": False})

    last_error: Exception | None = None
    buffer = _io.StringIO()

    for attempt_index, settings in enumerate(attempts):
        if attempt_index > 0:
            print(
                "⚠️ إعادة محاولة DeepSeek-OCR-2 مع crop_mode=false "
                f"بعد فشل المحاولة الأولى ({last_error})."
            )
        buffer.seek(0)
        buffer.truncate(0)
        try:
            with contextlib.redirect_stdout(buffer):
                res = model.infer(
                    tokenizer,
                    prompt=DEEPSEEK_OCR_PROMPT,
                    image_file=image_path,
                    output_path=out_dir,
                    base_size=settings["base_size"],
                    image_size=settings["image_size"],
                    crop_mode=settings["crop_mode"],
                    save_results=True,
                )
            return buffer.getvalue(), res
        except Exception as exc:
            last_error = exc
            message = str(exc)
            retryable = "param_img" in message or (
                settings["crop_mode"] and attempt_index == 0
            )
            if retryable and attempt_index < len(attempts) - 1:
                continue
            raise DeepSeekOCRError(_format_deepseek_error(exc)) from exc

    raise DeepSeekOCRError(_format_deepseek_error(last_error or RuntimeError("unknown DeepSeek failure")))


def _load_deepseek_ocr():
    """Lazily load DeepSeek-OCR-2 (once per process). Requires an NVIDIA GPU."""
    global _DEEPSEEK_OCR
    if _DEEPSEEK_OCR is None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        if not torch.cuda.is_available():
            # Mock mode if no GPU
            print("⚠️ No GPU detected. Entering Mock Mode for testing.")
            return "MOCK_MODEL", "MOCK_TOKENIZER"

        tokenizer = AutoTokenizer.from_pretrained(
            DEEPSEEK_OCR_MODEL_NAME, trust_remote_code=True
        )
        try:
            model = AutoModel.from_pretrained(
                DEEPSEEK_OCR_MODEL_NAME,
                _attn_implementation="flash_attention_2",
                trust_remote_code=True,
                use_safetensors=True,
            )
        except Exception as exc:
            print(f"flash_attention_2 unavailable ({exc}); falling back to eager.")
            model = AutoModel.from_pretrained(
                DEEPSEEK_OCR_MODEL_NAME,
                _attn_implementation="eager",
                trust_remote_code=True,
                use_safetensors=True,
            )
        model = model.eval().cuda().to(torch.bfloat16)
        _DEEPSEEK_OCR = (model, tokenizer)
    return _DEEPSEEK_OCR


def _read_deepseek_result(output_dir: str, fallback) -> str:
    """Read the markdown/text result DeepSeek writes to output_dir."""
    import glob

    for pattern in ("*.mmd", "*.md", "*.txt"):
        files = glob.glob(os.path.join(output_dir, "**", pattern), recursive=True)
        if files:
            files.sort(key=os.path.getmtime, reverse=True)
            try:
                with open(files[0], "r", encoding="utf-8") as handle:
                    text = handle.read().strip()
                if text:
                    return text
            except OSError:
                pass
    return fallback.strip() if isinstance(fallback, str) else ""


def _deepseek_ocr_text(image: Image.Image) -> str:
    """Extract cleaned page text from an image using DeepSeek-OCR-2."""
    return _clean_text(_deepseek_ocr_raw(image))


def _deepseek_ocr_raw(image: Image.Image) -> str:
    """Return the RAW DeepSeek output (with <|ref|>/<|det|> grounding tags)."""
    model_data = _load_deepseek_ocr()
    if model_data == ("MOCK_MODEL", "MOCK_TOKENIZER"):
        return "<|ref|>فقرة تجريبية<|/ref|><|det|>[[100,100,900,200]]<|/det|>هذا نص تجريبي تم إنشاؤه لأن البيئة الحالية لا تدعم GPU. مشروع رقيم يعمل الآن في وضع المحاكاة.\n<|ref|>جدول<|/ref|><|det|>[[100,300,900,600]]<|/det|><table><tr><td>الاسم</td><td>العمر</td></tr><tr><td>أحمد</td><td>25</td></tr></table>"

    model, tokenizer = model_data

    with tempfile.TemporaryDirectory() as work_dir:
        image_path = os.path.join(work_dir, "input.png")
        out_dir = os.path.join(work_dir, "out")
        os.makedirs(out_dir, exist_ok=True)
        image.convert("RGB").save(image_path)

        captured, res = _run_deepseek_infer(model, tokenizer, image_path, out_dir, image)

        def _trim(t: str) -> str:
            return re.split(r"=*\s*save results\s*:?\s*=*", t, maxsplit=1)[0]

        for candidate in (captured, res if isinstance(res, str) else ""):
            if candidate and ("<|det|>" in candidate or "<|ref|>" in candidate):
                return _trim(candidate)
        return _trim(_read_deepseek_result(out_dir, res))


def _scale_box(bbox, width: int, height: int) -> Dict:
    """Convert a normalized (0..1000) [x1,y1,x2,y2] box to pixel coords for the image."""
    x1, y1, x2, y2 = bbox
    px = int(min(x1, x2) / DEEPSEEK_COORD_SCALE * width)
    py = int(min(y1, y2) / DEEPSEEK_COORD_SCALE * height)
    pw = max(1, int(abs(x2 - x1) / DEEPSEEK_COORD_SCALE * width))
    ph = max(1, int(abs(y2 - y1) / DEEPSEEK_COORD_SCALE * height))
    return {
        "x": max(0, px),
        "y": max(0, py),
        "w": pw,
        "h": ph,
        "original_width": int(width),
        "original_height": int(height),
    }


def _parse_deepseek_segments(raw: str):
    """Parse RAW DeepSeek output into segments: {bbox: (x1,y1,x2,y2)|None, text}."""
    pattern = re.compile(
        r"<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>(\[\[.*?\]\])<\|/det\|>(.*?)(?=<\|ref\|>|\Z)",
        re.DOTALL,
    )
    segments = []
    for match in pattern.finditer(raw):
        label = (match.group(1) or "").strip().lower()
        nums = [int(n) for n in re.findall(r"-?\d+", match.group(2))]
        bbox = None
        if len(nums) >= 4:
            xs = nums[0::2]
            ys = nums[1::2]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        segments.append({"bbox": bbox, "text": match.group(3), "label": label})

    if not segments:
        segments.append({"bbox": None, "text": raw, "label": ""})
    return segments


def _assign_intra_segment_source_boxes(seg_words: List[Dict], source_box: Dict, width: int, height: int) -> None:
    if not seg_words or not source_box:
        return

    boxes = [w.get("bounding_box", {}) for w in seg_words]
    ax0 = min(b.get("x", 0) for b in boxes)
    ay0 = min(b.get("y", 0) for b in boxes)
    ax1 = max(b.get("x", 0) + b.get("w", 1) for b in boxes)
    ay1 = max(b.get("y", 0) + b.get("h", 1) for b in boxes)
    span_x = max(1, ax1 - ax0)
    span_y = max(1, ay1 - ay0)

    rx, ry = source_box["x"], source_box["y"]
    rw, rh = source_box["w"], source_box["h"]

    for word in seg_words:
        b = word.get("bounding_box", {})
        nx = (b.get("x", 0) - ax0) / span_x
        ny = (b.get("y", 0) - ay0) / span_y
        nw = b.get("w", 1) / span_x
        nh = b.get("h", 1) / span_y
        word["source_box"] = {
            "x": int(rx + nx * rw),
            "y": int(ry + ny * rh),
            "w": max(1, int(nw * rw)),
            "h": max(1, int(nh * rh)),
            "original_width": int(width),
            "original_height": int(height),
        }


def _build_words_with_real_boxes(raw: str, width: int, height: int) -> List[Dict]:
    segments = _parse_deepseek_segments(raw)
    words: List[Dict] = []

    for block_id, segment in enumerate(segments):
        raw_seg = segment["text"]
        table_match = re.search(r"<table[^>]*>.*?</table>", raw_seg, flags=re.DOTALL | re.IGNORECASE)
        if table_match:
            source_box = _scale_box(segment["bbox"], width, height) if segment["bbox"] else None
            y_start = source_box["y"] + 4 if source_box else None
            cells = _parse_html_table_cells(table_match.group(0))
            seg_words = _table_cells_to_words(cells, block_id + 1, width, height, y_start=y_start)
            _assign_intra_segment_source_boxes(seg_words, source_box, width, height)
            for word in seg_words:
                word["index"] = len(words)
                word["block_id"] = block_id
                words.append(word)
        else:
            source_box = _scale_box(segment["bbox"], width, height) if segment["bbox"] else None
            y_start = source_box["y"] + 4 if source_box else None
            seg_words = _words_from_structured_text(raw_seg, block_id + 1, width, height, y_start=y_start)
            _assign_intra_segment_source_boxes(seg_words, source_box, width, height)
            for word in seg_words:
                word["index"] = len(words)
                word["block_id"] = block_id
                words.append(word)
    return words


def _clean_text(text: str) -> str:
    """Clean RAW DeepSeek text by removing grounding tags and HTML tables."""
    text = re.sub(r"<\|ref\|>.*?<\|/ref\|>", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|det\|>.*?<\|/det\|>", "", text, flags=re.DOTALL)
    text = re.sub(r"<table[^>]*>.*?</table>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _parse_html_table_cells(html: str) -> List[Dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    cells = []
    rows = soup.find_all("tr")
    for r_idx, row in enumerate(rows):
        cols = row.find_all(["td", "th"])
        for c_idx, col in enumerate(cols):
            cells.append({
                "text": col.get_text(strip=True),
                "row": r_idx,
                "col": c_idx,
                "is_header": col.name == "th",
            })
    return cells


def _table_cells_to_words(cells: List[Dict], block_id: int, width: int, height: int, y_start=None) -> List[Dict]:
    words = []
    line_h = 40
    curr_y = y_start if y_start is not None else 100
    for cell in cells:
        cell_text = cell["text"]
        if not cell_text: continue
        parts = cell_text.split()
        for p in parts:
            words.append({
                "word": p,
                "confidence": DEEPSEEK_APPROX_CONFIDENCE,
                "bounding_box": {"x": 100, "y": curr_y, "w": 50, "h": 30},
                "block_id": block_id,
                "metadata": {"is_table": True, "row": cell["row"], "col": cell["col"]}
            })
        curr_y += line_h
    return words


def _words_from_structured_text(text: str, block_id: int, width: int, height: int, y_start=None) -> List[Dict]:
    words = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    curr_y = y_start if y_start is not None else 50
    line_h = 40
    for line in lines:
        parts = line.split()
        curr_x = width - 100
        for p in reversed(parts):
            words.append({
                "word": p,
                "confidence": DEEPSEEK_APPROX_CONFIDENCE,
                "bounding_box": {"x": curr_x - 60, "y": curr_y, "w": 50, "h": 30},
                "block_id": block_id,
            })
            curr_x -= 70
        curr_y += line_h
    return words


def ocr_with_highlighting(file_path: str | Path, output_folder: str | Path) -> List[Dict]:
    file_path = Path(file_path)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    if file_path.suffix.lower() == ".pdf":
        images = convert_from_path(file_path, dpi=DEFAULT_DPI)
    else:
        images = [Image.open(file_path)]

    results = []
    for i, img in enumerate(images):
        img_filename = f"page_{i+1}.png"
        img_path = output_folder / img_filename
        img.save(img_path, "PNG")
        
        raw_output = _deepseek_ocr_raw(img)
        page_words = _build_words_with_real_boxes(raw_output, img.width, img.height)
        
        results.append({
            "page_number": i + 1,
            "image_url": f"/outputs/{file_path.stem}/{img_filename}",
            "text": page_words
        })
    return results
