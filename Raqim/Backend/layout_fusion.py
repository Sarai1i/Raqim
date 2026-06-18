"""DeepSeek + DotOCR layout-fusion engine for Raqim.

This module implements an **experimental fusion pipeline** in which DeepSeek-OCR-2
stays the primary OCR engine (the *source of truth for text*) and DotOCR
(``dots.mocr``) is used **only as a document-layout post-processing engine**.

Pipeline
--------
::

    PDF ──> DeepSeek OCR ──> OCR text output (words + boxes, Raqim structure)
        └─> DotOCR       ──> Layout JSON (Title / Section-header / Table / Picture)
                              │
                              ▼
                     enhance_layout_with_dotocr(...)
                              │
                              ▼
                     fused Raqim page structure

Hard rules (enforced here)
--------------------------
* DeepSeek remains the **source of truth for text**. The fusion never rewrites a
  DeepSeek word's ``word`` value from DotOCR for normal text/headings.
* DotOCR is used for **structure detection only** — it re-tags DeepSeek blocks
  (``block_type``).
* The output is the SAME page/word structure produced by ``ocr_model`` /
  ``dots_ocr_engine``, so the review UI and ``docx_builder`` keep working
  unchanged.
* If DotOCR is unavailable or fails, the DeepSeek-only result is returned
  untouched (graceful degradation).

Phase 1 (this commit): detect ``Title`` / ``Section-header`` regions and convert
the matching DeepSeek blocks into ``block_type == "heading"``. Tables and
pictures are handled in later phases.

The expensive merge orchestration (``run_fusion_ocr``) lazily imports the heavy
engines, while the pure merge logic (``enhance_layout_with_dotocr`` and helpers)
has no model dependencies and is unit-testable on its own.
"""

from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# DotOCR layout categories (normalized to lower-case, whitespace folded).
# ---------------------------------------------------------------------------
TITLE_CATEGORIES = {"title"}
SECTION_CATEGORIES = {"section-header", "sectionheader", "section_header", "subtitle", "sub-title", "sub_title", "header"}
HEADING_CATEGORIES = TITLE_CATEGORIES | SECTION_CATEGORIES

# Minimum fraction of a DeepSeek block that must fall inside a DotOCR region for
# the block to inherit that region's structural role.
DEFAULT_OVERLAP_THRESHOLD = 0.5


def _normalize_category(category) -> str:
    """Lower-case a DotOCR category and fold whitespace."""
    return re.sub(r"\s+", "", (category or "").strip().lower())


# ---------------------------------------------------------------------------
# Geometry helpers (all boxes normalized to [0, 1] rectangles (x0, y0, x1, y1)).
# ---------------------------------------------------------------------------
def _rect_from_xywh(box: Dict, width: float, height: float) -> Optional[Tuple[float, float, float, float]]:
    """Normalize a Raqim ``{x, y, w, h}`` box to a [0,1] rectangle."""
    if not box or width <= 0 or height <= 0:
        return None
    try:
        x = float(box.get("x", 0))
        y = float(box.get("y", 0))
        w = float(box.get("w", 0))
        h = float(box.get("h", 0))
    except (TypeError, ValueError):
        return None
    return (x / width, y / height, (x + w) / width, (y + h) / height)


def _rect_from_bbox(bbox: Sequence, width: float, height: float) -> Optional[Tuple[float, float, float, float]]:
    """Normalize a DotOCR ``[x1, y1, x2, y2]`` pixel bbox to a [0,1] rectangle."""
    if not bbox or width <= 0 or height <= 0:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in list(bbox)[:4])
    except (TypeError, ValueError):
        return None
    return (
        min(x1, x2) / width,
        min(y1, y2) / height,
        max(x1, x2) / width,
        max(y1, y2) / height,
    )


def _area(rect: Tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _intersection_area(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _containment(inner: Tuple[float, float, float, float], outer: Tuple[float, float, float, float]) -> float:
    """Fraction of ``inner``'s area that lies within ``outer`` (0..1)."""
    inner_area = _area(inner)
    if inner_area <= 0:
        return 0.0
    return _intersection_area(inner, outer) / inner_area


def _union_rect(rects: Sequence[Tuple[float, float, float, float]]) -> Optional[Tuple[float, float, float, float]]:
    rects = [r for r in rects if r is not None]
    if not rects:
        return None
    return (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )


# ---------------------------------------------------------------------------
# Page-dimension + block-grouping helpers.
# ---------------------------------------------------------------------------
def _page_dimensions(words: Sequence[Dict]) -> Tuple[float, float]:
    """Recover the page pixel dimensions from a page's word boxes."""
    for word in words:
        for key in ("source_box", "bounding_box"):
            box = word.get(key) or {}
            width = box.get("original_width")
            height = box.get("original_height")
            if width and height:
                return float(width), float(height)
    return 0.0, 0.0


def _word_rect(word: Dict, width: float, height: float) -> Optional[Tuple[float, float, float, float]]:
    """Prefer the real grounding ``source_box``; fall back to the layout box."""
    rect = _rect_from_xywh(word.get("source_box"), width, height)
    if rect is None:
        rect = _rect_from_xywh(word.get("bounding_box"), width, height)
    return rect


def _group_blocks(words: Sequence[Dict]) -> List[Dict]:
    """Group a page's words into ordered blocks keyed by ``block_id``.

    Preserves the original ordering and keeps the words list per block so the
    fusion can re-tag, replace, or splice blocks and then flatten back.
    """
    blocks: List[Dict] = []
    for word in words:
        bid = word.get("block_id")
        if blocks and blocks[-1]["block_id"] == bid:
            blocks[-1]["words"].append(word)
        else:
            blocks.append(
                {
                    "block_id": bid,
                    "block_type": word.get("block_type", "text"),
                    "words": [word],
                }
            )
    return blocks


def _block_rect(block: Dict, width: float, height: float) -> Optional[Tuple[float, float, float, float]]:
    rects = [_word_rect(w, width, height) for w in block["words"]]
    return _union_rect(rects)


def _flatten_blocks(blocks: Sequence[Dict]) -> List[Dict]:
    """Flatten ordered blocks back into a Raqim word list.

    Re-assigns sequential ``block_id`` and ``index`` so downstream consumers
    (review UI grouping, ``docx_builder``) see a clean, consistent structure.
    """
    words: List[Dict] = []
    for block_id, block in enumerate(blocks):
        block_type = block.get("block_type", "text")
        for word in block["words"]:
            word["block_id"] = block_id
            word["block_type"] = block_type
            word["index"] = len(words)
            words.append(word)
    return words


# ---------------------------------------------------------------------------
# DotOCR layout-region extraction.
# ---------------------------------------------------------------------------
def _layout_regions(layout_blocks: Sequence[Dict], width: float, height: float) -> List[Dict]:
    """Normalize raw DotOCR blocks into ``{category, rect, text}`` regions."""
    regions: List[Dict] = []
    for block in layout_blocks or []:
        if not isinstance(block, dict):
            continue
        rect = _rect_from_bbox(block.get("bbox"), width, height)
        if rect is None:
            continue
        regions.append(
            {
                "category": _normalize_category(block.get("category")),
                "rect": rect,
                "text": block.get("text"),
            }
        )
    return regions


def _best_region(
    block_rect: Tuple[float, float, float, float],
    regions: Sequence[Dict],
    categories: set,
    threshold: float,
) -> Optional[Dict]:
    """Return the region (of the given categories) best containing ``block_rect``."""
    best = None
    best_score = threshold
    for region in regions:
        if region["category"] not in categories:
            continue
        score = _containment(block_rect, region["rect"])
        if score >= best_score:
            best_score = score
            best = region
    return best


# ---------------------------------------------------------------------------
# Public merge entry point.
# ---------------------------------------------------------------------------
def enhance_layout_with_dotocr(
    pages: Sequence[Dict],
    layout_pages: Sequence[Sequence[Dict]],
    *,
    enable_headings: bool = True,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> List[Dict]:
    """Fuse DeepSeek OCR pages with DotOCR layout regions.

    Parameters
    ----------
    pages:
        DeepSeek-OCR-2 page dicts (Raqim structure). Treated as the source of
        truth for text; never mutated in place (a deep copy is returned).
    layout_pages:
        Per-page list (parallel to ``pages``) of raw DotOCR layout blocks, each a
        dict with ``category``, ``bbox`` ([x1, y1, x2, y2] in page pixels) and
        ``text``. Use an empty list for pages where DotOCR produced nothing.
    enable_headings:
        Phase 1 switch for Title / Section-header detection.
    overlap_threshold:
        Minimum containment fraction for a DeepSeek block to inherit a DotOCR
        region's role.

    Returns
    -------
    A new list of fused page dicts with the same structure as the input.
    """
    fused_pages = copy.deepcopy(list(pages))

    for page_index, page in enumerate(fused_pages):
        words = page.get("text") or []
        if not words:
            continue

        layout_blocks = layout_pages[page_index] if page_index < len(layout_pages) else []
        width, height = _page_dimensions(words)
        if width <= 0 or height <= 0:
            # Without page dimensions we cannot match boxes; keep DeepSeek as-is.
            continue

        regions = _layout_regions(layout_blocks, width, height)
        if not regions:
            continue

        blocks = _group_blocks(words)
        for block in blocks:
            block["rect"] = _block_rect(block, width, height)

        heading_count = 0

        # ---- Phase 1: Title / Section-header detection -------------------
        if enable_headings:
            for block in blocks:
                if block["block_type"] == "table" or block.get("rect") is None:
                    continue
                region = _best_region(block["rect"], regions, HEADING_CATEGORIES, overlap_threshold)
                if region is None:
                    continue
                for word in block["words"]:
                    word["block_type"] = "heading"
                    word["layout_source"] = "dotocr"
                    word["dots_category"] = region["category"]
                block["block_type"] = "heading"
                heading_count += 1

        page["text"] = _flatten_blocks(blocks)
        _mark_page_fused(page)
        print(
            f"🔗 Layout fusion page {page.get('page_number', page_index + 1)}: "
            f"headings={heading_count}."
        )

    return fused_pages


def _mark_page_fused(page: Dict) -> None:
    """Tag a page so the app/UI can tell DeepSeek text was fused with DotOCR."""
    base_label = page.get("ocr_engine_label", "DeepSeek-OCR-2")
    if "DotOCR" not in base_label:
        page["ocr_engine_label"] = f"{base_label} + DotOCR layout"
    page["layout_engine"] = "dots"
    page["fusion"] = True


# ---------------------------------------------------------------------------
# Orchestration: run DeepSeek (text) + DotOCR (layout) and fuse them.
# ---------------------------------------------------------------------------
def run_fusion_ocr(file_path, output_folder) -> List[Dict]:
    """Run the full fusion pipeline and return Raqim review-compatible pages.

    DeepSeek-OCR-2 is always run first and is the source of truth for text. The
    DotOCR layout pass is best-effort: any failure (missing deps, no GPU, model
    error) is caught and the DeepSeek-only result is returned unchanged.
    """
    import ocr_model

    pages = ocr_model.ocr_with_highlighting(file_path, output_folder)
    print("✅ DeepSeek OCR completed")

    if not pages:
        return pages

    try:
        layout_pages = _collect_dotocr_layout(pages)
        print("✅ DotOCR layout completed")
    except Exception as exc:  # noqa: BLE001 — never let layout break OCR.
        print(f"⚠️ DotOCR layout failed; returning DeepSeek-only result: {exc}")
        return pages

    if not any(layout_pages):
        print("⚠️ DotOCR returned no layout regions; returning DeepSeek-only result.")
        return pages

    try:
        fused = enhance_layout_with_dotocr(pages, layout_pages)
        print("✅ Layout fusion completed")
        return fused
    except Exception as exc:  # noqa: BLE001 — fall back to DeepSeek on any merge error.
        print(f"⚠️ Layout fusion failed; returning DeepSeek-only result: {exc}")
        return pages


def _collect_dotocr_layout(pages: Sequence[Dict]) -> List[List[Dict]]:
    """Run the DotOCR layout model on each already-rendered page image.

    DeepSeek saves each page to ``page['image_path']`` and reports word boxes in
    that same pixel space, so running DotOCR on the identical image keeps both
    coordinate systems aligned for box matching.
    """
    import dots_ocr_engine

    layout_pages: List[List[Dict]] = []
    for page in pages:
        image_path = page.get("image_path")
        if not image_path:
            layout_pages.append([])
            continue
        try:
            blocks = dots_ocr_engine._run_dots_layout(image_path)
        except Exception as exc:  # noqa: BLE001 — one page failing must not abort.
            page_no = page.get("page_number", "?")
            print(f"⚠️ DotOCR layout failed on page {page_no}: {exc}")
            blocks = []
        layout_pages.append(blocks)
    return layout_pages
