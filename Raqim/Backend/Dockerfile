# Raqim Backend (Flask + Tesseract OCR + Poppler)
# ------------------------------------------------
# Python 3.11 base image (slim to keep the image small).
FROM python:3.11-slim

# Avoid interactive prompts during apt installs and keep Python output unbuffered.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# System dependencies required for OCR INSIDE the container:
#   - tesseract-ocr            -> the OCR engine itself
#   - tesseract-ocr-ara        -> Arabic language pack (ara)
#   - tesseract-ocr-eng        -> English language pack (eng)
#   - poppler-utils            -> pdftoppm/pdftocairo used by pdf2image to rasterize PDFs
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# The backend resolves Tesseract via shutil.which("tesseract"); pin the binary
# path and make Arabic + English the default OCR language. TESSDATA_PREFIX is
# left to the distro default so the language packs are auto-discovered.
ENV TESSERACT_CMD=/usr/bin/tesseract \
    OCR_TESSERACT_LANG=ara+eng

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Persisted working folders for uploads and corrected output.
RUN mkdir -p uploads corrected_files

# Flask listens on 0.0.0.0:5000 inside the container.
ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000

EXPOSE 5000

CMD ["python", "app.py"]
