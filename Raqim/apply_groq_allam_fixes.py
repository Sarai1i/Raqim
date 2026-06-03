from pathlib import Path

backend = Path('/home/ubuntu/Raqim/Backend/app.py')
frontend = Path('/home/ubuntu/Raqim/my-app/src/components/ReviewPage.js')
start_backend = Path('/home/ubuntu/Raqim/start_backend_qari.sh')
env_path = Path('/home/ubuntu/Raqim/Backend/.env')

app = backend.read_text()

# Load .env before reading os.getenv values.
if 'def _load_local_env_file' not in app:
    marker = 'import io\n\n\napp = Flask(__name__)'
    insert = '''import io\n\n\ndef _load_local_env_file():\n    """تحميل متغيرات .env المحلية دون طباعة أي أسرار."""\n    for candidate in [os.path.join(os.path.dirname(__file__), ".env"), os.path.join(os.path.dirname(__file__), "..", ".env")]:\n        if not os.path.exists(candidate):\n            continue\n        try:\n            with open(candidate, "r", encoding="utf-8") as env_file:\n                for raw_line in env_file:\n                    line = raw_line.strip()\n                    if not line or line.startswith("#") or "=" not in line:\n                        continue\n                    key, value = line.split("=", 1)\n                    key = key.strip()\n                    value = value.strip().strip("'\\\"")\n                    if key and key not in os.environ:\n                        os.environ[key] = value\n        except Exception as exc:\n            print(f"⚠️ تعذر تحميل ملف .env المحلي: {exc}")\n\n\n_load_local_env_file()\n\n\napp = Flask(__name__)'''
    if marker not in app:
        raise SystemExit('لم أجد موضع تحميل .env في app.py')
    app = app.replace(marker, insert, 1)

old_config = '''# إعدادات ALLaM للاقتراحات اليدوية داخل نافذة المراجعة فقط.\n# يمكن تشغيله عبر endpoint مباشر أو عبر خادم OpenAI-compatible مخصص لـ ALLaM.\nALLAM_SUGGESTIONS_ENABLED = os.getenv("ALLAM_SUGGESTIONS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}\nALLAM_SUGGESTIONS_ENDPOINT = os.getenv("ALLAM_SUGGESTIONS_ENDPOINT", os.getenv("ALLAM_API_URL", "")).rstrip("/")\nALLAM_SUGGESTIONS_API_BASE_URL = os.getenv("ALLAM_SUGGESTIONS_API_BASE_URL", os.getenv("ALLAM_API_BASE_URL", "")).rstrip("/")\nALLAM_SUGGESTIONS_API_KEY = os.getenv("ALLAM_SUGGESTIONS_API_KEY", os.getenv("ALLAM_API_KEY", ""))\nALLAM_SUGGESTIONS_MODEL_NAME = os.getenv("ALLAM_SUGGESTIONS_MODEL_NAME", os.getenv("ALLAM_MODEL_NAME", "allam"))\nALLAM_SUGGESTIONS_TIMEOUT_SECONDS = float(os.getenv("ALLAM_SUGGESTIONS_TIMEOUT_SECONDS", "25"))\n'''
new_config = '''# إعدادات ALLaM للاقتراحات اليدوية داخل نافذة المراجعة فقط.\n# عند LLM_PROVIDER=groq يستخدم Groq OpenAI-compatible مع مودل ALLaM، دون تفعيل أي LLM آخر.\nLLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()\nGROQ_API_KEY = os.getenv("GROQ_API_KEY", "")\nGROQ_MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")\nGROQ_API_BASE_URL = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")\n\nALLAM_SUGGESTIONS_ENABLED = os.getenv("ALLAM_SUGGESTIONS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}\nALLAM_SUGGESTIONS_ENDPOINT = os.getenv("ALLAM_SUGGESTIONS_ENDPOINT", os.getenv("ALLAM_API_URL", "")).rstrip("/")\nALLAM_SUGGESTIONS_API_BASE_URL = os.getenv("ALLAM_SUGGESTIONS_API_BASE_URL", os.getenv("ALLAM_API_BASE_URL", "")).rstrip("/")\nALLAM_SUGGESTIONS_API_KEY = os.getenv("ALLAM_SUGGESTIONS_API_KEY", os.getenv("ALLAM_API_KEY", ""))\nALLAM_SUGGESTIONS_MODEL_NAME = os.getenv("ALLAM_SUGGESTIONS_MODEL_NAME", os.getenv("ALLAM_MODEL_NAME", "allam"))\nALLAM_SUGGESTIONS_TIMEOUT_SECONDS = float(os.getenv("ALLAM_SUGGESTIONS_TIMEOUT_SECONDS", "25"))\n\nif LLM_PROVIDER == "groq":\n    ALLAM_SUGGESTIONS_ENDPOINT = ""\n    ALLAM_SUGGESTIONS_API_BASE_URL = GROQ_API_BASE_URL\n    ALLAM_SUGGESTIONS_API_KEY = GROQ_API_KEY\n    ALLAM_SUGGESTIONS_MODEL_NAME = GROQ_MODEL\n    LLM_SUGGESTIONS_ENABLED = False\n    OSS_LLM_ENABLED = False\n'''
if old_config in app:
    app = app.replace(old_config, new_config, 1)
elif 'GROQ_API_KEY = os.getenv("GROQ_API_KEY"' not in app:
    raise SystemExit('لم أجد كتلة إعداد ALLaM القديمة')

old_prompt = '''    system_prompt = (\n        "أنت ALLaM مساعد عربي متخصص في تصحيح أخطاء OCR. "\n        "أعد اقتراحات قصيرة للكلمة المحددة فقط داخل JSON صالح، ولا تغيّر الجملة كاملة."\n    )\n    user_prompt = f"""راجع كلمة OCR التالية واقترح تصحيحات محتملة فقط إذا كان الخطأ واضحًا.\n\nالقواعد:\n- أعد JSON صالحًا فقط بالشكل: {{"suggestions":[{{"word":"...","reason":"..."}}]}}\n- عدد الاقتراحات من 0 إلى {max_suggestions}.\n- الاقتراح كلمة واحدة أو عبارة قصيرة جدًا حسب السياق.\n- لا تضف شرحًا خارج JSON.\n\nالكلمة المحددة: {original_word}\nالسياق حول الكلمة: {context}\nرقم الصفحة: {page_number}\n"""\n'''
new_prompt = '''    system_prompt = (\n        "أنت ALLaM عبر Groq، مساعد عربي متخصص في تصحيح أخطاء OCR. "\n        "أعد JSON صالحًا فقط. لا تستخدم إلا العربية في الاقتراحات. "\n        "إذا كانت الكلمة صحيحة فاجعل is_correct=true واترك suggestions فارغة."\n    )\n    user_prompt = f"""راجع كلمة OCR التالية داخل سياقها واقترح تصحيحات عربية فقط إذا كان الخطأ واضحًا.\n\nالقواعد:\n- أعد JSON صالحًا فقط بالشكل: {{"is_correct": true/false, "suggestions":[{{"word":"...","reason":"..."}}]}}\n- إذا كانت الكلمة صحيحة أو لا يوجد خطأ واضح: {{"is_correct": true, "suggestions":[]}}\n- إذا كانت خاطئة: أعد من 3 إلى {max_suggestions} اقتراحات عربية فقط قدر الإمكان.\n- الاقتراح كلمة واحدة أو عبارة عربية قصيرة جدًا حسب السياق.\n- لا تعد النص كاملًا ولا تضف شرحًا خارج JSON.\n\nالكلمة المحددة: {original_word}\nالسياق حول الكلمة: {context}\nرقم الصفحة: {page_number}\n"""\n'''
if old_prompt in app:
    app = app.replace(old_prompt, new_prompt, 1)

# Ensure Groq max suggestions is 5 and no unsupported response_format fallback issue remains acceptable.
app = app.replace('max_suggestions=4):\n    """استدعاء ALLaM الحقيقي', 'max_suggestions=5):\n    """استدعاء ALLaM الحقيقي')
app = app.replace('    max_suggestions = int(data.get("max_suggestions") or 4)\n', '    max_suggestions = max(3, min(5, int(data.get("max_suggestions") or 5)))\n')

old_route_block = '''    suggestions = []\n\n    for item in get_allam_correction_suggestions(\n        word=word,\n        context=(data.get("context") or "").strip(),\n        page_number=data.get("page_number"),\n        max_suggestions=4,\n    ):\n        if item.get("word") and item.get("word") != word:\n            suggestions.append(item)\n\n    for item in get_llm_correction_suggestions(\n        word=word,\n        context=(data.get("context") or "").strip(),\n        confidence=data.get("confidence"),\n        max_suggestions=4,\n    ):\n        if item.get("word") and item.get("word") != word:\n            suggestions.append(item)\n\n    gemini_suggestion = get_gemini_suggestion(word)\n    if gemini_suggestion and gemini_suggestion != word:\n        suggestions.append({"source": "gemini", "word": gemini_suggestion})\n\n    open_source_llm_suggestion = get_open_source_llm_suggestion(word)\n    if open_source_llm_suggestion and open_source_llm_suggestion != word:\n        suggestions.append({"source": "open_source_llm", "word": open_source_llm_suggestion})\n\n    for item in get_corpus_filter_suggestions(word, threshold=50, top_n=5):\n'''
new_route_block = '''    suggestions = []\n\n    # المطلوب: ALLaM عبر Groq فقط كمصدر LLM، مع إبقاء CorpusFilter بجانبه.\n    for item in get_allam_correction_suggestions(\n        word=word,\n        context=(data.get("context") or "").strip(),\n        page_number=data.get("page_number"),\n        max_suggestions=5,\n    ):\n        if item.get("word") and item.get("word") != word:\n            suggestions.append(item)\n\n    for item in get_corpus_filter_suggestions(word, threshold=50, top_n=5):\n'''
if old_route_block in app:
    app = app.replace(old_route_block, new_route_block, 1)
else:
    print('تنبيه: لم يتم العثور على كتلة المسار الموحّد القديمة بالكامل؛ ربما عُدلت سابقًا.')

# Add provider metadata without enabling other LLMs.
app = app.replace('''        "open_source_llm_enabled": OSS_LLM_ENABLED,\n        "open_source_llm_provider": OSS_LLM_PROVIDER,\n        "open_source_llm_model": OSS_LLM_MODEL_NAME,\n        "llm_suggestions_enabled": LLM_SUGGESTIONS_ENABLED,\n        "llm_suggestions_model": LLM_SUGGESTIONS_MODEL_NAME,\n        "allam_enabled": ALLAM_SUGGESTIONS_ENABLED,\n''', '''        "llm_provider": LLM_PROVIDER or "allam",\n        "other_llm_sources_enabled": False,\n        "corpusfilter_enabled": True,\n        "allam_enabled": ALLAM_SUGGESTIONS_ENABLED,\n''')

backend.write_text(app)

# Frontend: call combined suggestions endpoint to show Groq ALLaM + CorpusFilter in the same existing popup.
ui = frontend.read_text()
ui = ui.replace('`${API_BASE_URL}/get_allam_suggestions`', '`${API_BASE_URL}/get_all_suggestions`')
ui = ui.replace('max_suggestions: 4,', 'max_suggestions: 5,')
ui = ui.replace('''      if (nextSuggestions.length === 0) {\n        setSuggestionError("لا توجد اقتراحات مؤكدة لهذه الكلمة. يمكنك تعديلها يدويًا أو اعتمادها كما هي.");\n      }\n''', '''      if (nextSuggestions.length === 0) {\n        setSuggestionError(response.data?.message || "الكلمة تبدو صحيحة أو لا توجد اقتراحات مؤكدة. يمكنك تعديلها يدويًا أو اعتمادها كما هي.");\n      }\n''')
frontend.write_text(ui)

# Start script: source .env and avoid generic LLM suggestions defaults.
start = start_backend.read_text()
if 'set -a; source /home/ubuntu/Raqim/Backend/.env; set +a' not in start:
    start = start.replace('cd /home/ubuntu/Raqim/Backend\nmkdir -p logs\n', 'cd /home/ubuntu/Raqim/Backend\nmkdir -p logs\nif [ -f /home/ubuntu/Raqim/Backend/.env ]; then\n  set -a; source /home/ubuntu/Raqim/Backend/.env; set +a\nfi\n')
start = start.replace('export LLM_SUGGESTIONS_ENABLED="${LLM_SUGGESTIONS_ENABLED:-true}"', 'export LLM_SUGGESTIONS_ENABLED="${LLM_SUGGESTIONS_ENABLED:-false}"')
start_backend.write_text(start)

# Write/update .env with provided Groq settings, preserving unrelated existing lines when possible.
existing = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            existing[k.strip()] = v.strip()
existing.update({
    'GROQ_API_KEY': '',
    'LLM_PROVIDER': 'groq',
    'GROQ_MODEL': 'allam-2-7b',
    'ALLAM_SUGGESTIONS_ENABLED': 'true',
    'LLM_SUGGESTIONS_ENABLED': 'false',
    'OSS_LLM_ENABLED': 'false',
})
ordered = ['GROQ_API_KEY', 'LLM_PROVIDER', 'GROQ_MODEL', 'ALLAM_SUGGESTIONS_ENABLED', 'LLM_SUGGESTIONS_ENABLED', 'OSS_LLM_ENABLED']
lines = [f'{k}={existing[k]}' for k in ordered if k in existing]
for k, v in existing.items():
    if k not in ordered:
        lines.append(f'{k}={v}')
env_path.write_text('\n'.join(lines) + '\n')
print('تم تطبيق ربط Groq ALLaM وتحديث مسار الواجهة مع إبقاء CorpusFilter.')
