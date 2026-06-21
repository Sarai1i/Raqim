"""OCR engine for Raqim with DeepSeek-OCR-2 support.

This module keeps the interface expected by ``Backend/app.py``:

- ``configure_tesseract(tesseract_cmd)`` is kept as a no-op shim for backward
  compatibility (Tesseract has been removed as the OCR engine).
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
import json
import tempfile
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

# OCR provider selector. Default "local" keeps the local GPU DeepSeek path intact.
# Set OCR_PROVIDER=gradio_deepseek to call a remote DeepSeek over Gradio instead
# (no _load_deepseek_ocr, no .cuda()).
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "local").strip().lower()
# Remote DeepSeek-over-Gradio settings (used only when OCR_PROVIDER=gradio_deepseek).
GRADIO_DEEPSEEK_URL = os.getenv("GRADIO_DEEPSEEK_URL", "")
GRADIO_DEEPSEEK_API_NAME = os.getenv("GRADIO_DEEPSEEK_API_NAME", "/ocr_image")

_DEEPSEEK_OCR = None
_GRADIO_DEEPSEEK_CLIENT = None


def configure_tesseract(tesseract_cmd: str | None = None) -> None:
    """No-op shim kept for backward compatibility.

    Tesseract has been removed as Raqim's OCR engine in favor of DeepSeek-OCR-2.
    ``app.py`` still imports and calls this function at startup, so it is kept
    here intentionally and simply does nothing.
    """

    return None


def _resolve_deepseek_infer_settings(image):
    """إعدادات infer آمنة تتجنّب خطأ param_img داخل كود DeepSeek.

    المُشفّر البصري يدعم فقط 144 (بلاطات 768) و256 (عرض شامل 1024). استخدام
    base_size=1280 مع crop_mode=True يسبّب: cannot access local variable 'param_img'.
    لذا نفرض الإعداد المتوافق تلقائيًا.
    """
    base_size = int(DEEPSEEK_OCR_BASE_SIZE)
    image_size = int(DEEPSEEK_OCR_IMAGE_SIZE)
    crop_mode = bool(DEEPSEEK_OCR_CROP_MODE)

    if crop_mode:
        if base_size != 1024:
            print(f"⚠️ crop_mode يتطلب base_size=1024؛ تجاوز {base_size} → 1024.")
            base_size = 1024
        if image_size != 768:
            print(f"⚠️ crop_mode يتطلب image_size=768؛ تجاوز {image_size} → 768.")
            image_size = 768
    else:
        if base_size not in {512, 640, 768, 1024, 1280}:
            print(f"⚠️ base_size={base_size} غير مدعوم؛ استخدام 1024.")
            base_size = 1024
        if image_size not in {512, 640, 768, 1024}:
            print(f"⚠️ image_size={image_size} غير مدعوم؛ استخدام 768.")
            image_size = 768

    return {"base_size": base_size, "image_size": image_size, "crop_mode": crop_mode}


def _load_deepseek_ocr():
    """Lazily load DeepSeek-OCR-2 (once per process). Requires an NVIDIA GPU."""
    global _DEEPSEEK_OCR
    if _DEEPSEEK_OCR is None:
        import torch
        from transformers import AutoModel, AutoTokenizer

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
    """Return the RAW DeepSeek output (with <|ref|>/<|det|> grounding tags).

    DeepSeek prints the grounded result to stdout during inference, while the
    saved .mmd file is already cleaned and carries no coordinates. We capture
    stdout to recover the real per-segment boxes, falling back to the infer
    return value or the saved file if no grounding is present (older builds).
    """
    import contextlib
    import io as _io

    model, tokenizer = _load_deepseek_ocr()

    with tempfile.TemporaryDirectory() as work_dir:
        image_path = os.path.join(work_dir, "input.png")
        out_dir = os.path.join(work_dir, "out")
        os.makedirs(out_dir, exist_ok=True)
        image.convert("RGB").save(image_path)

        buffer = _io.StringIO()
        _settings = _resolve_deepseek_infer_settings(image)
        with contextlib.redirect_stdout(buffer):
            res = model.infer(
                tokenizer,
                prompt=DEEPSEEK_OCR_PROMPT,
                image_file=image_path,
                output_path=out_dir,
                base_size=_settings["base_size"],
                image_size=_settings["image_size"],
                crop_mode=_settings["crop_mode"],
                save_results=True,
            )
        captured = buffer.getvalue()

        def _trim(t: str) -> str:
            # كل ما بعد علامة "save results" هو سجلّات تشغيل وليس محتوى.
            return re.split(r"=*\s*save results\s*:?\s*=*", t, maxsplit=1)[0]

        # Prefer whichever source actually carries grounding tags.
        for candidate in (captured, res if isinstance(res, str) else ""):
            if candidate and ("<|det|>" in candidate or "<|ref|>" in candidate):
                return _trim(candidate)
        # No grounding available; fall back to the cleaned saved result.
        return _trim(_read_deepseek_result(out_dir, res))


def _get_gradio_deepseek_client():
    """Lazily create a single gradio_client.Client for the remote DeepSeek space."""
    global _GRADIO_DEEPSEEK_CLIENT
    if not GRADIO_DEEPSEEK_URL:
        raise RuntimeError(
            "OCR_PROVIDER=gradio_deepseek لكن GRADIO_DEEPSEEK_URL غير مضبوط في .env"
        )
    if _GRADIO_DEEPSEEK_CLIENT is None:
        from gradio_client import Client
        _GRADIO_DEEPSEEK_CLIENT = Client(GRADIO_DEEPSEEK_URL)
    return _GRADIO_DEEPSEEK_CLIENT


def _gradio_deepseek_raw(image: Image.Image) -> str:
    """Send a page image to the remote DeepSeek (Gradio) and return its RAW output.

    The returned text keeps the original ``<|ref|>``/``<|det|>`` grounding tags so it
    can be passed unchanged to ``_build_words_with_real_boxes`` (coordinates preserved).
    No local model is loaded and no GPU (.cuda()) is used in this path.
    """
    try:
        from gradio_client import handle_file as _gradio_file
    except Exception:
        # Older gradio_client versions expose ``file`` instead of ``handle_file``.
        from gradio_client import file as _gradio_file

    client = _get_gradio_deepseek_client()
    with tempfile.TemporaryDirectory() as work_dir:
        image_path = os.path.join(work_dir, "input.png")
        image.convert("RGB").save(image_path)
        try:
            result = client.predict(_gradio_file(image_path), api_name=GRADIO_DEEPSEEK_API_NAME)
        except Exception as exc:
            raise RuntimeError(f"تعذر استدعاء DeepSeek عبر Gradio: {exc}") from exc

    # Some endpoints return a tuple/list of outputs; take the first textual one.
    if isinstance(result, (list, tuple)):
        result = result[0] if result else ""
    return result if isinstance(result, str) else str(result)


def _coerce_gradio_pages(parsed, local_image_path: str):
    """Normalize a parsed Gradio JSON payload into a Raqim pages list.

    The remote may return a ready Raqim result: a list (or single dict) of pages,
    each having ``page_number`` and ``text``. We accept it as-is and only rewrite
    ``image_path`` to point to the locally saved page image. Returns the pages
    list, or ``None`` if the payload is not in the expected Raqim page format.
    """
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        return None

    pages_out = []
    for page in parsed:
        if not isinstance(page, dict) or "page_number" not in page or "text" not in page:
            return None
        page = dict(page)
        page["image_path"] = local_image_path
        pages_out.append(page)
    return pages_out


# DeepSeek emits grounding coordinates on a normalized 0..1000 grid.


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
    """Parse RAW DeepSeek output into segments: {bbox: (x1,y1,x2,y2)|None, text}.

    Each segment is: <|ref|>label<|/ref|><|det|>[[..]]<|/det|> followed by its text
    up to the next <|ref|>. If grounding tags are absent, the whole text is one
    segment with no bbox.
    """
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
    """Estimate a per-word source box inside the segment's real grounding box.

    DeepSeek only gives one real box per segment (paragraph/table). We already
    laid the segment's words out approximately (RTL lines, correct order) via
    ``_words_from_structured_text``. Here we linearly map that approximate layout
    into the real paragraph rectangle, so each word gets a tight sub-box near its
    true position. This is an estimate (not pixel-perfect) but far tighter than
    highlighting the whole paragraph.
    """
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
    """Build review words segment-by-segment, attaching each word an estimated
    ``source_box`` inside the segment's real grounding box (used to highlight the
    original page), while keeping approximate per-line boxes for the left-panel
    layout."""
    segments = _parse_deepseek_segments(raw)
    words: List[Dict] = []

    for block_id, segment in enumerate(segments):
        raw_seg = segment["text"]

        # جدول HTML: نحلّله مباشرة مع دعم الامتدادات (rowspan/colspan).
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
                word["block_type"] = "table"
                words.append(word)
            continue

        seg_text = _clean_text(raw_seg)
        if not seg_text:
            continue

        source_box = _scale_box(segment["bbox"], width, height) if segment["bbox"] else None
        # Lay out this segment's approximate boxes starting at its real top, so the
        # left-panel paragraph ordering follows the page's real vertical order.
        y_start = source_box["y"] + 4 if source_box else None
        seg_words = _words_from_structured_text(seg_text, width, height, y_start=y_start)

        # Estimate a tight per-word source box inside the real paragraph box.
        _assign_intra_segment_source_boxes(seg_words, source_box, width, height)

        # Classify the block so exports (e.g. Word) can rebuild structure cleanly.
        label = segment.get("label", "")
        has_table = any(w.get("table_id") for w in seg_words)
        if has_table:
            block_type = "table"
        elif label in {"title", "sub_title", "section_title", "header"}:
            block_type = "heading"
        else:
            block_type = "text"

        for word in seg_words:
            word["index"] = len(words)
            word["block_id"] = block_id
            word["block_type"] = block_type
            words.append(word)

    return words


def _parse_html_table_cells(table_html: str) -> List[Dict]:
    """يحلّل جدول HTML إلى خلايا بمواضعها الصحيحة في الشبكة مع دعم rowspan/colspan.

    يعيد قائمة قواميس: {row, col, rowspan, colspan, text}. يضع كل خلية في أول
    موضع شاغر في صفّها، ويحجز المواضع التي تغطيها الامتدادات حتى لا تتزحلق الخلايا.
    """
    occupied = set()
    cells: List[Dict] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.DOTALL | re.IGNORECASE)
    for r, row_html in enumerate(rows):
        col = 0
        for attrs, content in re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", row_html, flags=re.DOTALL | re.IGNORECASE):
            while (r, col) in occupied:
                col += 1
            rs = re.search(r'rowspan="?(\d+)"?', attrs)
            cs = re.search(r'colspan="?(\d+)"?', attrs)
            rowspan = int(rs.group(1)) if rs else 1
            colspan = int(cs.group(1)) if cs else 1
            text = re.sub(r"<[^>]+>", "", content).strip()
            cells.append({"row": r, "col": col, "rowspan": rowspan, "colspan": colspan, "text": text})
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied.add((r + dr, col + dc))
            col += colspan
    return cells


def _table_cells_to_words(cells: List[Dict], table_id: int, width: int, height: int, y_start: int = None) -> List[Dict]:
    """يحوّل خلايا الجدول (مع الامتدادات) إلى كلمات مراجعة موسومة."""
    if not cells:
        return []
    nrows = max(c["row"] + c["rowspan"] for c in cells)
    ncols = max(c["col"] + c["colspan"] for c in cells)
    margin_x = max(18, width // 35)
    col_width = max(40, (width - 2 * margin_x) // max(1, ncols))
    row_h = max(24, min(48, height // max(nrows + 3, 8)))
    y0 = margin_x if y_start is None else max(margin_x, int(y_start))

    words = []
    for c in cells:
        x = width - margin_x - (c["col"] + c["colspan"]) * col_width
        item = _word_item(
            word=c["text"] if c["text"] else " ",
            confidence=DEEPSEEK_APPROX_CONFIDENCE,
            x=x,
            y=y0 + c["row"] * row_h,
            w=col_width * c["colspan"] - 4,
            h=row_h * c["rowspan"] - 2,
            width=width,
            height=height,
            index=len(words),
        )
        item["table_id"] = table_id
        item["table_row"] = c["row"]
        item["table_col"] = c["col"]
        item["table_rowspan"] = c["rowspan"]
        item["table_colspan"] = c["colspan"]
        words.append(item)
    return words


def _prepare_output_folder(output_folder):
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


def _html_table_to_markdown(text: str) -> str:
    """Convert DeepSeek's <table>...</table> HTML blocks into Markdown pipe rows.

    DeepSeek's markdown mode emits real HTML tables (with rowspan/colspan). We
    flatten each <tr> into a "| cell | cell |" line so the rest of the pipeline
    (table detection + frontend rendering) can handle it. Spanning attributes are
    ignored (cells are kept in order), which is good enough for review display.
    """

    def render_table(match):
        table_html = match.group(0)
        rows_out = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if cells:
                rows_out.append("| " + " | ".join(cells) + " |")
        return "\n" + "\n".join(rows_out) + "\n" if rows_out else ""

    return re.sub(r"<table[^>]*>.*?</table>", render_table, text, flags=re.DOTALL | re.IGNORECASE)


def _normalize_latex_math(text: str) -> str:
    r"""Convert DeepSeek's LaTeX delimiters to standard Markdown math fences.

    DeepSeek emits inline math as ``\( ... \)`` and display math as ``\[ ... \]``,
    which most Markdown/math renderers do not recognize. We convert them to
    ``$ ... $`` (inline) and ``$$ ... $$`` (display) so KaTeX/MathJax can render
    them. The LaTeX body itself is preserved verbatim.
    """
    # Display math: \[ ... \]  ->  $$ ... $$
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: "$$" + m.group(1).strip() + "$$", text, flags=re.DOTALL)
    # Inline math:  \( ... \)  ->  $ ... $
    text = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1).strip() + "$", text, flags=re.DOTALL)
    return text


def _clean_text(text: str) -> str:
    """Clean OCR output while preserving paragraph and table (Markdown) structure.

    DeepSeek's layout/markdown mode emits meaningful line breaks (paragraphs,
    headings), HTML tables, and grounding tags. We convert HTML tables to
    Markdown rows first, then strip remaining tags, keeping structure intact.
    """

    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    # Normalize LaTeX math delimiters \( \) and \[ \] to $ and $$ first.
    text = _normalize_latex_math(text)
    # Convert <table> HTML to Markdown pipe rows BEFORE stripping tags.
    text = _html_table_to_markdown(text)
    # Remove whole grounding blocks: <|ref|>label<|/ref|> and <|det|>[[..]]<|/det|>.
    text = re.sub(r"<\|ref\|>.*?<\|/ref\|>", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|det\|>.*?<\|/det\|>", "", text, flags=re.DOTALL)
    # Remove any leftover grounding tags and coordinate arrays.
    text = re.sub(r"<\|[^|>]*\|>", "", text)
    text = re.sub(r"\[\[[\d,\s]+\]\]", "", text)
    # Remove any remaining HTML tags (keep their text).
    text = re.sub(r"<[^>]+>", "", text)

    cleaned_lines = []
    for line in text.split("\n"):
        # Collapse repeated spaces/tabs within a line but keep the line itself.
        line = re.sub(r"[ \t]+", " ", line).strip()
        # Drop leading Markdown heading markers (e.g. "## عنوان" -> "عنوان").
        line = re.sub(r"^#{1,6}\s*", "", line)
        # Drop DeepSeek debug/log lines that may leak from stdout capture.
        if re.match(r"^=*\s*save results", line) or re.fullmatch(r"=+", line):
            continue
        if re.match(r"^(BASE|PATCHES)\s*:", line) or re.match(r"^(image|other)\s*:\s*\d", line):
            continue
        cleaned_lines.append(line)

    out = "\n".join(cleaned_lines)
    # Collapse 3+ blank lines into a single blank line (paragraph separator).
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


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


def _is_table_row(line: str) -> bool:
    """A Markdown table row looks like: | a | b | c |"""
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    """The row under the header, e.g. |---|---|---| (dashes/colons only)."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(set(c) <= {"-", ":"} and c for c in cells)


def _split_table_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _words_from_structured_text(text: str, width: int, height: int, y_start: int = None) -> List[Dict]:
    """Build review words from text while tagging Markdown table cells.

    Normal lines become RTL word boxes. Markdown table rows become one clickable
    word per cell, tagged with table_id/table_row/table_col so the frontend can
    render a real table. Separator rows (|---|) are dropped. ``y_start`` lets the
    caller place this chunk at its real vertical position on the page.
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
    y = margin_y if y_start is None else max(margin_y, int(y_start))
    table_counter = 0
    in_table = False
    table_row_index = 0
    current_line = 0

    for line in lines:
        # ----- Markdown table row -----
        if _is_table_row(line):
            if _is_table_separator(line):
                continue  # drop the |---|---| line
            if not in_table:
                in_table = True
                table_counter += 1
                table_row_index = 0
            cells = _split_table_cells(line)
            ncols = max(1, len(cells))
            col_width = max(40, (width - 2 * margin_x) // ncols)
            row_h = max(22, int(line_height * 0.8))
            for col, cell in enumerate(cells):
                # RTL: first cell is on the right
                x = width - margin_x - (col + 1) * col_width
                item = _word_item(
                    word=cell if cell else " ",
                    confidence=DEEPSEEK_APPROX_CONFIDENCE,
                    x=x,
                    y=y,
                    w=col_width - 4,
                    h=row_h,
                    width=width,
                    height=height,
                    index=len(words),
                )
                item["table_id"] = table_counter
                item["table_row"] = table_row_index
                item["table_col"] = col
                item["line_index"] = current_line
                words.append(item)
            table_row_index += 1
            y += line_height
            current_line += 1
            continue

        # ----- normal text line -----
        in_table = False
        # سطر معادلة كامل ($...$ أو $$...$$): نخرجه ككلمة واحدة موسومة is_math
        # حتى تعرضه الواجهة كمعادلة منسّقة (KaTeX) بدل تكسيره إلى رموز.
        stripped_line = line.strip()
        # نتجاهل نقطة التعداد البادئة (•, -, *) قبل فحص المعادلة.
        math_core = re.sub(r"^[•\-\*]\s*", "", stripped_line).strip()
        math_match = re.fullmatch(r"\$\$(.+?)\$\$|\$(.+?)\$", math_core, flags=re.DOTALL)
        if math_match:
            latex = (math_match.group(1) or math_match.group(2) or "").strip()
            display = math_match.group(1) is not None  # $$..$$ = معادلة معروضة
            item = _word_item(
                word=math_core,
                confidence=DEEPSEEK_APPROX_CONFIDENCE,
                x=margin_x,
                y=y,
                w=width - 2 * margin_x,
                h=max(28, line_height),
                width=width,
                height=height,
                index=len(words),
            )
            item["is_math"] = True
            item["latex"] = latex
            item["math_display"] = display
            item["line_index"] = current_line
            words.append(item)
            y += line_height
            current_line += 1
            continue

        # نقسّم السطر إلى أجزاء: معادلات مغلّفة ($...$ أو $$...$$) ونص عادي،
        # ثم نكتشف داخل النص أي وحدة معادلة غير مغلّفة (تحوي أوامر LaTeX).
        raw_parts = re.split(r"(\$\$.+?\$\$|\$.+?\$)", line)
        segments = []  # (kind, content, display)
        for part in raw_parts:
            if not part or not part.strip():
                continue
            fenced = re.fullmatch(r"\$\$(.+?)\$\$|\$(.+?)\$", part.strip(), flags=re.DOTALL)
            if fenced:
                latex = (fenced.group(1) or fenced.group(2) or "").strip()
                segments.append(("math", latex, fenced.group(1) is not None))
            else:
                for tok in part.split():
                    # معادلة غير مغلّفة: تحوي أمر LaTeX (\cmd) أو منخفض/مرفوع ({_}/{^}).
                    if re.search(r"\\[a-zA-Z]+|_\{|\^\{|\\vec", tok):
                        segments.append(("math", tok, False))
                    else:
                        segments.append(("text", tok, False))

        if not segments:
            y += line_height
            current_line += 1
            continue

        x_cursor = width - margin_x
        for kind, content, display in segments:
            if kind == "math":
                token_width = max(40, min(width - (2 * margin_x), len(content) * char_width + 16))
            else:
                token_width = max(24, min(width - (2 * margin_x), len(content) * char_width + 12))
            if x_cursor - token_width < margin_x:
                y += line_height
                x_cursor = width - margin_x
            x = x_cursor - token_width
            item = _word_item(
                word=(f"${content}$" if kind == "math" else content),
                confidence=DEEPSEEK_APPROX_CONFIDENCE,
                x=x,
                y=y,
                w=token_width,
                h=max(20, int(line_height * 0.78)),
                width=width,
                height=height,
                index=len(words),
            )
            if kind == "math":
                item["is_math"] = True
                item["latex"] = content
                item["math_display"] = display
            item["line_index"] = current_line
            words.append(item)
            x_cursor = x - gap
        y += line_height
        current_line += 1

    return words


def _ocr_page(image: Image.Image) -> tuple[List[Dict], Dict]:
    """Run DeepSeek-OCR-2 on a page image and return review-compatible words."""

    width, height = image.size

    raw = _deepseek_ocr_raw(image)
    words = _build_words_with_real_boxes(raw, width, height)

    if not words:
        raise RuntimeError("DeepSeek-OCR-2 returned empty text")

    highlighted_count = sum(1 for word in words if word.get("highlighted"))
    print(
        f"✅ DeepSeek-OCR-2 extracted {len(words)} review words "
        f"(model={DEEPSEEK_OCR_MODEL_NAME}, highlighted={highlighted_count})."
    )

    return words, {
        "ocr_engine": "deepseek",
        "ocr_engine_label": f"DeepSeek-OCR-2 ({DEEPSEEK_OCR_MODEL_NAME})",
        "ocr_provider": "deepseek_local",
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

        if OCR_PROVIDER == "gradio_deepseek":
            gradio_raw = _gradio_deepseek_raw(image)
            stripped = gradio_raw.strip() if isinstance(gradio_raw, str) else ""
            # (1) ناتج JSON جاهز بصيغة Raqim: نعيده مباشرة بعد ضبط image_path
            #     إلى صورة الصفحة المحلية، دون تمريره إلى _build_words_with_real_boxes.
            if stripped[:1] in ("[", "{"):
                try:
                    parsed = json.loads(stripped)
                except (ValueError, TypeError):
                    parsed = None
                page_dicts = _coerce_gradio_pages(parsed, str(preview_path)) if parsed is not None else None
                if page_dicts is not None:
                    results.extend(page_dicts)
                    continue
            # (2) ليس JSON متوقعًا: نعامله كـ raw DeepSeek output ونبني الكلمات منه.
            page_words = _build_words_with_real_boxes(gradio_raw, image.width, image.height)
            results.append(
                {
                    "page_number": page_number,
                    "image_path": str(preview_path),
                    "text": page_words,
                    "ocr_engine": "deepseek",
                    "ocr_engine_label": f"DeepSeek-OCR-2 (gradio, {DEEPSEEK_OCR_MODEL_NAME})",
                    "ocr_provider": "gradio_deepseek",
                    "qari_attempted": False,
                    "fallback_used": False,
                    "fallback_reason": "",
                }
            )
            continue

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