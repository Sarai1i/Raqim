from flask import Flask, request, jsonify, send_from_directory, send_file, redirect, url_for, session
import os
import json
import re
import time
import shutil
import threading
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from ocr_model import configure_tesseract, ocr_with_highlighting
from flask_cors import CORS
import requests
import google.generativeai as genai
from pymongo import MongoClient
import gridfs
import io


def _load_local_env_file():
    """تحميل متغيرات .env المحلية دون طباعة أي أسرار."""
    for candidate in [os.path.join(os.path.dirname(__file__), ".env"), os.path.join(os.path.dirname(__file__), "..", ".env")]:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception as exc:
            print(f"⚠️ تعذر تحميل ملف .env المحلي: {exc}")


_load_local_env_file()


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# تكوين Gemini API
API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
if API_KEY:
    genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL_NAME) if API_KEY else None

# تكوين Qwen2.5 API الاختياري - غير مفعّل افتراضيًا
QWEN_ENABLED = os.getenv("QWEN_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
QWEN_API_BASE_URL = os.getenv("QWEN_API_BASE_URL", "").rstrip("/")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL_NAME = os.getenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
QWEN_TIMEOUT_SECONDS = float(os.getenv("QWEN_TIMEOUT_SECONDS", "20"))

# تكوين LLM مفتوح المصدر اختياري للاقتراحات، مثل Ollama أو أي خادم OpenAI-compatible.
OSS_LLM_ENABLED = os.getenv("OSS_LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
OSS_LLM_PROVIDER = os.getenv("OSS_LLM_PROVIDER", "ollama").strip().lower()
OSS_LLM_API_BASE_URL = os.getenv("OSS_LLM_API_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OSS_LLM_API_KEY = os.getenv("OSS_LLM_API_KEY", "")
OSS_LLM_MODEL_NAME = os.getenv("OSS_LLM_MODEL_NAME", "qwen2.5:7b-instruct")
OSS_LLM_TIMEOUT_SECONDS = float(os.getenv("OSS_LLM_TIMEOUT_SECONDS", "25"))

# طبقة اقتراحات التصحيح الذكية داخل صفحة المراجعة.
# هذه الطبقة لا تغيّر OCR ولا تعدّل النص تلقائيًا؛ هي تعيد اقتراحات فقط يختارها المستخدم يدويًا.
LLM_SUGGESTIONS_API_BASE_URL = os.getenv("LLM_SUGGESTIONS_API_BASE_URL", os.getenv("OPENAI_API_BASE", "")).rstrip("/")
LLM_SUGGESTIONS_API_KEY = os.getenv("LLM_SUGGESTIONS_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_SUGGESTIONS_MODEL_NAME = os.getenv("LLM_SUGGESTIONS_MODEL_NAME", "gpt-5-nano")
LLM_SUGGESTIONS_TIMEOUT_SECONDS = float(os.getenv("LLM_SUGGESTIONS_TIMEOUT_SECONDS", "20"))
LLM_SUGGESTIONS_ENABLED = os.getenv(
    "LLM_SUGGESTIONS_ENABLED",
    "true" if LLM_SUGGESTIONS_API_BASE_URL and LLM_SUGGESTIONS_API_KEY else "false"
).lower() in {"1", "true", "yes", "on"}

# إعدادات ALLaM للاقتراحات اليدوية داخل نافذة المراجعة فقط.
# عند LLM_PROVIDER=groq يستخدم Groq OpenAI-compatible مع مودل ALLaM، دون تفعيل أي LLM آخر.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")
GROQ_API_BASE_URL = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

ALLAM_SUGGESTIONS_ENABLED = os.getenv("ALLAM_SUGGESTIONS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ALLAM_SUGGESTIONS_ENDPOINT = os.getenv("ALLAM_SUGGESTIONS_ENDPOINT", os.getenv("ALLAM_API_URL", "")).rstrip("/")
ALLAM_SUGGESTIONS_API_BASE_URL = os.getenv("ALLAM_SUGGESTIONS_API_BASE_URL", os.getenv("ALLAM_API_BASE_URL", "")).rstrip("/")
ALLAM_SUGGESTIONS_API_KEY = os.getenv("ALLAM_SUGGESTIONS_API_KEY", os.getenv("ALLAM_API_KEY", ""))
ALLAM_SUGGESTIONS_MODEL_NAME = os.getenv("ALLAM_SUGGESTIONS_MODEL_NAME", os.getenv("ALLAM_MODEL_NAME", "allam"))
ALLAM_SUGGESTIONS_TIMEOUT_SECONDS = float(os.getenv("ALLAM_SUGGESTIONS_TIMEOUT_SECONDS", "25"))

if LLM_PROVIDER == "groq":
    ALLAM_SUGGESTIONS_ENDPOINT = ""
    ALLAM_SUGGESTIONS_API_BASE_URL = GROQ_API_BASE_URL
    ALLAM_SUGGESTIONS_API_KEY = GROQ_API_KEY
    ALLAM_SUGGESTIONS_MODEL_NAME = GROQ_MODEL
    LLM_SUGGESTIONS_ENABLED = False
    OSS_LLM_ENABLED = False

app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# تكوين Tesseract
TESSERACT_PATH = os.getenv("TESSERACT_CMD") or shutil.which("tesseract") or "tesseract"
configure_tesseract(TESSERACT_PATH)

# متغيرات المعالجة
processing_complete = False
processing_failed = False
processing_error = ""
ocr_results = []
original_file_name = ""
ocr_engine_status = {
    "engine": "pending",
    "label": "بانتظار المعالجة",
    "provider": "pending",
    "qari_attempted": False,
    "fallback_used": False,
    "fallback_reason": "",
}

# مجلدات التخزين
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "corrected_files")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ملفات التصحيحات
corrections_file = os.path.join(OUTPUT_FOLDER, "corrections.json")
corrected_text_file = os.path.join(OUTPUT_FOLDER, "corrected_text.txt")

CORPUS_FILTER_API_URL = os.getenv("CORPUS_FILTER_API_URL", "http://127.0.0.1:9090/correct")
API_PUBLIC_BASE_URL = os.getenv("API_PUBLIC_BASE_URL", "http://127.0.0.1:5000")

# تكوين MongoDB

class _LocalInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _LocalUpdateResult:
    def __init__(self, matched_count=0, modified_count=0):
        self.matched_count = matched_count
        self.modified_count = modified_count


class _LocalStoredFile:
    def __init__(self, data, filename):
        self._data = data
        self.filename = filename

    def read(self):
        return self._data


class _LocalGridFS:
    """بديل محلي خفيف لـ GridFS عند عدم توفر MongoDB في بيئة الديمو."""

    def __init__(self):
        self._files = {}

    def put(self, data, filename=None):
        import uuid
        file_id = str(uuid.uuid4())
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._files[file_id] = _LocalStoredFile(data, filename or file_id)
        return file_id

    def get(self, file_id):
        key = str(file_id)
        if key not in self._files:
            raise gridfs.NoFile(f"Local file not found: {file_id}")
        return self._files[key]


class _LocalCollection:
    """بديل محلي بسيط للعمليات المستخدمة من PyMongo في هذا التطبيق."""

    def __init__(self):
        self._docs = []

    def insert_one(self, document):
        import uuid
        stored = dict(document)
        stored.setdefault("_id", str(uuid.uuid4()))
        self._docs.append(stored)
        return _LocalInsertResult(stored["_id"])

    def update_one(self, query, update, upsert=False):
        set_values = update.get("$set", update)
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(set_values)
                return _LocalUpdateResult(matched_count=1, modified_count=1)

        if upsert:
            new_doc = dict(query)
            new_doc.update(set_values)
            self.insert_one(new_doc)
            return _LocalUpdateResult(matched_count=0, modified_count=1)

        return _LocalUpdateResult(matched_count=0, modified_count=0)

    def find(self, query=None, projection=None):
        query = query or {}
        matched = []
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                item = dict(doc)
                if projection:
                    for key, include in projection.items():
                        if include == 0:
                            item.pop(key, None)
                matched.append(item)
        return matched

    def find_one(self, query=None, projection=None):
        results = self.find(query, projection)
        return results[0] if results else None


try:
    # الاتصال بقاعدة البيانات عند توفر MongoDB الحقيقي.
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=1500)
    client.admin.command("ping")
    db = client[os.getenv("MONGO_DB_NAME", "ocr_database")]
    fs = gridfs.GridFS(db)  # GridFS لتخزين الملفات الكبيرة
    files_collection = db["files"]
    corrected_words_collection = db["corrected_words"]  # مجموعة الكلمات المصححة
    users_collection = db["users"]  # مجموعة حسابات المستخدمين
    print("✅ Connected to MongoDB.")
except Exception as mongo_error:
    print(f"⚠️ MongoDB is not available; using local in-memory storage for demo/testing: {mongo_error}")
    client = None
    db = None
    fs = _LocalGridFS()
    files_collection = _LocalCollection()
    corrected_words_collection = _LocalCollection()
    users_collection = _LocalCollection()


def _apply_correction_to_ocr_results(page_number, word_index, corrected_word):
    """تحديث نتائج OCR الحالية حتى يعكس التنزيل اليدوي آخر تصحيحات المستخدم."""
    global ocr_results

    if not corrected_word or page_number is None or word_index is None:
        return False

    try:
        page_idx = int(page_number) - 1
        target_index = int(word_index)
    except (TypeError, ValueError):
        return False

    if page_idx < 0 or page_idx >= len(ocr_results):
        return False

    words = ocr_results[page_idx].get("text", [])
    for fallback_index, word_data in enumerate(words):
        current_index = word_data.get("index", fallback_index)
        if current_index == target_index:
            original_word = word_data.get("original_word") or word_data.get("word", "")
            word_data["original_word"] = original_word
            word_data["word"] = corrected_word
            word_data["corrected_word"] = corrected_word
            word_data["corrected"] = True
            word_data["highlighted"] = False
            word_data["wasHighlighted"] = True
            return True

    return False


def _build_corrected_text_from_ocr():
    """بناء النص النهائي من نتائج OCR مع تفضيل الكلمات المصححة يدويًا."""
    corrected_pages = []

    for page in ocr_results:
        page_words = []
        for word_data in page.get("text", []):
            page_words.append(
                word_data.get("corrected_word")
                or word_data.get("word")
                or ""
            )
        page_text = " ".join(word for word in page_words if word).strip()
        if page_text:
            corrected_pages.append(page_text)

    return "\n\n".join(corrected_pages)


def get_gemini_suggestion(word):
    """إرسال الكلمة إلى Gemini API للحصول على التصحيح الذكي"""
    try:
        prompt = f"""أنت مساعد ذكي متخصص في تصحيح النصوص العربية المستخرجة عبر OCR.
        - قم فقط بتصحيح الأخطاء الإملائية والنحوية.
        - لا تضف أي تعليق، فقط أعد النص المصحح بدون أي تغييرات غير ضرورية.
        - لا تكرر التعليمات، ولا تطرح أسئلة، ولا تطلب أي شيء، فقط أعد النص المصحح مباشرة.

        **النص الأصلي:** {word}

        **النص المصحح:**"""

        if model is None:
            return word

        response = model.generate_content(prompt,
                                          generation_config=genai.types.GenerationConfig(
                                              temperature=0.1,  # جعل الاستجابة أكثر دقة وأقل إبداعًا
                                              max_output_tokens=100  # تقليل عدد الرموز لتجنب الإجابات الطويلة
                                          ))

        return response.text.strip() if response and response.text else word  # استخراج التصحيح فقط
    except Exception as e:
        print(f"❌ خطأ في Gemini API: {e}")
        return word
def get_qwen_suggestion(word):
    """إرجاع اقتراح Qwen2.5 عند تفعيله صراحةً فقط، وإلا إعادة النص الأصلي."""
    if not QWEN_ENABLED or not QWEN_API_BASE_URL or not QWEN_API_KEY:
        return word

    try:
        prompt = f"""أنت مساعد ذكي متخصص في تصحيح النصوص العربية المستخرجة عبر OCR.
        - قم فقط بتصحيح الأخطاء الإملائية والنحوية.
        - لا تضف أي تعليق، فقط أعد النص المصحح بدون أي تغييرات غير ضرورية.
        - لا تكرر التعليمات، ولا تطرح أسئلة، ولا تطلب أي شيء، فقط أعد النص المصحح مباشرة.

        **النص الأصلي:** {word}

        **النص المصحح:**"""

        response = requests.post(
            f"{QWEN_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": QWEN_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "أنت مساعد متخصص في تصحيح النصوص العربية فقط."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 100,
            },
            timeout=QWEN_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        suggestion = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return suggestion.strip() if suggestion else word
    except Exception as e:
        print(f"❌ خطأ في Qwen2.5 API: {e}")
        return word


def _clean_llm_suggestion(suggestion, original_word):
    """تنظيف استجابة LLM حتى ترجع كلمة/عبارة قصيرة فقط للاستخدام داخل قائمة الاقتراحات."""
    if not suggestion:
        return original_word

    cleaned = str(suggestion).strip()
    for marker in ["النص المصحح:", "التصحيح:", "corrected:", "Corrected:"]:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[-1].strip()

    cleaned = cleaned.replace("`", "").replace('"', "").replace("'", "").strip()
    cleaned = cleaned.splitlines()[0].strip() if cleaned.splitlines() else cleaned

    # منع الردود الطويلة أو الشروحات من الظهور في واجهة الاقتراحات.
    # نقبل كلمة واحدة (أو كلمتين كحد أقصى) لأن المطلوب تصحيح إملائي لكلمة واحدة فقط.
    if not cleaned or len(cleaned.split()) > 2 or len(cleaned) > 40:
        return original_word
    return cleaned


def get_open_source_llm_suggestion(word):
    """إرجاع اقتراح من LLM مفتوح المصدر عبر Ollama أو خادم OpenAI-compatible عند تفعيله."""
    if not OSS_LLM_ENABLED or not OSS_LLM_API_BASE_URL:
        return word

    prompt = f"""صحح الكلمة العربية التالية إذا كانت ناتجة عن خطأ OCR.
أعد كلمة واحدة أو عبارة قصيرة فقط بدون شرح.
الكلمة: {word}
التصحيح:"""

    try:
        if OSS_LLM_PROVIDER == "ollama":
            response = requests.post(
                f"{OSS_LLM_API_BASE_URL}/api/generate",
                json={
                    "model": OSS_LLM_MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 32},
                },
                timeout=OSS_LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return _clean_llm_suggestion(data.get("response", ""), word)

        if OSS_LLM_PROVIDER in {"openai", "openai_compatible", "vllm", "tgi"}:
            headers = {"Content-Type": "application/json"}
            if OSS_LLM_API_KEY:
                headers["Authorization"] = f"Bearer {OSS_LLM_API_KEY}"

            response = requests.post(
                f"{OSS_LLM_API_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": OSS_LLM_MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "أنت مساعد متخصص في تصحيح كلمات عربية ناتجة عن OCR. أعد التصحيح فقط."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 32,
                },
                timeout=OSS_LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            suggestion = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _clean_llm_suggestion(suggestion, word)

        print(f"❌ مزود LLM مفتوح المصدر غير مدعوم: {OSS_LLM_PROVIDER}")
        return word
    except Exception as e:
        print(f"❌ خطأ في LLM المفتوح المصدر: {e}")
        return word


def _parse_json_safely(raw_text):
    """محاولة قراءة JSON من استجابة النموذج حتى لو أضاف النموذج نصًا زائدًا."""
    if not raw_text:
        return {}

    text = str(raw_text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


def _normalise_suggestion_item(item, original_word, source="llm"):
    """تحويل اقتراح LLM إلى صيغة آمنة وقصيرة للواجهة."""
    if isinstance(item, dict):
        candidate = item.get("word") or item.get("suggestion") or item.get("text") or ""
        reason = item.get("reason") or item.get("note") or ""
    else:
        candidate = item
        reason = ""

    cleaned = _clean_llm_suggestion(candidate, original_word)
    if not cleaned or cleaned == original_word:
        return None

    return {
        "word": cleaned,
        "source": source,
        "reason": str(reason).strip()[:120] if reason else "اقتراح تصحيح محتمل لأخطاء OCR"
    }


def _dedupe_suggestion_items(items):
    """إزالة التكرارات مع الحفاظ على ترتيب الاقتراحات."""
    deduped = []
    seen = set()
    for item in items:
        if not item:
            continue
        key = item.get("word", "").strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _extract_allam_suggestions_payload(data, original_word, max_suggestions):
    """قراءة اقتراحات ALLaM من أكثر من شكل استجابة محتمل."""
    if not isinstance(data, dict):
        return []

    if isinstance(data.get("suggestions"), list):
        return data.get("suggestions", [])
    if isinstance(data.get("allam_suggestions"), list):
        return data.get("allam_suggestions", [])
    if isinstance(data.get("corrections"), list):
        return data.get("corrections", [])

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _parse_json_safely(content)
    raw = parsed.get("suggestions", []) if isinstance(parsed, dict) else []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raw = []
    # احتياطي: أحيانًا يكسر النموذج صيغة JSON (مثل "reason:" بدل "reason":)،
    # فيفشل التحليل العادي. في هذه الحالة نستخرج الكلمات مباشرة بتعبير منتظم.
    if not raw and content:
        fallback_words = re.findall(r'"word"\s*:\s*"([^"]+)"', content)
        raw = [{"word": w} for w in fallback_words]
    return raw[:max_suggestions]


def get_allam_correction_suggestions(word, context="", page_number=None, max_suggestions=5):
    """استدعاء ALLaM الحقيقي لإرجاع اقتراحات كلمة OCR دون تطبيقها تلقائيًا."""
    original_word = (word or "").strip()
    if not original_word or not ALLAM_SUGGESTIONS_ENABLED:
        return []

    if not ALLAM_SUGGESTIONS_ENDPOINT and not ALLAM_SUGGESTIONS_API_BASE_URL:
        print("⚠️ لم يتم ضبط endpoint خاص بـ ALLaM؛ لن تُعرض اقتراحات ALLaM.")
        return []

    context = (context or "").strip()
    page_number = page_number or "غير متاح"
    system_prompt = (
        "أنت مدقّق إملائي عربي متخصص في تصحيح أخطاء OCR لكلمة واحدة. "
        "مهمتك تصحيح شكل الكلمة المعطاة فقط (حروف مشوّهة، رموز دخيلة مثل » أو الأرقام، "
        "حروف ناقصة أو زائدة، همزات وتشكيل خاطئ) دون تغيير معناها. "
        "كل اقتراح يجب أن يكون كلمة عربية واحدة تشبه الكلمة الأصلية إملائيًا بشكل كبير. "
        "ممنوع منعًا باتًا اقتراح كلمات مختلفة المعنى أو كلمات من السياق أو عبارات. "
        "أعد JSON صالحًا فقط بالعربية. إذا كانت الكلمة صحيحة إملائيًا فأرجع is_correct=true و suggestions فارغة."
    )
    user_prompt = f"""صحّح الأخطاء الإملائية في الكلمة التالية المستخرجة من OCR، إن وُجدت.

القواعد الصارمة:
- أعد JSON فقط بالشكل: {{"is_correct": true/false, "suggestions":[{{"word":"...","reason":"..."}}]}}
- كل اقتراح = كلمة عربية واحدة فقط (ليست عبارة ولا جملة).
- يجب أن يكون كل اقتراح قريبًا جدًا من شكل الكلمة الأصلية (نفس الحروف تقريبًا، مع إصلاح التشويه فقط).
- ممنوع اقتراح كلمة معناها مختلف عن الكلمة الأصلية، وممنوع أخذ كلمات من السياق.
- مثال: لكلمة "القارئ»" الصحيح "القارئ" (إزالة الرمز الدخيل)، وليس "الأول" أو "الكتاب".
- إذا كانت الكلمة صحيحة إملائيًا: {{"is_correct": true, "suggestions":[]}}
- إذا كانت خاطئة: أعد من 1 إلى {max_suggestions} اقتراحات إملائية فقط.
- استخدم السياق للفهم فقط، لا لاقتراح كلمات منه.
- لا تعد النص كاملًا ولا تضف شرحًا خارج JSON.

الكلمة المراد تصحيحها: {original_word}
السياق (للفهم فقط): {context}
"""

    try:
        headers = {"Content-Type": "application/json"}
        if ALLAM_SUGGESTIONS_API_KEY:
            headers["Authorization"] = f"Bearer {ALLAM_SUGGESTIONS_API_KEY}"

        if ALLAM_SUGGESTIONS_ENDPOINT:
            payload = {
                "word": original_word,
                "context": context,
                "page_number": page_number,
                "max_suggestions": max_suggestions,
            }
            response = requests.post(ALLAM_SUGGESTIONS_ENDPOINT, headers=headers, json=payload, timeout=ALLAM_SUGGESTIONS_TIMEOUT_SECONDS)
        else:
            payload = {
                "model": ALLAM_SUGGESTIONS_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            }
            response = requests.post(
                f"{ALLAM_SUGGESTIONS_API_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=ALLAM_SUGGESTIONS_TIMEOUT_SECONDS,
            )
            if response.status_code in {400, 422}:
                payload.pop("response_format", None)
                response = requests.post(
                    f"{ALLAM_SUGGESTIONS_API_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=ALLAM_SUGGESTIONS_TIMEOUT_SECONDS,
                )

        response.raise_for_status()
        raw_suggestions = _extract_allam_suggestions_payload(response.json(), original_word, max_suggestions)
        items = [_normalise_suggestion_item(item, original_word, source="allam") for item in raw_suggestions]
        return _dedupe_suggestion_items(items)[:max_suggestions]
    except Exception as e:
        print(f"❌ خطأ في اقتراحات ALLaM: {e}")
        return []


def get_llm_correction_suggestions(word, context="", confidence=None, max_suggestions=4):
    """إرجاع اقتراحات LLM لكلمة OCR واحدة دون تطبيقها تلقائيًا."""
    original_word = (word or "").strip()
    if not original_word:
        return []

    if not LLM_SUGGESTIONS_ENABLED or not LLM_SUGGESTIONS_API_BASE_URL or not LLM_SUGGESTIONS_API_KEY:
        return []

    context = (context or "").strip()
    confidence_text = "غير متاح" if confidence is None else str(confidence)

    system_prompt = (
        "أنت مساعد متخصص في مراجعة كلمات OCR العربية والإنجليزية. "
        "أعد اقتراحات تصحيح قصيرة فقط للكلمة المحددة، ولا تغيّر المعنى، ولا تشرح خارج JSON. "
        "إذا كانت الكلمة صحيحة أو غير مؤكدة، أعد قائمة فارغة."
    )
    user_prompt = f"""راجع الكلمة المحددة المستخرجة من OCR واقترح بدائل تصحيح محتملة فقط إذا كان هناك خطأ واضح.

القواعد:
- أعد JSON صالحًا فقط بالشكل: {{"suggestions":[{{"word":"...","reason":"..."}}]}}
- اجعل عدد الاقتراحات من 0 إلى {max_suggestions}.
- الاقتراح يجب أن يكون كلمة واحدة أو عبارة قصيرة جدًا، عربيًا أو إنجليزيًا حسب السياق.
- لا تطبق التصحيح، ولا تعد النص كاملًا، ولا تضف شرحًا خارج JSON.

الكلمة: {original_word}
ثقة OCR: {confidence_text}
السياق القريب: {context}
"""

    payload = {
        "model": LLM_SUGGESTIONS_MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 700,
        "reasoning": {"effort": "minimal"},
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            f"{LLM_SUGGESTIONS_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_SUGGESTIONS_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=LLM_SUGGESTIONS_TIMEOUT_SECONDS,
        )

        # بعض النماذج أو البروكسيات قد لا تدعم response_format؛ نعيد المحاولة بدونها بدل تعطيل الميزة.
        if response.status_code in {400, 422}:
            payload.pop("response_format", None)
            response = requests.post(
                f"{LLM_SUGGESTIONS_API_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_SUGGESTIONS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=LLM_SUGGESTIONS_TIMEOUT_SECONDS,
            )

        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_json_safely(content)
        raw_suggestions = parsed.get("suggestions", [])
        if isinstance(raw_suggestions, str):
            raw_suggestions = [raw_suggestions]
        if not isinstance(raw_suggestions, list):
            raw_suggestions = []

        items = [_normalise_suggestion_item(item, original_word, source="llm") for item in raw_suggestions]
        return _dedupe_suggestion_items(items)[:max_suggestions]
    except Exception as e:
        print(f"❌ خطأ في اقتراحات LLM: {e}")
        return []


def _extract_ocr_plain_text():
    """تجميع النص المستخرج من OCR كما هو بدون تعديل منطق التعرف البصري."""
    if not ocr_results:
        return ""

    pages_text = []
    for page in ocr_results:
        page_words = [word.get("word", "") for word in page.get("text", []) if word.get("word")]
        pages_text.append(" ".join(page_words).strip())
    return "\n\n".join([page_text for page_text in pages_text if page_text])


def _clean_full_text_llm_response(text):
    """تنظيف استجابة التصحيح الكامل: إزالة المقدمات والتكرار مع الحفاظ على النص."""
    if not text:
        return ""

    cleaned = str(text).strip()

    # إزالة المقدمات الشائعة التي يضيفها النموذج أحيانًا
    intro_markers = [
        "النص المصحح:", "النص المصحّح:", "التصحيح:", "بعد التصحيح:",
        "Corrected text:", "Corrected:",
    ]
    for marker in intro_markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[-1].strip()

    # إزالة سطر افتتاحي يحتوي عبارة مثل "بعد تصحيح الأخطاء ... كالتالي:"
    lines = cleaned.split("\n")
    if lines and ("بعد تصحيح" in lines[0] or "يصبح النص" in lines[0]) and lines[0].rstrip().endswith(":"):
        cleaned = "\n".join(lines[1:]).strip()

    cleaned = cleaned.replace("```text", "").replace("```", "").strip()

    # إزالة الفقرات المكررة المتطابقة (يكرّر النموذج النص أحيانًا)
    paragraphs = [p.strip() for p in cleaned.split("\n\n")]
    seen = set()
    unique_paragraphs = []
    for paragraph in paragraphs:
        if len(paragraph) > 40:
            if paragraph in seen:
                continue
            seen.add(paragraph)
        unique_paragraphs.append(paragraph)

    return "\n\n".join(p for p in unique_paragraphs if p).strip()


def correct_full_text_with_open_source_llm(text):
    """تصحيح النص العربي كاملًا عبر LLM المفتوح المصدر المفعّل حاليًا."""
    if not text.strip() or not OSS_LLM_ENABLED or not OSS_LLM_API_BASE_URL:
        return text

    prompt = f"""صحح النص العربي التالي المستخرج عبر OCR.
التزم بالقواعد التالية بدقة:
- صحح الأخطاء الإملائية والنحوية وأخطاء OCR فقط.
- لا تضف شرحًا أو تعليقات أو عناوين.
- لا تغيّر معنى النص ولا تضف معلومات جديدة.
- أعد النص المصحح فقط.

النص الأصلي:
{text}

النص المصحح:"""

    try:
        if OSS_LLM_PROVIDER == "ollama":
            response = requests.post(
                f"{OSS_LLM_API_BASE_URL}/api/generate",
                json={
                    "model": OSS_LLM_MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 4096},
                },
                timeout=max(OSS_LLM_TIMEOUT_SECONDS, 90),
            )
            response.raise_for_status()
            data = response.json()
            corrected = _clean_full_text_llm_response(data.get("response", ""))
            return corrected or text

        if OSS_LLM_PROVIDER in {"openai", "openai_compatible", "vllm", "tgi"}:
            headers = {"Content-Type": "application/json"}
            if OSS_LLM_API_KEY:
                headers["Authorization"] = f"Bearer {OSS_LLM_API_KEY}"

            response = requests.post(
                f"{OSS_LLM_API_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": OSS_LLM_MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "أنت محرر عربي متخصص في تصحيح نصوص OCR. أعد النص المصحح فقط دون شرح."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
                timeout=max(OSS_LLM_TIMEOUT_SECONDS, 90),
            )
            response.raise_for_status()
            data = response.json()
            corrected = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            corrected = _clean_full_text_llm_response(corrected)
            return corrected or text

        print(f"❌ مزود LLM مفتوح المصدر غير مدعوم للتصحيح الكامل: {OSS_LLM_PROVIDER}")
        return text
    except Exception as e:
        print(f"❌ خطأ في التصحيح الكامل عبر LLM المفتوح المصدر: {e}")
        return text


def correct_full_text_with_groq(text):
    """تصحيح النص الكامل عبر Groq/ALLaM (نفس مزود اقتراحات المراجعة اليدوية).

    يُرجع None إذا لم يكن Groq متاحًا، حتى يتمكن المستدعي من اللجوء لبديل آخر.
    """
    if not text.strip() or LLM_PROVIDER != "groq" or not GROQ_API_KEY:
        return None

    system_prompt = (
        "أنت مدقّق لغوي عربي متخصص في تصحيح نصوص OCR. "
        "مهمتك تصحيح الأخطاء فقط، دون إعادة صياغة أو تلخيص أو اختصار أو إضافة. "
        "تحافظ على النص كما هو بكامل محتواه وطوله وترتيب فقراته، "
        "وتصلح فقط أخطاء OCR والإملاء والتشكيل وعلامات الترقيم. "
        "تعيد النص المصحّح مرة واحدة فقط، دون أي مقدمة أو تكرار."
    )
    user_prompt = f"""صحّح أخطاء OCR في النص العربي التالي.

قواعد صارمة يجب الالتزام بها:
- صحّح أخطاء OCR والإملاء والتشكيل وعلامات الترقيم فقط.
- لا تُعد صياغة النص، ولا تلخّصه، ولا تختصره — احتفظ بكل الجمل والمحتوى كما هو.
- استعن بسياق الجملة لاستنتاج الكلمة الصحيحة عند وجود تشويه (مثال: "اللسانبات" ← "اللسانيات").
- لا تضف أي كلمة أو جملة أو معلومة من عندك.
- لا تكرّر النص أبدًا — أعِده مرة واحدة فقط.
- لا تكتب أي مقدمة أو عبارة مثل "النص المصحّح:" أو "بعد التصحيح".
- حافظ على نفس طول النص وترتيب فقراته الأصلي.
- أعد النص المصحّح فقط لا غير.

النص المراد تصحيحه:
{text}
"""
    try:
        print(f"🤖 بدء التصحيح الذكي الكامل عبر Groq ({GROQ_MODEL})...")
        response = requests.post(
            f"{GROQ_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=120,
        )
        response.raise_for_status()
        corrected = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        corrected = _clean_full_text_llm_response(corrected)
        print("✅ اكتمل التصحيح الذكي عبر Groq.")
        return corrected or text
    except Exception as e:
        print(f"❌ خطأ في التصحيح الكامل عبر Groq: {e}")
        return None


BATCH_SIZE = 8  # عدد الكلمات منخفضة الثقة في كل طلب (لاحترام حد التوكنز)


def _request_corrections_batch(items):
    """يرسل دفعة كلمات منخفضة الثقة إلى Groq ويرجّع dict {id: corrected_word}."""
    if not items or LLM_PROVIDER != "groq" or not GROQ_API_KEY:
        return {}

    system_prompt = (
        "أنت مدقّق OCR للنصوص المختلطة (عربي وإنجليزي). تصحّح كل كلمة بالاعتماد على سياقها. "
        "إذا كانت الكلمة عربية لكنها ظهرت بحروف إنجليزية أو أرقام بسبب خطأ OCR، فأعدها عربية صحيحة من السياق. "
        "وإذا كانت الكلمة إنجليزية (اسم علم، مصطلح، اختصار مثل ARCIF أو ISSN) لكنها ظهرت مشوّهة، فأعدها بالإنجليزية الصحيحة. "
        "كل تصحيح كلمة واحدة. إن كانت الكلمة صحيحة فأعدها كما هي. لا تضف شرحًا. أعد JSON صالحًا فقط."
    )
    user_prompt = (
        "صحّح كلمات OCR التالية بالاعتماد على سياق كل كلمة، مع مراعاة اللغة الصحيحة:\n"
        "- الكلمة العربية التي ظهرت حروفًا إنجليزية/أرقامًا ← أعدها عربية صحيحة.\n"
        "- الكلمة الإنجليزية (اسم/مصطلح/اختصار) التي ظهرت مشوّهة ← أعدها إنجليزية صحيحة.\n"
        "- لكل عنصر أعد الكلمة المصححة (كلمة واحدة فقط، لا جملة).\n"
        'أعد JSON فقط بالشكل: {"corrections":[{"id":\u0631\u0642\u0645,"word":"\u0627\u0644\u0643\u0644\u0645\u0629"}]}\n\n'
        "الكلمات:\n" + json.dumps(items, ensure_ascii=False)
    )

    for attempt in range(5):
        try:
            response = requests.post(
                f"{GROQ_API_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
                timeout=90,
            )
        except Exception as e:
            print(f"\u274c \u062e\u0637\u0623 \u0634\u0628\u0643\u0629 \u0641\u064a \u062f\u0641\u0639\u0629 \u0627\u0644\u062a\u0635\u062d\u064a\u062d: {e}")
            return {}

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            wait_seconds = float(retry_after) if retry_after else (2 ** attempt) * 3
            print(f"\u23f3 \u062a\u062c\u0627\u0648\u0632 \u062d\u062f \u0627\u0644\u062a\u0648\u0643\u0646\u0632 (429)\u060c \u0627\u0646\u062a\u0638\u0627\u0631 {wait_seconds:.0f}s...")
            time.sleep(min(wait_seconds, 30))
            continue

        if response.status_code != 200:
            print(f"\u26a0\ufe0f Groq \u0623\u0631\u062c\u0639 {response.status_code}: {response.text[:120]}")
            return {}

        content_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_json_safely(content_text)
        corrections = parsed.get("corrections", []) if isinstance(parsed, dict) else []
        out = {}
        for correction in corrections:
            try:
                cid = int(correction.get("id"))
            except (TypeError, ValueError):
                continue
            out[cid] = correction.get("word", "")
        return out

    print("\u26a0\ufe0f \u062a\u0639\u0630\u0631 \u0625\u0643\u0645\u0627\u0644 \u0627\u0644\u062f\u0641\u0639\u0629 \u0628\u0633\u0628\u0628 \u062a\u0643\u0631\u0627\u0631 429.")
    return {}


def build_corrected_text_low_confidence_only():
    """يبني النص الكامل كما هو مع تصحيح الكلمات منخفضة الثقة فقط عبر ALLaM (بدفعات)."""
    if not ocr_results:
        return ""

    # نجمع كل الكلمات منخفضة الثقة عبر كل الصفحات بمعرّف عام
    page_word_strs = []
    flat_targets = []  # [(global_id, page_idx, word_idx, word)]
    global_id = 0
    for page_idx, page in enumerate(ocr_results):
        words = page.get("text", [])
        strs = [(w.get("word", "") or "") for w in words]
        page_word_strs.append(strs)
        for word_idx, word in enumerate(words):
            if word.get("highlighted") and strs[word_idx].strip():
                flat_targets.append((global_id, page_idx, word_idx, strs[word_idx]))
                global_id += 1

    total_low = len(flat_targets)

    if LLM_PROVIDER == "groq" and GROQ_API_KEY and flat_targets:
        corrections_map = {}
        batch_count = (len(flat_targets) + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_no, batch_start in enumerate(range(0, len(flat_targets), BATCH_SIZE), start=1):
            batch = flat_targets[batch_start:batch_start + BATCH_SIZE]
            items = []
            for (gid, p_idx, w_idx, word) in batch:
                strs = page_word_strs[p_idx]
                start = max(0, w_idx - 4)
                end = min(len(strs), w_idx + 5)
                context = " ".join(strs[start:end])
                items.append({"id": gid, "word": word, "context": context})

            print(f"\U0001f916 \u062f\u0641\u0639\u0629 {batch_no}/{batch_count} ({len(items)} \u0643\u0644\u0645\u0629)...")
            corrections_map.update(_request_corrections_batch(items))
            time.sleep(1.5)  # انتظار بسيط بين الدفعات لاحترام حد التوكنز

        # نطبّق التصحيحات على مواضعها
        for (gid, p_idx, w_idx, word) in flat_targets:
            if gid in corrections_map:
                new_word = _clean_llm_suggestion(corrections_map[gid], word)
                if new_word:
                    page_word_strs[p_idx][w_idx] = new_word

    pages_out = [" ".join(s for s in strs if s).strip() for strs in page_word_strs]
    print(f"\U0001f916 \u062a\u0645 \u062a\u0635\u062d\u064a\u062d {total_low} \u0643\u0644\u0645\u0629 \u0645\u0646\u062e\u0641\u0636\u0629 \u0627\u0644\u062b\u0642\u0629 \u0639\u0628\u0631 ALLaM (\u0627\u0644\u0628\u0627\u0642\u064a \u0643\u0645\u0627 \u0647\u0648).")
    return "\n\n".join(p for p in pages_out if p)


def get_corpus_filter_suggestions(text, threshold=50, top_n=5):
    """
    استدعاء Corpus API وتحليل التصحيحات الممكنة.
    """
    try:
        payload = {
            "text": text,
            "threshold": threshold,
            "top_n": top_n
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }

        response = requests.post(CORPUS_FILTER_API_URL, json=payload, headers=headers)

        print("🔍 إرسال الطلب إلى Corpus API:", payload)  # طباعة الطلب
        print("🔍 استجابة Corpus API:", response.status_code, response.text)  # طباعة الاستجابة

        if response.status_code == 200:
            data = response.json()

            # استخراج التصحيحات من الحقل الصحيح
            corrections = []
            if text in data:
                for suggestion in data[text]:
                    corrections.append({
                        "word": suggestion["word"],
                        "score": float(suggestion["score"]),  # تحويل score إلى عدد عشري
                        "freq": suggestion["freq"]
                    })

            return corrections
        else:
            print(f"❌ خطأ في Corpus API {response.status_code}: {response.text}")
            return []
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بـ Corpus API: {e}")
        return []

@app.route("/")
def home():
    return jsonify({"message": "API تعمل بنجاح!"})


@app.route("/upload", methods=["POST"])
def upload_file():
    """رفع ملف وحفظه في GridFS ثم تشغيل OCR"""
    global processing_complete, processing_failed, processing_error, ocr_results, original_file_name, ocr_engine_status
    processing_complete = False
    processing_failed = False
    processing_error = ""
    ocr_results = []
    ocr_engine_status = {
        "engine": "pending",
        "label": "جاري تحديد المحرك",
        "provider": "pending",
        "qari_attempted": False,
        "fallback_used": False,
        "fallback_reason": "",
    }

    if "file" not in request.files:
        return jsonify({"error": "يرجى رفع ملف"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "لم يتم اختيار ملف"}), 400

    allowed_extensions = {"pdf", "png", "jpg", "jpeg"}
    if not file.filename.lower().endswith(tuple(allowed_extensions)):
        return jsonify({"error": "صيغة الملف غير مدعومة"}), 400

    original_file_name = file.filename
    file_id = fs.put(file.read(), filename=original_file_name)

    # حفظ بيانات الملف الأصلي في قاعدة البيانات وربطه بالـ OCR لاحقًا
    file_entry = {
        "filename": original_file_name,
        "file_id": file_id,
        "ocr_file_id": None,  # سيتم تحديثه لاحقًا بعد تنفيذ OCR
        "ocr_results": None
    }
    file_doc = files_collection.insert_one(file_entry)
    file_entry["_id"] = file_doc.inserted_id

    # تشغيل OCR في الخلفية
    threading.Thread(target=process_ocr, args=(file_entry,)).start()

    return jsonify({"message": "تم رفع الملف بنجاح!", "file_id": str(file_id)})



def _summarize_ocr_engine(pages):
    """تلخيص المحرك المستخدم في آخر معالجة حتى يظهر بوضوح في الواجهة."""
    if not pages:
        return {
            "engine": "unknown",
            "label": "غير معروف",
            "provider": "unknown",
            "qari_attempted": False,
            "fallback_used": False,
            "fallback_reason": "",
        }

    fallback_page = next((page for page in pages if page.get("fallback_used")), None)
    qari_page = next((page for page in pages if page.get("ocr_engine") == "qari"), None)
    first_page = pages[0]

    if fallback_page:
        return {
            "engine": "tesseract",
            "label": "Tesseract fallback",
            "provider": "tesseract",
            "qari_attempted": bool(fallback_page.get("qari_attempted")),
            "fallback_used": True,
            "fallback_reason": fallback_page.get("fallback_reason", ""),
        }

    if qari_page:
        return {
            "engine": "qari",
            "label": "Qari OCR",
            "provider": qari_page.get("ocr_provider", "space"),
            "qari_attempted": True,
            "fallback_used": False,
            "fallback_reason": "",
        }

    return {
        "engine": first_page.get("ocr_engine", "unknown"),
        "label": first_page.get("ocr_engine_label", "غير معروف"),
        "provider": first_page.get("ocr_provider", "unknown"),
        "qari_attempted": bool(first_page.get("qari_attempted")),
        "fallback_used": bool(first_page.get("fallback_used")),
        "fallback_reason": first_page.get("fallback_reason", ""),
    }



def process_ocr(file_entry):
    """ تشغيل OCR على الملف الأصلي وحفظ النتائج في قاعدة البيانات و GridFS """
    global processing_complete, processing_failed, processing_error, ocr_results, ocr_engine_status

    # استخراج الملف الأصلي من GridFS
    file_id = file_entry["file_id"]
    file_data = fs.get(file_id).read()

    # حفظ الملف مؤقتًا لاستخدامه مع OCR
    temp_file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_entry["filename"])
    with open(temp_file_path, "wb") as f:
        f.write(file_data)

    print(f"📂 تحميل الملف من GridFS: {file_entry['filename']}")

    # تشغيل OCR وتحديث `ocr_results`. إذا تعذر Qari لا نعرض Tesseract fallback كنجاح عادي.
    try:
        ocr_results = ocr_with_highlighting(temp_file_path, UPLOAD_FOLDER)
        ocr_engine_status = _summarize_ocr_engine(ocr_results)
        print(f"🔎 OCR engine used: {ocr_engine_status['label']} (provider={ocr_engine_status['provider']}, fallback={ocr_engine_status['fallback_used']})")
    except Exception as ocr_error:
        processing_complete = False
        processing_failed = True
        processing_error = str(ocr_error)
        ocr_results = []
        ocr_engine_status = {
            "engine": "tesseract_error",
            "label": "تعذر تشغيل Tesseract OCR",
            "provider": "tesseract",
            "language": "ara+eng",
            "fallback_used": False,
            "fallback_reason": str(ocr_error),
        }
        print(f"❌ تعذر تشغيل Tesseract OCR على ملف المستخدم باللغتين العربية والإنجليزية: {ocr_error}")
        return

    # ✅ **تأكد من عدم احتواء `ocr_results` على بيانات غير صحيحة**
    if not ocr_results or not isinstance(ocr_results, list) or len(ocr_results) == 0:
        print("❌ خطأ: لم يتم استخراج أي نصوص صحيحة!")
        return

    # 🔹 تحديث قاعدة البيانات وربط نتائج OCR بالملف الأصلي
    ocr_text = "\n".join([" ".join([word["word"] for word in page["text"]]) for page in ocr_results])
    ocr_file_id = fs.put(ocr_text.encode("utf-8"), filename=f"ocr_{file_entry['filename']}.txt")

    files_collection.update_one(
        {"_id": file_entry["_id"]},
        {"$set": {"ocr_file_id": ocr_file_id, "ocr_results": ocr_results, "ocr_engine_status": ocr_engine_status}}
    )

    processing_complete = True
    print(f"✅ OCR تم بنجاح، تم تحديث `ocr_results` وأضيف إلى قاعدة البيانات.")


@app.route("/review", methods=["GET"])
def review_page():
    """إرجاع بيانات النص المستخرج واسم الملف الأصلي"""
    global processing_complete, processing_failed, processing_error, ocr_results, original_file_name, ocr_engine_status

    if processing_failed:
        return jsonify({
            "status": "failed",
            "error": "تعذر تشغيل Tesseract OCR على الملف الحالي باللغتين العربية والإنجليزية.",
            "details": processing_error,
            "ocr_engine": ocr_engine_status,
        }), 503

    if not processing_complete:
        return jsonify({"status": "processing"}), 202  # ✅ تحديث الاستجابة في حالة المعالجة

    if not ocr_results:
        return jsonify({"error": "❌ لا توجد بيانات OCR متاحة!"}), 404  # ✅ خطأ إذا لم يكن هناك نتائج

    return jsonify({
        "pages": ocr_results,  # ✅ إرسال جميع البيانات
        "original_file": original_file_name,
        "file_url": f"{API_PUBLIC_BASE_URL}/uploads/{original_file_name}",
        "ocr_engine": ocr_engine_status
    })
@app.route("/get_gemini_suggestion", methods=["POST"])
def get_gemini_suggestion_api():
    """إرجاع تصحيح Gemini لكلمة معينة"""
    data = request.json
    word = data.get("word", "")

    gemini_suggestion = get_gemini_suggestion(word)

    return jsonify({
        "gemini_suggestion": gemini_suggestion
    })

@app.route("/get_qwen_suggestion", methods=["POST"])
def get_qwen_suggestion_api():
    """إرجاع تصحيح Qwen2.5 فقط عند تفعيله صراحةً عبر متغيرات البيئة."""
    data = request.json or {}
    word = data.get("word", "")

    qwen_suggestion = get_qwen_suggestion(word)

    return jsonify({
        "qwen_suggestion": qwen_suggestion,
        "enabled": QWEN_ENABLED
    })


@app.route("/get_open_source_llm_suggestion", methods=["POST"])
def get_open_source_llm_suggestion_api():
    """إرجاع اقتراح LLM مفتوح المصدر عند تفعيله عبر متغيرات البيئة."""
    data = request.json or {}
    word = data.get("word", "").strip()

    if not word:
        return jsonify({"error": "❌ الكلمة المرسلة فارغة!"}), 400

    suggestion = get_open_source_llm_suggestion(word)
    return jsonify({
        "open_source_llm_suggestion": suggestion,
        "enabled": OSS_LLM_ENABLED,
        "provider": OSS_LLM_PROVIDER,
        "model": OSS_LLM_MODEL_NAME
    })



@app.route("/suggest_correction", methods=["POST"])
def suggest_correction_api():
    """إرجاع اقتراحات LLM لكلمة محددة في صفحة المراجعة دون تعديل نتائج OCR."""
    data = request.json or {}
    word = (data.get("word") or data.get("text") or "").strip()
    context = (data.get("context") or "").strip()
    confidence = data.get("confidence")

    if not word:
        return jsonify({"error": "❌ الكلمة المرسلة فارغة!"}), 400

    suggestions = get_llm_correction_suggestions(
        word=word,
        context=context,
        confidence=confidence,
        max_suggestions=int(data.get("max_suggestions") or 4),
    )

    return jsonify({
        "word": word,
        "suggestions": suggestions,
        "enabled": LLM_SUGGESTIONS_ENABLED,
        "provider": "openai_compatible",
        "model": LLM_SUGGESTIONS_MODEL_NAME,
        "auto_applied": False,
        "message": "اقتراحات مساعدة فقط؛ لا يتم تطبيق أي تصحيح إلا بعد اختيار المستخدم."
    })


@app.route("/get_allam_suggestions", methods=["POST"])
def get_allam_suggestions_api():
    """إرجاع اقتراحات ALLaM للكلمة المحددة مع السياق ورقم الصفحة."""
    data = request.json or {}
    word = (data.get("word") or data.get("text") or "").strip()
    if not word:
        return jsonify({"error": "❌ الكلمة المرسلة فارغة!"}), 400

    max_suggestions = max(3, min(5, int(data.get("max_suggestions") or 5)))
    suggestions = get_allam_correction_suggestions(
        word=word,
        context=(data.get("context") or "").strip(),
        page_number=data.get("page_number"),
        max_suggestions=max_suggestions,
    )

    return jsonify({
        "word": word,
        "suggestions": suggestions,
        "enabled": ALLAM_SUGGESTIONS_ENABLED,
        "provider": "allam",
        "model": ALLAM_SUGGESTIONS_MODEL_NAME,
        "endpoint_configured": bool(ALLAM_SUGGESTIONS_ENDPOINT or ALLAM_SUGGESTIONS_API_BASE_URL),
        "auto_applied": False,
    })


@app.route("/get_all_suggestions", methods=["POST"])
def get_all_suggestions_api():
    """تجميع اقتراحات Gemini الاختيارية وLLM المفتوح المصدر وcorpusfilter في استجابة واحدة."""
    data = request.json or {}
    word = data.get("word") or data.get("text", "")
    word = word.strip()

    if not word:
        return jsonify({"error": "❌ الكلمة المرسلة فارغة!"}), 400

    suggestions = []

    # المطلوب: ALLaM عبر Groq فقط كمصدر LLM، مع إبقاء CorpusFilter بجانبه.
    allam_count = 0
    for item in get_allam_correction_suggestions(
        word=word,
        context=(data.get("context") or "").strip(),
        page_number=data.get("page_number"),
        max_suggestions=5,
    ):
        if item.get("word") and item.get("word") != word:
            suggestions.append(item)
            allam_count += 1

    corpus_count = 0
    for item in get_corpus_filter_suggestions(word, threshold=50, top_n=5):
        candidate = item.get("word")
        if candidate and candidate != word:
            suggestions.append({
                "source": "corpusfilter",
                "word": candidate,
                "score": item.get("score"),
                "freq": item.get("freq")
            })
            corpus_count += 1

    print(f"🤖 اقتراحات الكلمة [{word}] → ALLaM: {allam_count} | Corpus: {corpus_count}")

    deduped = []
    seen = set()
    for item in suggestions:
        key = item.get("word", "").strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)

    return jsonify({
        "suggestions": deduped,
        "llm_provider": LLM_PROVIDER or "allam",
        "other_llm_sources_enabled": False,
        "corpusfilter_enabled": True,
        "allam_enabled": ALLAM_SUGGESTIONS_ENABLED,
        "allam_endpoint_configured": bool(ALLAM_SUGGESTIONS_ENDPOINT or ALLAM_SUGGESTIONS_API_BASE_URL),
        "allam_model": ALLAM_SUGGESTIONS_MODEL_NAME,
        "auto_applied": False
    })


@app.route("/get_corpus_suggestions", methods=["POST"])
def get_corpus_suggestions_api():
    """
    استدعاء Corpus API عبر Flask API وإرجاع التصحيحات.
    """
    data = request.json
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "❌ النص المرسل فارغ!"}), 400

    try:
        payload = {
            "text": text,
            "threshold": 50,
            "top_n": 5
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }

        print(f"🔍 إرسال الطلب إلى Corpus API: {payload}")
        response = requests.post(CORPUS_FILTER_API_URL, json=payload, headers=headers)

        print(f"🔍 استجابة Corpus API: {response.status_code} - {response.text}")

        if response.status_code == 200:
            data = response.json()

            if text in data and isinstance(data[text], list):
                corrections = [
                    {
                        "word": suggestion["word"],
                        "score": float(suggestion["score"]),
                        "freq": suggestion["freq"]
                    }
                    for suggestion in data[text] if suggestion["word"] != text  # ✅ استبعاد الكلمات المطابقة
                ]
                return jsonify({"corpus_suggestions": corrections})

        return jsonify({"corpus_suggestions": []})

    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بـ Corpus API: {e}")
        return jsonify({"error": f"❌ خطأ أثناء الاتصال بـ Corpus API: {e}"}), 500

@app.route("/auto_correct_text", methods=["POST", "GET"])
def auto_correct_text():
    """تصحيح النص المستخرج كاملًا عبر LLM وإرساله كملف TXT للتنزيل."""
    global corrected_text_file

    original_text = _extract_ocr_plain_text()
    if not original_text:
        return jsonify({"error": "❌ لا توجد نتائج OCR متاحة للتصحيح التلقائي!"}), 404

    # نصحّح الكلمات منخفضة الثقة فقط ونُبقي بقية النص كما هو حرفيًا.
    corrected_text = build_corrected_text_low_confidence_only()
    if not corrected_text:
        corrected_text = original_text

    auto_corrected_file = os.path.join(OUTPUT_FOLDER, "auto_corrected_text.txt")
    with open(auto_corrected_file, "w", encoding="utf-8") as f:
        f.write(corrected_text)

    return send_file(
        auto_corrected_file,
        as_attachment=True,
        download_name="raqeim_auto_corrected_text.txt",
        mimetype="text/plain; charset=utf-8"
    )


@app.route("/processing_status", methods=["GET"])
def processing_status():
    """إرجاع حالة المعالجة."""
    global processing_complete, processing_failed, processing_error, ocr_engine_status
    try:
        if processing_failed:
            return jsonify({
                "status": "failed",
                "error": "تعذر تشغيل Tesseract OCR على الملف الحالي باللغتين العربية والإنجليزية.",
                "details": processing_error,
                "ocr_engine": ocr_engine_status,
            }), 503
        return jsonify({"status": "done" if processing_complete else "processing", "ocr_engine": ocr_engine_status})
    except NameError:
        return jsonify({"status": "processing"})  # ✅ تأمين الحالة الافتراضية

@app.route("/uploads/<filename>", methods=["GET"])
def uploaded_file(filename):
    """إرجاع الملفات المرفوعة"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

from datetime import datetime

from datetime import datetime

from datetime import datetime

@app.route("/submit_corrections", methods=["POST"])
def submit_corrections():
    """حفظ تصحيحات المستخدم في قاعدة البيانات بعد التحقق منها."""

    print("\n✅ Received request to submit corrections.")

    data = request.json
    print(f"📥 Received Data: {json.dumps(data, ensure_ascii=False, indent=4)}")

    if not data or "filename" not in data or "corrections" not in data:
        print("❌ ERROR: Missing filename or corrections in request!")
        return jsonify({"error": "❌ Missing filename or corrections!"}), 400

    filename = data["filename"]
    corrections = data["corrections"]

    print(f"📂 Processing corrections for file: {filename}")

    if not filename or not corrections:
        print("❌ ERROR: Filename or corrections list is empty!")
        return jsonify({"error": "❌ Filename or corrections list is empty!"}), 400

    inserted_count = 0

    for page in corrections:
        page_number = page.get("page_number")
        text_data = page.get("text", [])

        for word_data in text_data:
            original_word = word_data.get("word", "").strip()
            corrected_word = word_data.get("corrected_word", "").strip()
            word_index = word_data.get("index")

            if original_word and corrected_word and original_word != corrected_word:
                correction_entry = {
                    "filename": filename,
                    "page_number": page_number,
                    "word_index": word_index,
                    "original_word": original_word,
                    "corrected_word": corrected_word,
                    "timestamp": datetime.utcnow()
                }

                try:
                    corrected_words_collection.insert_one(correction_entry)
                    _apply_correction_to_ocr_results(page_number, word_index, corrected_word)
                    inserted_count += 1
                    print(f"✅ Inserted Correction: {correction_entry}")
                except Exception as e:
                    print(f"❌ ERROR: Failed to insert correction -> {e}")
                    return jsonify({"error": f"❌ Failed to save correction: {e}"}), 500

    if inserted_count == 0:
        print("ℹ️ No new corrections were inserted; returning success so manual download can continue.")
        return jsonify({
            "message": "ℹ️ لا توجد تصحيحات جديدة للحفظ.",
            "inserted_count": 0
        }), 200

    return jsonify({
        "message": f"✅ Successfully saved {inserted_count} corrections!",
        "inserted_count": inserted_count
    }), 200




@app.route("/word_counts")
def word_counts():
    """إرجاع عدد الكلمات التي تحتاج إلى تصحيح بناءً على مستوى الثقة"""
    global ocr_results

    if not ocr_results:
        return jsonify({"level_30": 0, "level_50": 0, "level_80": 0})

    count_30, count_50, count_80 = 0, 0, 0

    for page in ocr_results:
        for word_data in page.get("text", []):
            confidence = word_data.get("confidence", 0)
            if confidence <= 30:
                count_30 += 1
            if confidence <= 50:
                count_50 += 1
            if confidence <= 80:
                count_80 += 1

    return jsonify({"level_30": count_30, "level_50": count_50, "level_80": count_80})

@app.route("/download_corrected", methods=["GET"])
def download_corrected():
    """تنزيل النص المصحح"""
    global ocr_results

    if not ocr_results:
        return jsonify({"error": "❌ لا توجد نتائج OCR متاحة!"}), 404

    # تجميع النص المصحح من الحالة الحالية بعد تطبيق التصحيحات اليدوية
    corrected_text = _build_corrected_text_from_ocr()

    # كتابة النص المصحح إلى ملف
    with open(corrected_text_file, "w", encoding="utf-8") as f:
        f.write(corrected_text)

    # إرسال الملف للتنزيل
    return send_file(corrected_text_file, as_attachment=True, download_name="corrected_text.txt", mimetype="text/plain")

#دالة إضافية لأسترجاع الملف من قاعدة البيانات
@app.route("/get_file/<file_id>/<file_type>", methods=["GET"])
def get_file(file_id, file_type):
    """استرجاع الملفات الأصلية أو ملفات OCR من GridFS"""
    try:
        file = fs.get(file_id)
        if file_type == "ocr":
            return send_file(BytesIO(file.read()), as_attachment=True, download_name=file.filename, mimetype="text/plain")
        else:
            return send_file(BytesIO(file.read()), as_attachment=True, download_name=file.filename)
    except gridfs.NoFile:
        return jsonify({"error": "❌ الملف غير موجود!"}), 404

@app.route("/list_files", methods=["GET"])
def list_files():
    """إرجاع قائمة الملفات الأصلية مع ملفات OCR المرتبطة بها"""
    files = []
    for entry in files_collection.find():
        files.append({
            "file_id": str(entry["file_id"]),
            "ocr_file_id": str(entry["ocr_file_id"]) if entry["ocr_file_id"] else None,
            "original_file_url": f"{API_PUBLIC_BASE_URL}/get_file/{entry['file_id']}/original",
            "ocr_file_url": f"{API_PUBLIC_BASE_URL}/get_file/{entry['ocr_file_id']}/ocr" if entry["ocr_file_id"] else None
        })

    return jsonify({"files": files})

@app.route("/get_corrections/<filename>", methods=["GET"])
def get_corrections(filename):
    """إرجاع جميع التصحيحات المحفوظة لملف معين"""
    corrections = list(corrected_words_collection.find({"filename": filename}, {"_id": 0}))
    return jsonify({"corrections": corrections})
@app.route("/save_correction", methods=["POST"])
def save_correction():
    """حفظ كل كلمة يتم تصحيحها فورًا في قاعدة البيانات"""
    try:
        data = request.json
        print("\n📥 البيانات المستلمة لحفظ التصحيح:", json.dumps(data, ensure_ascii=False, indent=4))

        filename = data.get("filename", "").strip()
        original_word = data.get("original_word", "").strip()
        corrected_word = data.get("corrected_word", "").strip()
        page_number = data.get("page_number", None)
        word_index = data.get("word_index", None)

        # ✅ تحقق من صحة البيانات
        if not filename or not original_word or not corrected_word or original_word == corrected_word:
            print("❌ البيانات غير صالحة!")
            return jsonify({"error": "❌ البيانات غير صالحة!"}), 400

        # ✅ إدراج أو تحديث التصحيح في قاعدة البيانات
        correction_entry = {
            "filename": filename,
            "page_number": page_number,
            "word_index": word_index,
            "original_word": original_word,
            "corrected_word": corrected_word,
            "timestamp": datetime.utcnow()
        }

        result = corrected_words_collection.update_one(
            {
                "filename": filename,
                "page_number": page_number,
                "word_index": word_index
            },
            {"$set": correction_entry},
            upsert=True  # ✅ إدخال جديد إذا لم يكن موجودًا مسبقًا
        )

        _apply_correction_to_ocr_results(page_number, word_index, corrected_word)

        print(f"✅ تم حفظ التصحيح في قاعدة البيانات: {correction_entry}")
        print(f"📊 تحديثات قاعدة البيانات - matched: {result.matched_count}, modified: {result.modified_count}")

        return jsonify({"message": "✅ تم حفظ التصحيح بنجاح!"}), 200

    except Exception as e:
        print(f"❌ خطأ أثناء حفظ التصحيح: {e}")
        return jsonify({"error": f"❌ خطأ أثناء حفظ التصحيح: {str(e)}"}), 500


# ============================================================================
# مسارات المصادقة: إنشاء حساب وتسجيل الدخول (مع تشفير كلمة المرور)
# ============================================================================

def _normalise_email(email):
    return (email or "").strip().lower()


@app.route("/register", methods=["POST"])
def register_api():
    """إنشاء حساب جديد مع تشفير كلمة المرور وحفظه في قاعدة البيانات."""
    data = request.json or {}
    name = (data.get("name") or "").strip()
    email = _normalise_email(data.get("email"))
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "❌ الاسم والبريد وكلمة المرور كلها مطلوبة."}), 400

    if len(password) < 6:
        return jsonify({"error": "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل."}), 400

    # التحقق من عدم وجود الحساب مسبقًا
    existing = users_collection.find_one({"email": email})
    if existing:
        return jsonify({"error": "❌ هذا البريد مسجّل مسبقًا. سجّل الدخول بدلاً من ذلك."}), 409

    try:
        users_collection.insert_one({
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
        })
        print(f"✅ تم إنشاء حساب جديد: {email}")
        return jsonify({
            "message": "✅ تم إنشاء الحساب بنجاح!",
            "user": {"name": name, "email": email},
        }), 201
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء الحساب: {e}")
        return jsonify({"error": f"❌ خطأ أثناء إنشاء الحساب: {str(e)}"}), 500


@app.route("/login", methods=["POST"])
def login_api():
    """تسجيل الدخول والتحقق من كلمة المرور المشفّرة."""
    data = request.json or {}
    email = _normalise_email(data.get("email"))
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "❌ البريد وكلمة المرور مطلوبان."}), 400

    user = users_collection.find_one({"email": email})
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"error": "❌ البريد أو كلمة المرور غير صحيحة."}), 401

    print(f"✅ تسجيل دخول ناجح: {email}")
    return jsonify({
        "message": "✅ تم تسجيل الدخول بنجاح!",
        "user": {"name": user.get("name", ""), "email": email},
    }), 200


if __name__ == "__main__":
    flask_host = os.getenv("FLASK_HOST", "0.0.0.0")
    flask_port = int(os.getenv("FLASK_PORT", "5000"))
    flask_debug = os.getenv("FLASK_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
    app.run(host=flask_host, port=flask_port, debug=flask_debug)