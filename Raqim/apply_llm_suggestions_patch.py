from pathlib import Path

backend = Path('/home/ubuntu/Raqim/Backend/app.py')
frontend = Path('/home/ubuntu/Raqim/my-app/src/components/ReviewPage.js')
start_script = Path('/home/ubuntu/Raqim/start_backend_qari.sh')

app = backend.read_text(encoding='utf-8')

old = '''# تكوين LLM مفتوح المصدر اختياري للاقتراحات، مثل Ollama أو أي خادم OpenAI-compatible.\nOSS_LLM_ENABLED = os.getenv("OSS_LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}\nOSS_LLM_PROVIDER = os.getenv("OSS_LLM_PROVIDER", "ollama").strip().lower()\nOSS_LLM_API_BASE_URL = os.getenv("OSS_LLM_API_BASE_URL", "http://127.0.0.1:11434").rstrip("/")\nOSS_LLM_API_KEY = os.getenv("OSS_LLM_API_KEY", "")\nOSS_LLM_MODEL_NAME = os.getenv("OSS_LLM_MODEL_NAME", "qwen2.5:7b-instruct")\nOSS_LLM_TIMEOUT_SECONDS = float(os.getenv("OSS_LLM_TIMEOUT_SECONDS", "25"))\n'''
new = '''# تكوين LLM مفتوح المصدر اختياري للاقتراحات، مثل Ollama أو أي خادم OpenAI-compatible.\nOSS_LLM_ENABLED = os.getenv("OSS_LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}\nOSS_LLM_PROVIDER = os.getenv("OSS_LLM_PROVIDER", "ollama").strip().lower()\nOSS_LLM_API_BASE_URL = os.getenv("OSS_LLM_API_BASE_URL", "http://127.0.0.1:11434").rstrip("/")\nOSS_LLM_API_KEY = os.getenv("OSS_LLM_API_KEY", "")\nOSS_LLM_MODEL_NAME = os.getenv("OSS_LLM_MODEL_NAME", "qwen2.5:7b-instruct")\nOSS_LLM_TIMEOUT_SECONDS = float(os.getenv("OSS_LLM_TIMEOUT_SECONDS", "25"))\n\n# طبقة اقتراحات التصحيح الذكية داخل صفحة المراجعة.\n# هذه الطبقة لا تغيّر OCR ولا تعدّل النص تلقائيًا؛ هي تعيد اقتراحات فقط يختارها المستخدم يدويًا.\nLLM_SUGGESTIONS_API_BASE_URL = os.getenv("LLM_SUGGESTIONS_API_BASE_URL", os.getenv("OPENAI_API_BASE", "")).rstrip("/")\nLLM_SUGGESTIONS_API_KEY = os.getenv("LLM_SUGGESTIONS_API_KEY", os.getenv("OPENAI_API_KEY", ""))\nLLM_SUGGESTIONS_MODEL_NAME = os.getenv("LLM_SUGGESTIONS_MODEL_NAME", "gpt-5-nano")\nLLM_SUGGESTIONS_TIMEOUT_SECONDS = float(os.getenv("LLM_SUGGESTIONS_TIMEOUT_SECONDS", "20"))\nLLM_SUGGESTIONS_ENABLED = os.getenv(\n    "LLM_SUGGESTIONS_ENABLED",\n    "true" if LLM_SUGGESTIONS_API_BASE_URL and LLM_SUGGESTIONS_API_KEY else "false"\n).lower() in {"1", "true", "yes", "on"}\n'''
if old not in app:
    raise SystemExit('Backend config block not found')
app = app.replace(old, new, 1)

insert_after = '''def get_open_source_llm_suggestion(word):\n    """إرجاع اقتراح من LLM مفتوح المصدر عبر Ollama أو خادم OpenAI-compatible عند تفعيله."""\n'''
# Insert helper functions before _extract_ocr_plain_text, after get_open_source_llm_suggestion block.
marker = '\n\ndef _extract_ocr_plain_text():\n'
helper = r'''

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
        "max_tokens": 220,
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
'''
if marker not in app:
    raise SystemExit('Insertion marker not found')
app = app.replace(marker, helper + marker, 1)

route_marker = '''@app.route("/get_all_suggestions", methods=["POST"])\ndef get_all_suggestions_api():\n'''
new_route = r'''
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


'''
if route_marker not in app:
    raise SystemExit('Route marker not found')
app = app.replace(route_marker, new_route + route_marker, 1)

# Enhance get_all_suggestions with the new LLM provider for backward compatibility.
old = '''    suggestions = []\n\n    gemini_suggestion = get_gemini_suggestion(word)\n'''
new = '''    suggestions = []\n\n    for item in get_llm_correction_suggestions(\n        word=word,\n        context=(data.get("context") or "").strip(),\n        confidence=data.get("confidence"),\n        max_suggestions=4,\n    ):\n        if item.get("word") and item.get("word") != word:\n            suggestions.append(item)\n\n    gemini_suggestion = get_gemini_suggestion(word)\n'''
if old not in app:
    raise SystemExit('get_all_suggestions insertion point not found')
app = app.replace(old, new, 1)

old = '''        "open_source_llm_model": OSS_LLM_MODEL_NAME\n    })\n'''
new = '''        "open_source_llm_model": OSS_LLM_MODEL_NAME,\n        "llm_suggestions_enabled": LLM_SUGGESTIONS_ENABLED,\n        "llm_suggestions_model": LLM_SUGGESTIONS_MODEL_NAME,\n        "auto_applied": False\n    })\n'''
if old not in app:
    raise SystemExit('get_all_suggestions response block not found')
app = app.replace(old, new, 1)

backend.write_text(app, encoding='utf-8')

review = frontend.read_text(encoding='utf-8')
review = review.replace('''  const [ocrEngine, setOcrEngine] = useState(null);\n''', '''  const [ocrEngine, setOcrEngine] = useState(null);\n  const [suggestionLoading, setSuggestionLoading] = useState(false);\n  const [suggestionError, setSuggestionError] = useState("");\n  const [selectedWordInfo, setSelectedWordInfo] = useState(null);\n''', 1)

old_fetch = '''  const fetchSuggestions = async (word, event, wordIndex) => {\n    try {\n      const rect = event.target.getBoundingClientRect();\n      setPopupPosition({\n        top: rect.bottom + window.scrollY || 0,\n        left: rect.left + window.scrollX || 0,\n      });\n\n      const response = await axios.post(`${API_BASE_URL}/get_all_suggestions`, { word });\n      const combinedSuggestions = (response.data.suggestions || []).map((s) => s.word);\n      const uniqueSuggestions = [...new Set(combinedSuggestions)].filter((s) => s && s !== word);\n\n      setSuggestions(uniqueSuggestions.length > 0 ? uniqueSuggestions : [word]);\n\n      setShowSuggestions(true);\n      setInputValue(word);\n      setSelectedWordIndex(wordIndex);\n    } catch (error) {\n      console.error("❌ خطأ أثناء جلب الاقتراحات:", error);\n    }\n  };\n'''
new_fetch = '''  const buildWordContext = (wordIndex) => {\n    const words = pages[currentPage]?.text || [];\n    const start = Math.max(0, wordIndex - 7);\n    const end = Math.min(words.length, wordIndex + 8);\n    return words.slice(start, end).map((item) => item.word || "").join(" ").trim();\n  };\n\n  const normaliseSuggestionItems = (items, originalWord) => {\n    const seen = new Set();\n    return (items || [])\n      .map((item) => {\n        if (typeof item === "string") {\n          return { word: item, source: "llm", reason: "اقتراح تصحيح محتمل" };\n        }\n        return {\n          word: item.word || item.suggestion || item.text || "",\n          source: item.source || "llm",\n          reason: item.reason || "اقتراح تصحيح محتمل",\n        };\n      })\n      .filter((item) => {\n        const candidate = item.word.trim();\n        if (!candidate || candidate === originalWord || seen.has(candidate)) return false;\n        seen.add(candidate);\n        return true;\n      });\n  };\n\n  const fetchSuggestions = async (wordData, event, wordIndex) => {\n    const word = wordData.word || "";\n    const rect = event.target.getBoundingClientRect();\n    setPopupPosition({\n      top: rect.bottom + window.scrollY || 0,\n      left: rect.left + window.scrollX || 0,\n    });\n    setSuggestions([]);\n    setSuggestionError("");\n    setSuggestionLoading(true);\n    setShowSuggestions(true);\n    setInputValue(word);\n    setSelectedWordIndex(wordIndex);\n    setSelectedWordInfo(wordData);\n\n    try {\n      const response = await axios.post(`${API_BASE_URL}/suggest_correction`, {\n        word,\n        context: buildWordContext(wordIndex),\n        confidence: wordData.confidence,\n        highlighted: wordData.highlighted,\n        page_number: currentPage + 1,\n        word_index: wordIndex,\n        max_suggestions: 4,\n      });\n\n      const smartSuggestions = normaliseSuggestionItems(response.data.suggestions || [], word);\n      setSuggestions(smartSuggestions);\n      if (!response.data.enabled) {\n        setSuggestionError("اقتراحات LLM غير مفعّلة حاليًا، ويمكنك التصحيح يدويًا.");\n      } else if (smartSuggestions.length === 0) {\n        setSuggestionError("لا توجد اقتراحات ذكية مؤكدة لهذه الكلمة. يمكنك تعديلها يدويًا أو اعتمادها كما هي.");\n      }\n    } catch (error) {\n      console.error("❌ خطأ أثناء جلب اقتراحات LLM:", error);\n      setSuggestionError("تعذر جلب اقتراحات LLM الآن. يمكنك المتابعة بالتصحيح اليدوي.");\n    } finally {\n      setSuggestionLoading(false);\n    }\n  };\n'''
if old_fetch not in review:
    raise SystemExit('Frontend fetchSuggestions block not found')
review = review.replace(old_fetch, new_fetch, 1)

review = review.replace('''  const handleWordClick = (wordData, event, index) => {\n    fetchSuggestions(wordData.word, event, index);\n''', '''  const handleWordClick = (wordData, event, index) => {\n    fetchSuggestions(wordData, event, index);\n''', 1)

old_popup = '''      {showSuggestions && (\n  <div style={{ ...styles.suggestionBox, top: popupPosition.top, left: popupPosition.left }}>\n    <div style={styles.suggestionList}>\n      {suggestions.map((s, idx) => (\n        <label key={idx} style={styles.suggestionItem}>\n          <input\n            type="radio"\n            name="suggestion"\n            value={s}\n            onChange={() => setInputValue(s)}\n            style={styles.radioButton}\n          />\n          {s}\n        </label>\n      ))}\n    </div>\n\n    {/* ✅ مربع إدخال يدوي للتصحيح */}\n'''
new_popup = '''      {showSuggestions && (\n  <div style={{ ...styles.suggestionBox, top: popupPosition.top, left: popupPosition.left }}>\n    <div style={styles.suggestionHeader}>\n      <strong>اقتراحات LLM للتصحيح</strong>\n      <button style={styles.closeSuggestionButton} onClick={() => setShowSuggestions(false)}>×</button>\n    </div>\n    <div style={styles.suggestionMeta}>\n      الكلمة: <strong>{selectedWordInfo?.word || inputValue}</strong>\n      {selectedWordInfo?.confidence !== undefined && (\n        <span> · الثقة: {Math.round(Number(selectedWordInfo.confidence) || 0)}%</span>\n      )}\n    </div>\n    <div style={styles.suggestionNote}>\n      الاقتراحات مساعدة فقط، ولا يتم تعديل النص إلا عند اختيارك ثم الضغط على زر التصحيح.\n    </div>\n\n    <div style={styles.suggestionList}>\n      {suggestionLoading && <div style={styles.suggestionStatus}>جاري توليد الاقتراحات...</div>}\n      {!suggestionLoading && suggestions.map((s, idx) => {\n        const suggestionWord = typeof s === "string" ? s : s.word;\n        const suggestionReason = typeof s === "string" ? "اقتراح تصحيح محتمل" : s.reason;\n        return (\n          <label key={idx} style={styles.suggestionItem}>\n            <input\n              type="radio"\n              name="suggestion"\n              value={suggestionWord}\n              onChange={() => setInputValue(suggestionWord)}\n              style={styles.radioButton}\n            />\n            <span>\n              <strong>{suggestionWord}</strong>\n              {suggestionReason && <small style={styles.suggestionReason}>{suggestionReason}</small>}\n            </span>\n          </label>\n        );\n      })}\n      {!suggestionLoading && suggestionError && <div style={styles.suggestionStatus}>{suggestionError}</div>}\n    </div>\n\n    {/* ✅ مربع إدخال يدوي للتصحيح */}\n'''
if old_popup not in review:
    raise SystemExit('Frontend popup block not found')
review = review.replace(old_popup, new_popup, 1)

review = review.replace('''\t    تصحيح\n''', '''\t    تطبيق التصحيح المختار\n''', 1)

review = review.replace('''  suggestionBox: {\n    position: "absolute",\n    backgroundColor: "#fff",\n    padding: "15px",\n    boxShadow: "0 4px 10px rgba(0,0,0,0.2)",\n    borderRadius: "8px",\n    zIndex: 1000,\n    border: "1px solid #ddd",\n    fontFamily: "IBM Plex Sans Arabic, sans-serif",\n    width: "250px",\n    textAlign: "right",\n  },\n''', '''  suggestionBox: {\n    position: "absolute",\n    backgroundColor: "#fff",\n    padding: "16px",\n    boxShadow: "0 14px 30px rgba(0,0,0,0.22)",\n    borderRadius: "12px",\n    zIndex: 1000,\n    border: "1px solid #dbe3ef",\n    fontFamily: "IBM Plex Sans Arabic, sans-serif",\n    width: "320px",\n    textAlign: "right",\n  },\n  suggestionHeader: {\n    display: "flex",\n    alignItems: "center",\n    justifyContent: "space-between",\n    color: "#002147",\n    marginBottom: "8px",\n  },\n  closeSuggestionButton: {\n    border: "none",\n    background: "#eef3f8",\n    color: "#002147",\n    borderRadius: "50%",\n    width: "26px",\n    height: "26px",\n    cursor: "pointer",\n    fontSize: "18px",\n    lineHeight: "20px",\n  },\n  suggestionMeta: {\n    color: "#2d3748",\n    fontSize: "13px",\n    marginBottom: "6px",\n  },\n  suggestionNote: {\n    background: "#f5f9ff",\n    border: "1px solid #dbeafe",\n    borderRadius: "8px",\n    padding: "8px",\n    color: "#36506b",\n    lineHeight: 1.6,\n    fontSize: "12px",\n    marginBottom: "10px",\n  },\n''', 1)

review = review.replace('''  suggestionItem: {\n    display: "flex",\n    alignItems: "center",\n    gap: "8px",\n    cursor: "pointer",\n    padding: "6px",\n    borderRadius: "5px",\n    transition: "background 0.2s ease",\n  },\n''', '''  suggestionItem: {\n    display: "flex",\n    alignItems: "flex-start",\n    gap: "8px",\n    cursor: "pointer",\n    padding: "8px",\n    borderRadius: "8px",\n    border: "1px solid #eef2f7",\n    transition: "background 0.2s ease",\n  },\n  suggestionReason: {\n    display: "block",\n    color: "#607086",\n    lineHeight: 1.5,\n    marginTop: "2px",\n  },\n  suggestionStatus: {\n    background: "#fff8e1",\n    color: "#6b4e00",\n    borderRadius: "8px",\n    padding: "8px",\n    lineHeight: 1.6,\n    fontSize: "13px",\n  },\n''', 1)

frontend.write_text(review, encoding='utf-8')

script = start_script.read_text(encoding='utf-8')
if 'LLM_SUGGESTIONS_MODEL_NAME' not in script:
    script = script.replace('''export FLASK_DEBUG=false\n''', '''export FLASK_DEBUG=false\n\n# طبقة اقتراحات التصحيح بالذكاء الاصطناعي. لا تغيّر OCR ولا تطبق التصحيح تلقائيًا.\nexport LLM_SUGGESTIONS_ENABLED="${LLM_SUGGESTIONS_ENABLED:-true}"\nexport LLM_SUGGESTIONS_API_BASE_URL="${LLM_SUGGESTIONS_API_BASE_URL:-${OPENAI_API_BASE:-}}"\nexport LLM_SUGGESTIONS_API_KEY="${LLM_SUGGESTIONS_API_KEY:-${OPENAI_API_KEY:-}}"\nexport LLM_SUGGESTIONS_MODEL_NAME="${LLM_SUGGESTIONS_MODEL_NAME:-gpt-5-nano}"\nexport LLM_SUGGESTIONS_TIMEOUT_SECONDS="${LLM_SUGGESTIONS_TIMEOUT_SECONDS:-20}"\n''', 1)
    start_script.write_text(script, encoding='utf-8')

print('LLM suggestions patch applied successfully')
