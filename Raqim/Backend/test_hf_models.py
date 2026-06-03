import json
import os
import requests

BACKEND_PID_FILE = "/home/ubuntu/Raqim/Backend/logs/backend_hf.pid"


def read_backend_env_var(name: str) -> str:
    try:
        with open(BACKEND_PID_FILE, "r", encoding="utf-8") as f:
            pid = f.read().strip()
        with open(f"/proc/{pid}/environ", "rb") as f:
            environ = f.read().split(b"\x00")
        prefix = (name + "=").encode("utf-8")
        for item in environ:
            if item.startswith(prefix):
                return item[len(prefix):].decode("utf-8")
    except Exception:
        return ""
    return ""


token = os.environ.get("HF_TOKEN") or read_backend_env_var("OSS_LLM_API_KEY")
if not token:
    raise SystemExit("HF token not available")

models = [
    "openai/gpt-oss-120b:fastest",
    "Qwen/Qwen3-32B:fastest",
    "meta-llama/Llama-3.3-70B-Instruct:fastest",
]

words = ["الرحمنن", "الكتلب", "مسوول"]

system_prompt = (
    "أنت مصحح OCR عربي. مهمتك إرجاع التصحيح الإملائي الأقرب فقط. "
    "لا تشرح ولا تضع علامات تنصيص. إذا كانت الكلمة صحيحة أعدها كما هي."
)

results = []
for model in models:
    for word in words:
        try:
            response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"صحح كلمة OCR العربية التالية وأعد كلمة واحدة فقط: {word}"},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 32,
                },
                timeout=45,
            )
            status = response.status_code
            if status == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                results.append({"model": model, "word": word, "status": status, "content": content})
            else:
                short_error = response.text[:300].replace(token, "[REDACTED]")
                results.append({"model": model, "word": word, "status": status, "error": short_error})
        except Exception as exc:
            results.append({"model": model, "word": word, "status": "exception", "error": str(exc)[:300]})

print(json.dumps(results, ensure_ascii=False, indent=2))
