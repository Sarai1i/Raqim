"""DeepSeek + DotOCR layout fusion for Raqim (Phase 1).

Raqim's primary OCR engine is DeepSeek-OCR-2. DotOCR (dots.mocr) is a strong
*layout* analyzer. This module fuses the two: it keeps **all DeepSeek text**
untouched and uses DotOCR **only for structure**, so DeepSeek's superior Arabic
text recognition is preserved while DotOCR's layout understanding improves the
block classification.

Phase 1 scope (intentionally minimal):

* Run DeepSeek OCR normally (done by the caller).
* Run DotOCR layout analysis on the same pages (done by the caller).
* Use DotOCR ONLY for structure -- never its text.
* Match DeepSeek blocks against DotOCR blocks by bounding-box overlap.
* When a DeepSeek block overlaps a DotOCR ``Title`` / ``Section-header`` block,
  promote that DeepSeek block to ``block_type == "heading"``.

Explicitly NOT handled in Phase 1: tables, images/pictures, DOCX-builder changes
and UI changes. Existing DeepSeek ``table`` blocks are left exactly as-is.

Both ``deepseek_pages`` and ``dotocr_pages`` use Raqim's standard page structure
(the list of pages returned by an engine's ``ocr_with_highlighting``), i.e. each
page is a dict with a ``text`` list of word dicts tagged with ``block_id`` /
``block_type`` / ``bounding_box`` / ``source_box`` (and ``dots_category`` for
DotOCR words).

Backward compatibility: the input ``deepseek_pages`` is never mutated; a fused
copy is returned. If DotOCR output is missing or fusion fails for any reason, the
original DeepSeek pages are returned unchanged.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# DotOCR layout categories that mark a heading block. Phase 1 only promotes
# headings (Title / Section-header); everything else is left untouched.
HEADING_CATEGORIES = {"title", "section-header"}

# A DeepSeek block is promoted to a heading when it overlaps a DotOCR heading
# block by at least one of these measures. IoU is robust when the two boxes are
# similar in size; the containment ratio (intersection / DeepSeek-block-area)
# catches the common case where the DotOCR heading box is larger than a single
# DeepSeek text line.
DEFAULT_IOU_THRESHOLD = 0.30
DEFAULT_CONTAINMENT_THRESHOLD = 0.50

# Block types that must never be reclassified in Phase 1.
_PROTECTED_BLOCK_TYPES = {"table"}

_Box = Tuple[float, float, float, float]  # (x1, y1, x2, y2), normalized to [0, 1]


def _normalize_category(value) -> str:
    """Normalize a DotOCR category, e.g. ``"Section_header"`` -> ``"section-header"``."""
    normalized = re.sub(r"[\s_]+", "-", str(value or "").strip().lower())
    return normalized


def _word_box(word: Dict) -> Optional[_Box]:
    """Return a word's box normalized to [0, 1], preferring the real ``source_box``.

    Falls back to the approximate ``bounding_box`` when no source box exists.
    Returns ``None`` when the word carries no usable geometry.
    """
    box = word.get("source_box") or word.get("bounding_box")
    if not isinstance(box, dict):
        return None
    try:
        x = float(box.get("x", 0))
        y = float(box.get("y", 0))
        w = float(box.get("w", 0))
        h = float(box.get("h", 0))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None

    # Normalize so DeepSeek and DotOCR boxes are comparable even if their pixel
    # spaces differ. Both engines set original_width/height to the page size.
    ow = float(box.get("original_width") or 0) or None
    oh = float(box.get("original_height") or 0) or None
    if ow and oh:
        return (x / ow, y / oh, (x + w) / ow, (y + h) / oh)
    return (x, y, x + w, y + h)


def _union_box(boxes: Sequence[_Box]) -> Optional[_Box]:
    """Union of several normalized boxes (the bounding box of a whole block)."""
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    return (x1, y1, x2, y2)


def _area(box: _Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection_area(a: _Box, b: _Box) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


def _iou(a: _Box, b: _Box) -> float:
    inter = _intersection_area(a, b)
    if inter <= 0:
        return 0.0
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _containment(inner: _Box, outer: _Box) -> float:
    """Fraction of ``inner`` covered by ``outer`` (intersection / area(inner))."""
    inner_area = _area(inner)
    if inner_area <= 0:
        return 0.0
    return _intersection_area(inner, outer) / inner_area


def _group_blocks(page: Dict) -> List[Dict]:
    """Group a page's words into blocks (consecutive runs of the same ``block_id``).

    Mirrors how ``docx_builder`` groups words, and returns each block's normalized
    bounding box plus its dominant DotOCR category (when present).
    """
    words = page.get("text") or []
    blocks: List[Dict] = []
    for word in words:
        bid = word.get("block_id")
        btype = word.get("block_type", "text")
        if blocks and blocks[-1]["id"] == bid and blocks[-1]["type"] == btype:
            blocks[-1]["words"].append(word)
        else:
            blocks.append({"id": bid, "type": btype, "words": [word]})

    for block in blocks:
        block["bbox"] = _union_box([_word_box(w) for w in block["words"]])
        block["category"] = _block_category(block["words"])
    return blocks


def _block_category(words: Sequence[Dict]) -> str:
    """Dominant normalized DotOCR category for a block (falls back to block_type)."""
    counts: Dict[str, int] = {}
    for word in words:
        raw = word.get("dots_category")
        if raw is None:
            # No explicit DotOCR category: infer from block_type (a DotOCR heading
            # block already carries block_type == "heading").
            raw = "section-header" if word.get("block_type") == "heading" else word.get("block_type", "")
        category = _normalize_category(raw)
        if category:
            counts[category] = counts.get(category, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def _dotocr_pages_by_number(dotocr_pages: Sequence[Dict]) -> Dict[int, Dict]:
    mapping: Dict[int, Dict] = {}
    for index, page in enumerate(dotocr_pages):
        if not isinstance(page, dict):
            continue
        number = page.get("page_number", index + 1)
        mapping[number] = page
    return mapping


def _fuse_page(
    deepseek_page: Dict,
    dotocr_page: Optional[Dict],
    iou_threshold: float,
    containment_threshold: float,
) -> int:
    """Promote matching DeepSeek blocks to headings in place. Returns #promotions."""
    if not isinstance(dotocr_page, dict):
        return 0

    dot_heading_boxes = [
        block["bbox"]
        for block in _group_blocks(dotocr_page)
        if block["bbox"] and block["category"] in HEADING_CATEGORIES
    ]
    if not dot_heading_boxes:
        return 0

    promotions = 0
    for ds_block in _group_blocks(deepseek_page):
        if ds_block["type"] in _PROTECTED_BLOCK_TYPES:
            continue
        ds_box = ds_block["bbox"]
        if not ds_box:
            continue

        matched = any(
            _iou(ds_box, dot_box) >= iou_threshold
            or _containment(ds_box, dot_box) >= containment_threshold
            for dot_box in dot_heading_boxes
        )
        if not matched:
            continue

        if ds_block["type"] != "heading":
            promotions += 1
        for word in ds_block["words"]:
            word["block_type"] = "heading"
    return promotions


def enhance_layout_with_dotocr(
    deepseek_pages: Sequence[Dict],
    dotocr_pages: Optional[Sequence[Dict]],
    *,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    containment_threshold: float = DEFAULT_CONTAINMENT_THRESHOLD,
) -> List[Dict]:
    """Fuse DeepSeek OCR output with DotOCR layout structure (Phase 1: headings).

    Args:
        deepseek_pages: Raqim pages from the DeepSeek engine (the text source of
            truth; never mutated).
        dotocr_pages: Raqim pages from the DotOCR engine, used only for structure.
            When ``None``/empty (e.g. DotOCR failed), the DeepSeek pages are
            returned unchanged.
        iou_threshold: minimum IoU between a DeepSeek block and a DotOCR heading
            block to count as a match.
        containment_threshold: minimum fraction of a DeepSeek block covered by a
            DotOCR heading block to count as a match.

    Returns:
        A new list of fused pages (a copy of ``deepseek_pages`` with matching
        blocks re-tagged ``block_type == "heading"``).
    """
    logger.info("DeepSeek OCR completed")

    base_pages = list(deepseek_pages or [])

    if not dotocr_pages:
        logger.warning("DotOCR layout unavailable; using DeepSeek output unchanged")
        return base_pages

    logger.info("DotOCR layout completed")

    try:
        fused_pages = copy.deepcopy(base_pages)
        dot_by_number = _dotocr_pages_by_number(dotocr_pages)

        total_promotions = 0
        for index, ds_page in enumerate(fused_pages):
            if not isinstance(ds_page, dict):
                continue
            page_number = ds_page.get("page_number", index + 1)
            dot_page = dot_by_number.get(page_number)
            if dot_page is None and index < len(dotocr_pages):
                # Fall back to positional pairing when page numbers don't line up.
                dot_page = dotocr_pages[index]
            total_promotions += _fuse_page(
                ds_page, dot_page, iou_threshold, containment_threshold
            )
    except Exception as exc:  # noqa: BLE001 - never break OCR because of fusion.
        logger.warning("Layout fusion failed (%s); using DeepSeek output unchanged", exc)
        return base_pages

    logger.info("Layout fusion completed (%d block(s) promoted to heading)", total_promotions)
    return fused_pages
