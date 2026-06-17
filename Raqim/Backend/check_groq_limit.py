"""فحص سريع: هل المفتاح الجديد يشتغل؟ وكم باقي من الحد؟"""
import os, requests

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ: os.environ[k] = v

key = os.getenv("GROQ_API_KEY", "")
model = os.getenv("GROQ_MODEL", "allam-2-7b")
base = os.getenv("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

print(f"المفتاح المستخدم: ...{key[-6:] if key else 'فارغ'}  (طول={len(key)})")
print(f"الموديل: {model}\n")

r = requests.post(
    f"{base}/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={"model": model, "messages": [{"role": "user", "content": "قل: تم"}], "max_tokens": 10},
    timeout=20,
)
print(f"HTTP: {r.status_code}")
# طباعة حدود الطلبات من الـ headers
for h in r.headers:
    if "ratelimit" in h.lower() or "retry" in h.lower():
        print(f"  {h}: {r.headers[h]}")
if r.status_code == 200:
    print(f"\n✅ المفتاح يشتغل! الرد: {r.json()['choices'][0]['message']['content'][:30]}")
elif r.status_code == 429:
    print(f"\n❌ 429 - الحد ممتلئ. التفاصيل: {r.text[:200]}")
else:
    print(f"\n⚠️ {r.text[:200]}")
