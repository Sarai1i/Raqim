from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path('/home/ubuntu/Raqim/ui_review_test_sample.png')
img = Image.new('RGB', (900, 420), 'white')
draw = ImageDraw.Draw(img)
font_paths = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
]
font = None
for p in font_paths:
    try:
        font = ImageFont.truetype(p, 44)
        break
    except Exception:
        pass
if font is None:
    font = ImageFont.load_default()

draw.rectangle((40, 40, 860, 380), outline=(15, 43, 74), width=3)
draw.text((120, 130), 'رقيم يساعد على مراجعة النصوص', fill=(15, 43, 74), font=font)
draw.text((120, 210), 'هذه عينة لاختبار واجهة التصحيح', fill=(49, 67, 91), font=font)
img.save(out)
print(out)
