"""
🧪 اختبار ALLaM/Groq على كلمات صحيحة وخاطئة
شغّله داخل مجلد Backend:  python test_allam_words.py
يكشف: هل ALLaM يرجع اقتراحات لكلمة خاطئة؟ وهل صيغة الرد مفهومة؟
"""

import os
import json
import requests

# تحميل .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")
BASE = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

system_prompt = (
    "أنت ALLaM عبر Groq، مساعد عربي متخصص في تصحيح أخطاء OCR. "
    "أعد JSON صالحًا فقط. لا تستخدم إلا العربية في الاقتراحات. "
    "إذا كانت الكلمة صحيحة فاجعل is_correct=true واترك suggestions فارغة."
)

def test_word(word, context=""):
    user_prompt = f"""راجع كلمة OCR التالية داخل سياقها واقترح تصحيحات عربية فقط إذا كان الخطأ واضحًا.

القواعد:
- أعد JSON صالحًا فقط بالشكل: {{"is_correct": true/false, "suggestions":[{{"word":"...","reason":"..."}}]}}
- إذا كانت الكلمة صحيحة أو لا يوجد خطأ واضح: {{"is_correct": true, "suggestions":[]}}
- إذا كانت خاطئة: أعد من 3 إلى 5 اقتراحات عربية.

الكلمة المحددة: {word}
السياق حول الكلمة: {context}
"""
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    r = requests.post(f"{BASE}/chat/completions", headers=headers, json=payload, timeout=25)
    if r.status_code in {400, 422}:
        payload.pop("response_format", None)
        r = requests.post(f"{BASE}/chat/completions", headers=headers, json=payload, timeout=25)

    print(f"\n{'='*55}")
    print(f"🔤 الكلمة: [{word}]  | السياق: [{context or 'لا يوجد'}]")
    print(f"   HTTP: {r.status_code}")
    if r.status_code != 200:
        print(f"   ❌ خطأ: {r.text[:200]}")
        return
    content = r.json()["choices"][0]["message"]["content"]
    print(f"   📥 رد ALLaM الخام:\n   {content.strip()}")
    try:
        parsed = json.loads(content)
        sugg = parsed.get("suggestions", [])
        print(f"   ✅ is_correct={parsed.get('is_correct')} | عدد الاقتراحات={len(sugg)}")
        for s in sugg:
            print(f"      → {s.get('word')}  ({s.get('reason','')})")
    except Exception as e:
        print(f"   ⚠️ الرد مو JSON صالح: {e}")


print("🧪 اختبار ALLaM على كلمات مختلفة\n")

# كلمة صحيحة - متوقع: فارغة
test_word("مجلّة", "مجلّة اللسانيات العربية")

# كلمة خاطئة واضحة - متوقع: اقتراحات
test_word("اللسانبات", "مجلة اللسانبات العربية")

# كلمة خاطئة ثانية - متوقع: اقتراحات
test_word("الادب", "في مجال الادب")

print(f"\n{'='*55}")
print("💡 الخلاصة:")
print("  - لو الكلمة الصحيحة رجعت فارغة → ALLaM يشتغل صح")
print("  - لو الكلمات الخاطئة رجعت اقتراحات → ALLaM ممتاز ✅")
print("  - لو كلها فارغة → فيه مشكلة في الموديل أو الاستخراج")
print('='*55)
