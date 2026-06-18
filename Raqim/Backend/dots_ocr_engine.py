"""DotOCR (dots.mocr) layout-analysis engine for Raqim.

This engine runs rednote-hilab's ``dots.mocr`` vision-language model as a
**layout analyzer**: it asks the model for a JSON description of every layout
element on the page (bbox + category + text), then reconstructs Raqim's standard
page/word structure from that JSON so the rest of the app (review UI + DOCX
export) works unchanged.

Mapping from DotOCR JSON -> Raqim structure:

* ``Table``                         -> a ``block_type == "table"`` block whose
  HTML is parsed into real cells (``table_row`` / ``table_col`` / spans), which
  ``docx_builder`` turns directly into a Word table.
* ``Title`` / ``Section-header``    -> ``block_type == "heading"`` (Word heading).
* ``Picture``                       -> skipped (no text content).
* everything else (``Text``,
  ``List-item``, ``Formula``, ``Page-footer`` ...) -> ``block_type == "text"``.

Blocks are ordered by their bbox coordinates (top-to-bottom, then left-to-right)
to preserve human reading order.

DeepSeek-OCR-2 is untouched and remains Raqim's default engine; this module is
only imported when ``OCR_ENGINE=dots``. It reuses the layout helpers from
``ocr_model`` (HTML-table parsing, RTL word layout, source-box estimation) and
the hardened model loader/inference from ``test_dots_ocr``.

Requires the dots.mocr dependencies (see ``requirements-dots.txt``); in
particular ``transformers==4.57.6`` for correct output (newer transformers load
but emit empty/incorrect results).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Dict, List

import ocr_model
from ocr_engine import DotsOCRError

DOTS_MOCR_MODEL_NAME = os.getenv("DOTS_MOCR_MODEL_NAME", "rednote-hilab/dots.mocr")
DOTS_MAX_NEW_TOKENS = int(os.getenv("DOTS_MAX_NEW_TOKENS", "8192"))
DOTS_DEVICE = os.getenv("DOTS_DEVICE") or None

# DotOCR layout categories mapped to Raqim heading blocks.
HEADING_CATEGORIES = {"title", "section-header", "sub_title", "subtitle", "header"}
# Categories with no text content for the document body.
SKIP_CATEGORIES = {"picture"}

_DOTS = None


def _load():
    """Lazily load dots.mocr (model + processor) once per process."""
    global _DOTS
    if _DOTS is None:
        try:
            import test_dots_ocr as dots

            model, processor, device = dots.load_model_and_processor(
                DOTS_MOCR_MODEL_NAME, DOTS_DEVICE
            )
            _DOTS = (dots, model, processor, device)
        except DotsOCRError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DotsOCRError(f"تعذر تحميل DotOCR (dots.mocr): {exc}") from exc
    return _DOTS


def _parse_layout_blocks(raw_output: str) -> List[Dict]:
    """Parse dots.mocr's raw output into a list of layout-block dicts."""
    candidate = (raw_output or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", candidate, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                parsed = value
                break

    if not isinstance(parsed, list):
        return []
    return [block for block in parsed if isinstance(block, dict)]


def _run_dots_layout(image_path: str) -> List[Dict]:
    dots, model, processor, device = _load()
    raw = dots.run_inference(
        model, processor, device, image_path, dots.PROMPT_LAYOUT_ALL, DOTS_MAX_NEW_TOKENS
    )
    return _parse_layout_blocks(raw)


def _bbox_source_box(bbox, width: int, height: int):
    """Convert a DotOCR pixel bbox [x1,y1,x2,y2] into a Raqim source_box dict."""
    if not bbox:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in list(bbox)[:4])
    except (TypeError, ValueError):
        return None
    x = max(0, min(int(min(x1, x2)), width))
    y = max(0, min(int(min(y1, y2)), height))
    w = max(1, min(int(abs(x2 - x1)), width))
    h = max(1, min(int(abs(y2 - y1)), height))
    return {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "original_width": int(width),
        "original_height": int(height),
    }


def _reading_order_key(block: Dict):
    """Sort key for human reading order using bbox: top-to-bottom, then left-to-right."""
    bbox = block.get("bbox") or [0, 0, 0, 0]
    try:
        x1, y1 = float(bbox[0]), float(bbox[1])
    except (TypeError, ValueError, IndexError):
        x1, y1 = 0.0, 0.0
    # Quantize the vertical position into coarse rows so blocks on the same line
    # are grouped, then order within a row by horizontal position.
    return (round(y1 / 20.0), x1)


def _blocks_to_words(blocks: List[Dict], width: int, height: int) -> List[Dict]:
    """Reconstruct Raqim's tagged word list from DotOCR layout blocks."""
    ordered = sorted(blocks, key=_reading_order_key)
    words: List[Dict] = []

    for block_id, block in enumerate(ordered):
        category = (block.get("category") or "").strip().lower()
        if category in SKIP_CATEGORIES:
            continue

        text = block.get("text")
        if text is None:
            continue

        source_box = _bbox_source_box(block.get("bbox"), width, height)
        y_start = source_box["y"] + 4 if source_box else None

        table_match = re.search(
            r"<table[^>]*>.*?</table>", str(text), flags=re.DOTALL | re.IGNORECASE
        )
        if category == "table" or table_match:
            # Tables: convert HTML directly into real (merged-aware) cells.
            html = table_match.group(0) if table_match else str(text)
            cells = ocr_model._parse_html_table_cells(html)
            seg_words = ocr_model._table_cells_to_words(
                cells, block_id + 1, width, height, y_start=y_start
            )
            if source_box:
                ocr_model._assign_intra_segment_source_boxes(seg_words, source_box, width, height)
            block_type = "table"
        else:
            seg_text = ocr_model._clean_text(str(text))
            if not seg_text:
                continue
            seg_words = ocr_model._words_from_structured_text(
                seg_text, width, height, y_start=y_start
            )
            if source_box:
                ocr_model._assign_intra_segment_source_boxes(seg_words, source_box, width, height)
            block_type = "heading" if category in HEADING_CATEGORIES else "text"

        for word in seg_words:
            word["index"] = len(words)
            word["block_id"] = block_id
            word["block_type"] = block_type
            word["dots_category"] = category
            words.append(word)

    return words


def ocr_with_highlighting(file_path, output_folder) -> List[Dict]:
    """Run DotOCR on a PDF/image and return Raqim review-compatible page words."""
    output_dir = ocr_model._prepare_output_folder(output_folder)
    try:
        pages = ocr_model._load_pages(file_path)
    except Exception as exc:  # noqa: BLE001
        raise DotsOCRError(f"تعذر قراءة ملف OCR: {exc}") from exc

    results: List[Dict] = []
    for page_number, image in enumerate(pages, start=1):
        preview_path = output_dir / f"original_page_{page_number}.png"
        image.save(preview_path, format="PNG")
        width, height = image.size

        with tempfile.TemporaryDirectory() as work_dir:
            page_path = os.path.join(work_dir, "page.png")
            image.convert("RGB").save(page_path)
            try:
                blocks = _run_dots_layout(page_path)
            except DotsOCRError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise DotsOCRError(
                    f"فشل DotOCR أثناء تحليل الصفحة {page_number}: {exc}"
                ) from exc

        words = _blocks_to_words(blocks, width, height)
        if not words:
            raise DotsOCRError(f"DotOCR لم يُعد أي محتوى نصي للصفحة {page_number}.")

        table_blocks = sum(1 for w in words if w.get("block_type") == "table")
        print(
            f"✅ DotOCR استخرج {len(words)} عنصرًا من الصفحة {page_number} "
            f"({len(blocks)} كتلة، خلايا جداول={table_blocks})."
        )
        results.append(
            {
                "page_number": page_number,
                "image_path": str(preview_path),
                "text": words,
                "ocr_engine": "dots",
                "ocr_engine_label": f"DotOCR ({DOTS_MOCR_MODEL_NAME})",
                "ocr_provider": "dots_local",
                "qari_attempted": False,
                "fallback_used": False,
                "fallback_reason": "",
            }
        )

    return results
