"""Phase 1 tests for DeepSeek + DotOCR layout fusion (heading detection).

These tests are pure-Python: they build synthetic Raqim page structures and do
NOT require an OCR model / GPU.
"""

import logging

from layout_fusion import enhance_layout_with_dotocr

PAGE_W = 1000
PAGE_H = 1000


def _box(x, y, w, h):
    return {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "original_width": PAGE_W,
        "original_height": PAGE_H,
    }


def _word(index, block_id, block_type, text, box, dots_category=None):
    word = {
        "index": index,
        "block_id": block_id,
        "block_type": block_type,
        "word": text,
        "corrected_word": "",
        "source_box": box,
        "bounding_box": box,
    }
    if dots_category is not None:
        word["dots_category"] = dots_category
    return word


def _deepseek_pages():
    """DeepSeek output: two TEXT blocks (DeepSeek does not detect these headings)."""
    return [
        {
            "page_number": 1,
            "image_path": "uploads/original_page_1.png",
            "text": [
                # Block 0: visually a title near the top of the page.
                _word(0, 0, "text", "الفصل", _box(100, 50, 150, 40)),
                _word(1, 0, "text", "الأول", _box(260, 50, 140, 40)),
                # Block 1: ordinary body paragraph lower on the page.
                _word(2, 1, "text", "هذا", _box(100, 200, 120, 30)),
                _word(3, 1, "text", "نص", _box(230, 200, 120, 30)),
                _word(4, 1, "text", "عادي", _box(360, 200, 200, 30)),
            ],
            "ocr_engine": "deepseek",
        }
    ]


def _dotocr_pages():
    """DotOCR output: a Title block over block 0, plain Text over block 1."""
    return [
        {
            "page_number": 1,
            "image_path": "uploads/original_page_1.png",
            "text": [
                # DotOCR text differs on purpose: it must NOT be used.
                _word(0, 0, "heading", "DOTOCR-TITLE", _box(95, 45, 320, 50),
                      dots_category="Title"),
                _word(1, 1, "text", "DOTOCR-BODY", _box(95, 195, 480, 40),
                      dots_category="Text"),
            ],
            "ocr_engine": "dots",
        }
    ]


def _block_type_for(page, block_id):
    return next(w["block_type"] for w in page["text"] if w["block_id"] == block_id)


def _block_text(page, block_id):
    return " ".join(w["word"] for w in page["text"] if w["block_id"] == block_id)


def test_heading_promoted_from_dotocr_title():
    ds = _deepseek_pages()
    fused = enhance_layout_with_dotocr(ds, _dotocr_pages())

    page = fused[0]
    # Block 0 overlaps a DotOCR "Title" -> promoted to heading.
    assert _block_type_for(page, 0) == "heading"
    # Block 1 overlaps only plain text -> stays text.
    assert _block_type_for(page, 1) == "text"

    # DotOCR text must NOT leak into the fused output: DeepSeek text is kept.
    assert _block_text(page, 0) == "الفصل الأول"
    assert "DOTOCR" not in _block_text(page, 0)

    # Backward compatibility: the input pages are not mutated.
    assert _block_type_for(ds[0], 0) == "text"


def test_section_header_category_is_promoted():
    ds = _deepseek_pages()
    dot = _dotocr_pages()
    dot[0]["text"][0]["dots_category"] = "Section-header"
    fused = enhance_layout_with_dotocr(ds, dot)
    assert _block_type_for(fused[0], 0) == "heading"


def test_dotocr_failure_returns_deepseek_unchanged():
    ds = _deepseek_pages()
    # DotOCR failed / produced nothing -> DeepSeek output is used as-is.
    fused = enhance_layout_with_dotocr(ds, None)
    assert _block_type_for(fused[0], 0) == "text"
    assert _block_type_for(fused[0], 1) == "text"


def test_table_blocks_are_not_touched():
    ds = _deepseek_pages()
    # Pretend block 0 is a table; it must never be reclassified in Phase 1.
    for w in ds[0]["text"]:
        if w["block_id"] == 0:
            w["block_type"] = "table"
    fused = enhance_layout_with_dotocr(ds, _dotocr_pages())
    assert _block_type_for(fused[0], 0) == "table"


def test_logs_pipeline_stages(caplog):
    with caplog.at_level(logging.INFO, logger="layout_fusion"):
        enhance_layout_with_dotocr(_deepseek_pages(), _dotocr_pages())
    messages = [r.getMessage() for r in caplog.records]
    assert any("DeepSeek OCR completed" in m for m in messages)
    assert any("DotOCR layout completed" in m for m in messages)
    assert any("Layout fusion completed" in m for m in messages)


if __name__ == "__main__":
    test_heading_promoted_from_dotocr_title()
    test_section_header_category_is_promoted()
    test_dotocr_failure_returns_deepseek_unchanged()
    test_table_blocks_are_not_touched()
    print("ok")
