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

Phases implemented so far:

* Phase 1: detect ``Title`` / ``Section-header`` regions and convert the matching
  DeepSeek blocks into ``block_type == "heading"``.
* Phase 2: detect ``Table`` regions and, where DeepSeek only produced plain text,
  rebuild a real Raqim table block from DotOCR's HTML table output (DeepSeek
  tables that were already detected are kept untouched).
* Phase 3: detect ``Picture`` regions (DeepSeek emits no text for images) and
  insert an editable placeholder block at the right reading position, plus a
  TOC-friendly heading hierarchy (``heading_level`` 1 for Title, 2 for
  Section-header) consumed by ``docx_builder``.

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
TABLE_CATEGORIES = {"table"}
PICTURE_CATEGORIES = {"picture", "figure", "image"}

# Minimum fraction of a DeepSeek block that must fall inside a DotOCR region for
# the block to inherit that region's structural role.
DEFAULT_OVERLAP_THRESHOLD = 0.5

# Placeholder text used for a detected Picture region (DeepSeek emits no text for
# images, so we inject a clearly-marked, editable placeholder block instead).
PICTURE_PLACEHOLDER = "[صورة]"


def _heading_level_for(category: str) -> int:
    """TOC-friendly heading level: Title -> 1, Section-header/others -> 2."""
    return 1 if category in TITLE_CATEGORIES else 2


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
# Table reconstruction from DotOCR HTML (Phase 2).
# ---------------------------------------------------------------------------
def _extract_table_html(text) -> Optional[str]:
    """Return the ``<table>...</table>`` fragment from a DotOCR cell, if any."""
    if not text:
        return None
    match = re.search(r"<table[^>]*>.*?</table>", str(text), flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0)
    # DotOCR may emit a bare table without the wrapping tag for some pages.
    if "<tr" in str(text).lower():
        return str(text)
    return None


def _table_words_from_html(html: str, table_id: int, width: float, height: float, y_start: Optional[int]) -> List[Dict]:
    """Build Raqim table words from a DotOCR HTML table (lazy ocr_model import).

    Reuses ``ocr_model``'s battle-tested HTML-table parser and RTL cell layout so
    the resulting cells (``table_id`` / ``table_row`` / ``table_col`` / spans)
    are identical in shape to DeepSeek's own tables — the review UI and
    ``docx_builder`` render them with no special-casing.
    """
    import ocr_model

    cells = ocr_model._parse_html_table_cells(html)
    if not cells:
        return []
    return ocr_model._table_cells_to_words(
        cells, table_id, int(width) or 1000, int(height) or 1000, y_start=y_start
    )


def _apply_table_fusion(
    blocks: List[Dict],
    regions: Sequence[Dict],
    width: float,
    height: float,
    threshold: float,
) -> Tuple[List[Dict], int]:
    """Replace DeepSeek text blocks that fall inside a DotOCR table region.

    Returns the new block list and the number of tables reconstructed. Tables
    DeepSeek already detected (``block_type == "table"``) are kept untouched so
    DeepSeek stays the source of truth where it succeeded.
    """
    table_regions = [r for r in regions if r["category"] in TABLE_CATEGORIES and _extract_table_html(r.get("text"))]
    if not table_regions:
        return blocks, 0

    new_blocks: List[Dict] = []
    handled_regions: set = set()
    table_count = 0

    for block in blocks:
        rect = block.get("rect")
        matched_idx = None
        if rect is not None and block["block_type"] != "table":
            for region_idx, region in enumerate(table_regions):
                if _containment(rect, region["rect"]) >= threshold:
                    matched_idx = region_idx
                    break

        if matched_idx is None:
            new_blocks.append(block)
            continue

        if matched_idx in handled_regions:
            # Region already converted; drop this extra text fragment so we do
            # not duplicate the table content.
            continue

        region = table_regions[matched_idx]
        html = _extract_table_html(region["text"])
        y_start = int(region["rect"][1] * height) + 4
        table_words = _table_words_from_html(html, len(new_blocks) + 1, width, height, y_start)
        if not table_words:
            # Could not parse the HTML table; keep the DeepSeek text block.
            new_blocks.append(block)
            continue

        handled_regions.add(matched_idx)
        for word in table_words:
            word["block_type"] = "table"
            word["layout_source"] = "dotocr"
            word["dots_category"] = "table"
        new_blocks.append(
            {"block_id": None, "block_type": "table", "words": table_words, "rect": region["rect"]}
        )
        table_count += 1

    return new_blocks, table_count


# ---------------------------------------------------------------------------
# Picture detection (Phase 3).
# ---------------------------------------------------------------------------
def _picture_placeholder_words(width: float, height: float, y_start: Optional[int]) -> List[Dict]:
    """Build a single editable placeholder word for a detected Picture region."""
    import ocr_model

    pw = int(width) or 1000
    ph = int(height) or 1000
    margin_x = max(18, pw // 35)
    y = margin_x if y_start is None else max(margin_x, int(y_start))
    item = ocr_model._word_item(
        word=PICTURE_PLACEHOLDER,
        confidence=ocr_model.DEEPSEEK_APPROX_CONFIDENCE,
        x=margin_x,
        y=y,
        w=pw - 2 * margin_x,
        h=max(40, ph // 12),
        width=pw,
        height=ph,
        index=0,
    )
    item["line_index"] = 0
    item["is_picture"] = True
    return [item]


def _insert_block_by_position(blocks: List[Dict], new_block: Dict) -> None:
    """Insert ``new_block`` into ``blocks`` preserving top-to-bottom reading order."""
    new_rect = new_block.get("rect")
    if new_rect is None:
        blocks.append(new_block)
        return
    new_top = new_rect[1]
    for idx, block in enumerate(blocks):
        rect = block.get("rect")
        if rect is not None and rect[1] > new_top:
            blocks.insert(idx, new_block)
            return
    blocks.append(new_block)


def _apply_picture_fusion(
    blocks: List[Dict],
    regions: Sequence[Dict],
    width: float,
    height: float,
    threshold: float,
) -> int:
    """Insert placeholder blocks for DotOCR Picture regions; return the count.

    A picture region that is already covered by a real content block (e.g. a
    figure with an embedded caption DeepSeek read as text) is skipped so we do
    not duplicate content.
    """
    picture_regions = [r for r in regions if r["category"] in PICTURE_CATEGORIES]
    picture_count = 0
    for region in picture_regions:
        overlapped = any(
            block.get("rect") is not None
            and _containment(region["rect"], block["rect"]) >= threshold
            for block in blocks
        )
        if overlapped:
            continue
        y_start = int(region["rect"][1] * height) + 4
        placeholder = _picture_placeholder_words(width, height, y_start)
        for word in placeholder:
            word["block_type"] = "picture"
            word["layout_source"] = "dotocr"
            word["dots_category"] = "picture"
        _insert_block_by_position(
            blocks,
            {"block_id": None, "block_type": "picture", "words": placeholder, "rect": region["rect"]},
        )
        picture_count += 1
    return picture_count


# ---------------------------------------------------------------------------
# Public merge entry point.
# ---------------------------------------------------------------------------
def enhance_layout_with_dotocr(
    pages: Sequence[Dict],
    layout_pages: Sequence[Sequence[Dict]],
    *,
    enable_headings: bool = True,
    enable_tables: bool = True,
    enable_pictures: bool = True,
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
    enable_tables:
        Phase 2 switch for Table detection (reuse DotOCR HTML structure).
    enable_pictures:
        Phase 3 switch for Picture detection (insert editable placeholders).
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
        table_count = 0
        picture_count = 0

        # ---- Phase 1: Title / Section-header detection -------------------
        if enable_headings:
            for block in blocks:
                if block["block_type"] == "table" or block.get("rect") is None:
                    continue
                region = _best_region(block["rect"], regions, HEADING_CATEGORIES, overlap_threshold)
                if region is None:
                    continue
                # Phase 3: TOC-friendly hierarchy (Title -> 1, Section -> 2).
                level = _heading_level_for(region["category"])
                for word in block["words"]:
                    word["block_type"] = "heading"
                    word["heading_level"] = level
                    word["layout_source"] = "dotocr"
                    word["dots_category"] = region["category"]
                block["block_type"] = "heading"
                heading_count += 1

        # ---- Phase 2: Table detection (reuse DotOCR HTML structure) ------
        if enable_tables:
            blocks, table_count = _apply_table_fusion(blocks, regions, width, height, overlap_threshold)

        # ---- Phase 3: Picture detection ---------------------------------
        if enable_pictures:
            picture_count = _apply_picture_fusion(blocks, regions, width, height, overlap_threshold)

        page["text"] = _flatten_blocks(blocks)
        _mark_page_fused(page)
        print(
            f"🔗 Layout fusion page {page.get('page_number', page_index + 1)}: "
            f"headings={heading_count}, tables={table_count}, pictures={picture_count}."
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
