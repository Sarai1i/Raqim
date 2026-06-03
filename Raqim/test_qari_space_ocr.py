from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from Backend.ocr_model import ocr_with_highlighting

root = Path(__file__).resolve().parent
img_path = root / "qari_arabic_sample.png"
out_dir = root / "Backend" / "uploads"

img = Image.new("RGB", (900, 360), "white")
draw = ImageDraw.Draw(img)
font = None
for candidate in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
]:
    try:
        font = ImageFont.truetype(candidate, 46)
        break
    except Exception:
        pass
if font is None:
    font = ImageFont.load_default()

# PIL does not shape Arabic perfectly without libraqm in all environments, but the
# sample is sufficient for testing the application flow and API call.
draw.text((120, 120), "هذا اختبار للتعرف الضوئي العربي", fill="black", font=font)
draw.text((120, 190), "رقيم يستخدم نموذج قاري", fill="black", font=font)
img.save(img_path)

results = ocr_with_highlighting(str(img_path), str(out_dir))
print("pages", len(results))
print("words", len(results[0]["text"]) if results else 0)
print("sample", " ".join(w["word"] for w in results[0]["text"][:12]) if results else "")
