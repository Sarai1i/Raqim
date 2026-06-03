from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path('/home/ubuntu/Raqim/ocr_test_upload.png')
img = Image.new('RGB', (1000, 420), 'white')
draw = ImageDraw.Draw(img)
font_paths = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
]
font = None
for p in font_paths:
    try:
        font = ImageFont.truetype(p, 54)
        break
    except Exception:
        pass
if font is None:
    font = ImageFont.load_default()

lines = [
    'Raqim OCR manual review test',
    'This text should be extracted',
    'correction download flow check',
]
y = 70
for line in lines:
    draw.text((70, y), line, fill='black', font=font)
    y += 95
img.save(out)
print(out)
