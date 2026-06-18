"""Tests for the DeepSeek + DotOCR layout-fusion engine (``layout_fusion``).

These tests exercise the pure merge logic (``enhance_layout_with_dotocr``) with
synthetic DeepSeek pages and synthetic DotOCR layout regions — no OCR models are
loaded.

Covered phases:

* Phase 1: Title / Section-header -> ``block_type == "heading"``.
* Phase 2: Table region -> Raqim table structure (reusing DotOCR HTML), without
  clobbering tables DeepSeek already detected.
* Phase 3: Picture detection + TOC-friendly heading hierarchy (heading levels).

Plus the two hard rules: DeepSeek text is never replaced, and DotOCR failure
degrades gracefully to the DeepSeek-only result.
"""

import layout_fusion


PAGE_W = 1000
PAGE_H = 1400


def _box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h, "original_width": PAGE_W, "original_height": PAGE_H}


def _word(word, block_id, x, y, w, h, block_type="text", line_index=0):
    return {
        "index": 0,
        "word": word,
        "original_word": word,
        "corrected_word": "",
        "confidence": 95,
        "highlighted": False,
        "block_id": block_id,
        "block_type": block_type,
        "line_index": line_index,
        "bounding_box": _box(x, y, w, h),
        "source_box": _box(x, y, w, h),
    }


def _page(words):
    return {
        "page_number": 1,
        "image_path": "uploads/original_page_1.png",
        "text": words,
        "ocr_engine": "deepseek",
        "ocr_engine_label": "DeepSeek-OCR-2 (test)",
        "ocr_provider": "deepseek_local",
    }


def _simple_page():
    # block 0: a short heading-like line near the top.
    # block 1: a normal paragraph below it.
    return _page(
        [
            _word("الفصل", 0, 400, 50, 90, 40),
            _word("الأول", 0, 300, 50, 90, 40),
            _word("هذا", 1, 880, 200, 70, 36),
            _word("نص", 1, 800, 200, 60, 36),
            _word("الفقرة", 1, 700, 200, 90, 36),
        ]
    )


def test_phase1_marks_title_as_heading():
    pages = [_simple_page()]
    layout = [[{"category": "Title", "bbox": [290, 40, 500, 100], "text": "العنوان"}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    words = fused[0]["text"]

    heading_words = [w for w in words if w["block_type"] == "heading"]
    assert heading_words, "expected the top block to become a heading"
    assert {w["word"] for w in heading_words} == {"الفصل", "الأول"}
    # The paragraph stays text.
    para_words = [w for w in words if w["block_type"] == "text"]
    assert {w["word"] for w in para_words} == {"هذا", "نص", "الفقرة"}


def test_phase1_section_header_detected():
    pages = [_simple_page()]
    layout = [[{"category": "Section-header", "bbox": [290, 40, 500, 100], "text": "قسم"}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    heading_words = [w for w in fused[0]["text"] if w["block_type"] == "heading"]
    assert {w["word"] for w in heading_words} == {"الفصل", "الأول"}
    assert all(w.get("dots_category") == "section-header" for w in heading_words)


def test_deepseek_text_is_never_replaced():
    pages = [_simple_page()]
    # DotOCR claims different text for the heading region; it must be ignored.
    layout = [[{"category": "Title", "bbox": [290, 40, 500, 100], "text": "DOTOCR TEXT"}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    all_text = {w["word"] for w in fused[0]["text"]}
    assert "DOTOCR TEXT" not in all_text
    assert {"الفصل", "الأول"} <= all_text


def test_no_layout_returns_unchanged_structure():
    pages = [_simple_page()]
    fused = layout_fusion.enhance_layout_with_dotocr(pages, [[]])
    assert {w["word"] for w in fused[0]["text"]} == {"الفصل", "الأول", "هذا", "نص", "الفقرة"}
    assert all(w["block_type"] == "text" for w in fused[0]["text"])


def test_large_paragraph_not_turned_into_heading():
    # A big paragraph block overlapping a tiny title bbox should NOT be promoted
    # (containment of the big block in the small bbox is low).
    pages = [_page([_word("نص", 0, 50, 50, 900, 1000)])]
    layout = [[{"category": "Title", "bbox": [60, 60, 200, 110], "text": "x"}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    assert all(w["block_type"] == "text" for w in fused[0]["text"])


def test_input_pages_not_mutated():
    pages = [_simple_page()]
    layout = [[{"category": "Title", "bbox": [290, 40, 500, 100], "text": "x"}]]
    layout_fusion.enhance_layout_with_dotocr(pages, layout)
    # Original input object stays text-only (deep copy returned).
    assert all(w["block_type"] == "text" for w in pages[0]["text"])


def test_page_marked_as_fused():
    pages = [_simple_page()]
    layout = [[{"category": "Title", "bbox": [290, 40, 500, 100], "text": "x"}]]
    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    assert fused[0]["fusion"] is True
    assert fused[0]["layout_engine"] == "dots"
    assert "DotOCR" in fused[0]["ocr_engine_label"]


def test_phase2_table_from_dotocr_html():
    # A page where DeepSeek saw plain text where DotOCR detects a table.
    pages = [
        _page(
            [
                _word("بيانات", 0, 700, 600, 90, 36),
                _word("الجدول", 0, 600, 600, 90, 36),
            ]
        )
    ]
    html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
    layout = [[{"category": "Table", "bbox": [550, 560, 950, 760], "text": html}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    words = fused[0]["text"]
    table_words = [w for w in words if w["block_type"] == "table"]
    assert table_words, "expected a reconstructed table block"
    # The cells carry table_row/table_col so the review UI + docx can render it.
    assert all("table_row" in w and "table_col" in w for w in table_words)
    cell_text = {w["word"] for w in table_words}
    assert {"A", "B", "C", "D"} <= cell_text
    # The original DeepSeek plain-text fragment is replaced by the table.
    assert "بيانات" not in cell_text


def test_phase2_keeps_existing_deepseek_table():
    # DeepSeek already produced a real table; fusion must not rebuild it.
    table_word = _word("X", 0, 700, 600, 90, 36, block_type="table")
    table_word["table_id"] = 1
    table_word["table_row"] = 0
    table_word["table_col"] = 0
    pages = [_page([table_word])]
    html = "<table><tr><td>Z</td></tr></table>"
    layout = [[{"category": "Table", "bbox": [550, 560, 950, 760], "text": html}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    words = fused[0]["text"]
    assert {w["word"] for w in words} == {"X"}  # DeepSeek cell text preserved.
    assert "Z" not in {w["word"] for w in words}


def test_phase2_unparsable_table_keeps_text():
    pages = [_page([_word("نص", 0, 700, 600, 90, 36)])]
    # Table category but no parseable HTML -> keep the DeepSeek text.
    layout = [[{"category": "Table", "bbox": [550, 560, 950, 760], "text": "not a table"}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    words = fused[0]["text"]
    assert {w["word"] for w in words} == {"نص"}
    assert all(w["block_type"] != "table" for w in words)


def test_phase2_can_be_disabled():
    pages = [_page([_word("نص", 0, 700, 600, 90, 36)])]
    html = "<table><tr><td>A</td></tr></table>"
    layout = [[{"category": "Table", "bbox": [550, 560, 950, 760], "text": html}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout, enable_tables=False)
    words = fused[0]["text"]
    assert {w["word"] for w in words} == {"نص"}


def test_phase3_heading_hierarchy_levels():
    pages = [_simple_page()]
    title_layout = [[{"category": "Title", "bbox": [290, 40, 500, 100], "text": "x"}]]
    section_layout = [[{"category": "Section-header", "bbox": [290, 40, 500, 100], "text": "x"}]]

    title_fused = layout_fusion.enhance_layout_with_dotocr(pages, title_layout)
    section_fused = layout_fusion.enhance_layout_with_dotocr(pages, section_layout)

    title_headings = [w for w in title_fused[0]["text"] if w["block_type"] == "heading"]
    section_headings = [w for w in section_fused[0]["text"] if w["block_type"] == "heading"]
    assert all(w["heading_level"] == 1 for w in title_headings)
    assert all(w["heading_level"] == 2 for w in section_headings)


def test_phase3_picture_detection_adds_placeholder():
    pages = [_simple_page()]
    layout = [[{"category": "Picture", "bbox": [100, 900, 900, 1200]}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    pictures = [w for w in fused[0]["text"] if w.get("block_type") == "picture"]
    assert pictures, "expected a picture placeholder block"
    assert pictures[0].get("is_picture") is True
    assert pictures[0]["word"] == layout_fusion.PICTURE_PLACEHOLDER


def test_phase3_picture_skipped_when_overlapping_text():
    # Picture bbox covering an existing text block should not add a duplicate.
    pages = [_simple_page()]
    layout = [[{"category": "Picture", "bbox": [690, 190, 960, 250]}]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    pictures = [w for w in fused[0]["text"] if w.get("block_type") == "picture"]
    assert not pictures


def test_phase3_picture_inserted_in_reading_order():
    # Heading (top, y=50), picture (y=110-180), paragraph (y=200) -> the picture
    # must land between the heading and the paragraph.
    pages = [_simple_page()]
    layout = [[
        {"category": "Title", "bbox": [290, 40, 500, 100], "text": "x"},
        {"category": "Picture", "bbox": [100, 110, 900, 180]},
    ]]

    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout)
    block_types = [w["block_type"] for w in fused[0]["text"]]
    pic_index = block_types.index("picture")
    heading_index = block_types.index("heading")
    text_index = block_types.index("text")
    assert heading_index < pic_index < text_index


def test_phase3_picture_can_be_disabled():
    pages = [_simple_page()]
    layout = [[{"category": "Picture", "bbox": [100, 900, 900, 1200]}]]
    fused = layout_fusion.enhance_layout_with_dotocr(pages, layout, enable_pictures=False)
    assert not [w for w in fused[0]["text"] if w.get("block_type") == "picture"]


def test_run_fusion_ocr_degrades_when_dotocr_unavailable(monkeypatch):
    """If DotOCR import/inference fails, the DeepSeek-only result is returned."""
    deepseek_pages = [_simple_page()]

    import ocr_model

    monkeypatch.setattr(ocr_model, "ocr_with_highlighting", lambda *_a, **_k: deepseek_pages)

    def _boom(_pages):
        raise RuntimeError("DotOCR not installed")

    monkeypatch.setattr(layout_fusion, "_collect_dotocr_layout", _boom)

    result = layout_fusion.run_fusion_ocr("x.pdf", "out")
    assert result is deepseek_pages
    assert all(w["block_type"] == "text" for w in result[0]["text"])


def test_run_fusion_ocr_skips_when_no_regions(monkeypatch):
    """No DotOCR regions -> DeepSeek-only result, no fusion tag."""
    deepseek_pages = [_simple_page()]

    import ocr_model

    monkeypatch.setattr(ocr_model, "ocr_with_highlighting", lambda *_a, **_k: deepseek_pages)
    monkeypatch.setattr(layout_fusion, "_collect_dotocr_layout", lambda _pages: [[]])

    result = layout_fusion.run_fusion_ocr("x.pdf", "out")
    assert result is deepseek_pages


if __name__ == "__main__":
    import sys

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            argc = fn.__code__.co_argcount
            if "monkeypatch" in fn.__code__.co_varnames[:argc]:
                continue  # needs pytest fixtures
            try:
                fn()
                print(f"ok  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
