"""OCR engine dispatcher for Raqim.

Raqim supports three interchangeable OCR modes, selected at runtime via the
``OCR_ENGINE`` environment variable:

* ``OCR_ENGINE=deepseek`` (default) -> DeepSeek-OCR-2 (``ocr_model.py``).
* ``OCR_ENGINE=dots``               -> DotOCR / dots.mocr layout engine
                                       (``dots_ocr_engine.py``).
* ``OCR_ENGINE=fusion``             -> DeepSeek text + DotOCR layout fusion
                                       (``layout_fusion.py``). DeepSeek stays the
                                       source of truth for text; DotOCR only adds
                                       structure (headings/tables/pictures).

All modes return the SAME page/word structure (a list of pages, each with a
``text`` list of word dicts tagged with ``block_id`` / ``block_type`` /
``table_*`` ...), so the rest of Raqim (review UI + ``docx_builder``) works
unchanged regardless of the selected engine.

DeepSeek remains the default and is never replaced. The DotOCR and fusion paths
are loaded lazily, so importing this dispatcher never pulls in dots.mocr's
dependencies unless ``OCR_ENGINE=dots`` / ``OCR_ENGINE=fusion`` is actually used.
"""

from __future__ import annotations

import os

from ocr_model import DeepSeekOCRError, ocr_with_highlighting as _deepseek_ocr_with_highlighting

DEFAULT_ENGINE = "deepseek"
# Accept a few friendly spellings for the dots engine.
_DOTS_ALIASES = {"dots", "dotocr", "dot_ocr", "dots.ocr", "dots.mocr", "dots_ocr", "dotsocr"}
# Accept a few friendly spellings for the DeepSeek+DotOCR fusion mode.
_FUSION_ALIASES = {
    "fusion",
    "deepseek+dots",
    "deepseek_dots",
    "deepseek-dots",
    "deepseek+dotocr",
    "deepseek_dotocr",
    "deepseek-dotocr",
    "deepseek_dotocr_fusion",
}


class DotsOCRError(RuntimeError):
    """Raised when the DotOCR (dots.mocr) layout engine fails."""


def get_engine() -> str:
    """Return the normalized OCR engine name from the environment."""
    return os.getenv("OCR_ENGINE", DEFAULT_ENGINE).strip().lower()


def is_dots_engine() -> bool:
    return get_engine() in _DOTS_ALIASES


def is_fusion_engine() -> bool:
    return get_engine() in _FUSION_ALIASES


def current_engine_label() -> str:
    """Human-readable label for the currently selected engine."""
    if is_fusion_engine():
        return "DeepSeek-OCR-2 + DotOCR layout"
    if is_dots_engine():
        return "DotOCR (dots.mocr)"
    return "DeepSeek-OCR-2"


def ocr_with_highlighting(file_path, output_folder):
    """Run the selected OCR engine and return review-compatible page words.

    The signature/return shape matches ``ocr_model.ocr_with_highlighting`` so it
    is a drop-in dispatcher for the rest of the app.
    """
    if is_fusion_engine():
        # Lazy import: pulls in both DeepSeek and DotOCR only when fusion is used.
        from layout_fusion import run_fusion_ocr

        return run_fusion_ocr(file_path, output_folder)
    if is_dots_engine():
        # Lazy import: only pull in dots.mocr deps (torch/transformers) when the
        # dots engine is actually selected.
        from dots_ocr_engine import ocr_with_highlighting as _dots_ocr_with_highlighting

        return _dots_ocr_with_highlighting(file_path, output_folder)
    return _deepseek_ocr_with_highlighting(file_path, output_folder)
