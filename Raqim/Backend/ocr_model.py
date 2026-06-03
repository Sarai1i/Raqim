"""محرك OCR الخاص بمنصة Raqim — يعتمد على Tesseract v5 فقط.

هذا الملف يوفّر الواجهة التي يتوقعها ``Backend/app.py``:

- ``configure_tesseract(tesseract_cmd)`` لضبط مسار تنفيذ Tesseract.
- ``ocr_with_highlighting(file_path, output_folder)`` لتحويل ملفات PDF/الصور إلى
  صور صفحات، ثم إرجاع كلمات OCR مع صناديق الإحداثيات (bounding_box) وقيم الثقة
  (confidence) المطلوبة لتظليل الكلمات منخفضة الثقة في صفحة المراجعة.

المحرك الوحيد المستخدم هنا هو Tesseract v5، ومضبوط افتراضيًا على العربية
والإنجليزية معًا (``ara+eng``) عند توفّر حزم اللغة. الملف متوافق مع Windows:
يقرأ مسار Tesseract من متغير البيئة أو يبحث عنه في المسارات الافتراضية، ويدعم
تمرير مسار Poppler لقراءة ملفات PDF على Windows.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from statistics import median
from typing import Dict, List

from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
from pytesseract import Output


# الصيغ المدعومة للصور، وإعدادات OCR القابلة للضبط عبر متغيرات البيئة.
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_DPI = int(os.getenv("OCR_PDF_DPI", "220"))
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "80"))

# مسارات Windows الافتراضية لتثبيت Tesseract v5 (تُستخدم عند عدم توفّره في PATH).
_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


# configure_tesseract: ضبط مسار تنفيذ Tesseract المستخدم في كل عمليات OCR.
def configure_tesseract(tesseract_cmd: str | None = None) -> None:
    """تحديد ملف tesseract التنفيذي.

    ترتيب البحث: الوسيط الممرَّر، ثم متغير البيئة ``TESSERACT_CMD``، ثم البحث
    في ``PATH``، وأخيرًا المسارات الافتراضية على Windows. هذا يضمن عمل المحرك
    على Windows مع Tesseract v5 دون تعديل الكود.
    """

    candidate = tesseract_cmd or os.getenv("TESSERACT_CMD") or shutil.which("tesseract")

    # احتياط خاص بـ Windows عند عدم إضافة Tesseract إلى متغير PATH.
    if not candidate and sys.platform.startswith("win"):
        for windows_path in _WINDOWS_TESSERACT_PATHS:
            if os.path.exists(windows_path):
                candidate = windows_path
                break

    if candidate:
        pytesseract.pytesseract.tesseract_cmd = candidate


# _available_tesseract_languages: إرجاع مجموعة حزم اللغة المثبتة في Tesseract.
def _available_tesseract_languages() -> set[str]:
    try:
        langs = pytesseract.get_languages(config="")
        return set(langs or [])
    except Exception:
        return set()


# _preferred_language: اختيار لغة OCR، مع تفضيل العربية والإنجليزية معًا.
def _preferred_language() -> str:
    """إرجاع لغة Tesseract المناسبة.

    الافتراضي ``ara+eng`` عند توفّر الحزمتين. يمكن فرض لغة محددة عبر متغير
    البيئة ``OCR_TESSERACT_LANG`` (مثل ``ara`` أو ``ara+eng``).
    """

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


# _prepare_output_folder: تجهيز مجلد الإخراج وحذف معاينات الصفحات القديمة.
def _prepare_output_folder(output_folder: str | os.PathLike[str]) -> Path:
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)

    for old_page in folder.glob("original_page_*.png"):
        try:
            old_page.unlink()
        except OSError:
            pass
    return folder


# _load_pages: تحويل ملف PDF/صورة إلى قائمة صور صفحات بصيغة RGB.
def _load_pages(file_path: str | os.PathLike[str]) -> List[Image.Image]:
    """قراءة الملف المدخل وإرجاع صفحاته كصور.

    لملفات PDF يُستخدم Poppler عبر ``pdf2image``. على Windows يمكن تمرير مسار
    Poppler عبر متغير البيئة ``POPPLER_PATH`` إذا لم يكن مضافًا إلى ``PATH``.
    """

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        poppler_path = os.getenv("POPPLER_PATH", "").strip() or None
        pages = convert_from_path(str(path), dpi=DEFAULT_DPI, poppler_path=poppler_path)
        return [page.convert("RGB") for page in pages]

    if suffix in SUPPORTED_IMAGE_EXTENSIONS:
        with Image.open(path) as image:
            return [image.convert("RGB")]

    raise ValueError(f"Unsupported OCR file type: {suffix or 'unknown'}")


# _normalize_for_ocr: تحويل الصورة إلى تدرّج رمادي بتباين تلقائي لتحسين دقة OCR.
def _normalize_for_ocr(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return ImageOps.autocontrast(gray)


# _clean_text: تنظيف النص الكامل بإزالة المسافات الزائدة والأسطر الفارغة.
def _clean_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


# _clean_word: تنظيف كلمة واحدة بدمج المسافات وإزالة الأطراف.
def _clean_word(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# _safe_confidence: تحويل قيمة الثقة إلى رقم عشري آمن (-1 عند الفشل).
def _safe_confidence(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


# _word_item: بناء عنصر الكلمة الموحّد (نص + ثقة + صندوق إحداثيات + حالة التظليل).
def _word_item(word: str, confidence: float, x: int, y: int, w: int, h: int, width: int, height: int, index: int) -> Dict:
    """تكوين قاموس الكلمة المتوافق مع صفحة المراجعة.

    تُظلَّل الكلمة (highlighted) عندما تقل ثقتها عن العتبة الافتراضية، أو عند
    تعذّر قياس الثقة، حتى ينتبه إليها المستخدم أثناء المراجعة.
    """

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


# _approximate_words_from_text: توليد صناديق تقريبية لكلمات RTL من نص بلا إحداثيات.
def _approximate_words_from_text(text: str, width: int, height: int) -> List[Dict]:
    """احتياط فقط: عند توفّر نص دون صناديق كلمات من Tesseract.

    يوزّع الكلمات على أسطر من اليمين إلى اليسار بمواضع تقريبية حتى تبقى صفحة
    المراجعة قابلة للاستخدام (الضغط على الكلمة يشير إلى موقع تقريبي على الصورة).
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
                    confidence=0,
                    x=x,
                    y=y,
                    w=token_width,
                    h=max(20, int(line_height * 0.78)),
                    width=width,
                    height=height,
                    index=len(words),
                )
            )
            # نص الاحتياط غير موثوق الثقة، لذلك يُظلَّل دائمًا للمراجعة اليدوية.
            words[-1]["highlighted"] = True
            words[-1]["wasHighlighted"] = True
            x_cursor = x - gap
        y += line_height

    return words


# _sort_words_for_arabic_reading_order: ترتيب الكلمات بترتيب القراءة العربي
# (من الأعلى للأسفل، ثم من اليمين لليسار داخل كل سطر).
def _sort_words_for_arabic_reading_order(words: List[Dict]) -> List[Dict]:
    """ترتيب كلمات OCR حسب الترتيب البصري للقراءة العربية.

    يستخدم متوسط ارتفاع الكلمات (median) لتحديد تسامح تجميع الأسطر، ثم يرتّب
    الأسطر تنازليًا حسب y والكلمات داخل السطر تنازليًا حسب x (يمين ← يسار).
    """

    indexed_words = []
    heights = []
    for original_index, word in enumerate(words or []):
        bbox = word.get("bounding_box", {}) or {}
        y = int(bbox.get("y", 0) or 0)
        h = int(bbox.get("h", 1) or 1)
        heights.append(h)
        indexed_words.append(
            {"word": word, "original_index": original_index, "y": y, "h": h, "x": int(bbox.get("x", 0) or 0)}
        )

    if not indexed_words:
        return []

    typical_height = median(heights)
    line_tolerance = max(6, typical_height * 0.65)
    lines: List[Dict] = []

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

    sorted_words: List[Dict] = []
    for line in sorted(lines, key=lambda item: item["y"]):
        sorted_words.extend(
            item["word"] for item in sorted(line["items"], key=lambda item: (-item["x"], item["original_index"]))
        )

    # إعادة ترقيم الفهارس لتبقى متسلسلة بعد إعادة الترتيب.
    for new_index, word in enumerate(sorted_words):
        word["index"] = new_index

    return sorted_words


# _ocr_page_tesseract: تشغيل Tesseract على صفحة واحدة واستخراج الكلمات وصناديقها.
def _ocr_page_tesseract(image: Image.Image) -> List[Dict]:
    """استخراج الكلمات مع bounding_box والثقة عبر Tesseract فقط.

    يستخدم ``image_to_data`` للحصول على إحداثيات وثقة كل كلمة. عند عدم إرجاع
    أي كلمات ذات صناديق، يلجأ إلى ``image_to_string`` ويبني صناديق تقريبية.
    """

    width, height = image.size
    ocr_image = _normalize_for_ocr(image)
    lang = _preferred_language()

    # إعدادات Tesseract: oem 3 = المحرك الافتراضي، psm 6 = افتراض كتلة نص موحّدة.
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

    # احتياط: إذا لم تُرجع image_to_data أي كلمات، نستخرج النص الخام ونبني صناديق تقريبية.
    if not words:
        plain_text = _clean_word(pytesseract.image_to_string(ocr_image, lang=lang, config=config))
        if plain_text:
            words = _approximate_words_from_text(plain_text, width, height)

    # ترتيب اختياري حسب القراءة العربية، يُفعَّل عبر OCR_SORT_READING_ORDER=true.
    if os.getenv("OCR_SORT_READING_ORDER", "false").lower() in {"1", "true", "yes", "on"}:
        words = _sort_words_for_arabic_reading_order(words)

    return words


# ocr_with_highlighting: تشغيل OCR على الملف كاملًا وإرجاع نتائج الصفحات للمراجعة.
def ocr_with_highlighting(file_path: str | os.PathLike[str], output_folder: str | os.PathLike[str]) -> List[Dict]:
    """تشغيل Tesseract على كل صفحات الملف وإرجاع كلمات قابلة للمراجعة.

    لكل صفحة: تُحفظ صورة معاينة (original_page_N.png) لعرضها في الواجهة، ثم
    تُستخرج الكلمات مع صناديقها وثقتها، مع بيانات المحرك (Tesseract) لكل صفحة.
    """

    output_dir = _prepare_output_folder(output_folder)
    pages = _load_pages(file_path)
    lang = _preferred_language()

    results: List[Dict] = []
    for page_number, image in enumerate(pages, start=1):
        preview_path = output_dir / f"original_page_{page_number}.png"
        image.save(preview_path, format="PNG")

        page_words = _ocr_page_tesseract(image)
        results.append(
            {
                "page_number": page_number,
                "image_path": str(preview_path),
                "text": page_words,
                "ocr_engine": "tesseract",
                "ocr_engine_label": f"Tesseract ({lang})",
                "ocr_provider": "tesseract",
                "fallback_used": False,
                "fallback_reason": "",
            }
        )

    return results
