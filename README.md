# Usage

## 1. Clone the Repository

```bash
git clone https://github.com/Sarai1i/Raqim.git
cd Raqim
```

## 2. Install Backend Dependencies

```bash
cd Backend
pip install -r requirements.txt
```

Create a `.env` file inside the `Backend` folder:

```env
GROQ_API_KEY=YOUR_GROQ_API_KEY
LLM_PROVIDER=groq
GROQ_MODEL=allam-2-7b
ALLAM_SUGGESTIONS_ENABLED=true
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_TESSERACT_LANG=ara+eng
```

## 3. Run CorpusFilter

Make sure CorpusFilter service is running on:

```text
http://127.0.0.1:9090
```

## 4. Start Backend

```bash
python app.py
```

Backend will run on:

```text
http://localhost:5000
```

## 5. Install Frontend Dependencies

Open a new terminal:

```bash
cd my-app
npm install
```

## 6. Start Frontend

```bash
npm start
```

Frontend will run on:

```text
http://localhost:3000
```

## 7. Using Raqim

1. Upload a PDF or image document.
2. Wait for OCR extraction using Tesseract OCR.
3. Review the extracted text.
4. Click any word to:

   * View CorpusFilter suggestions.
   * View ALLaM suggestions.
   * Apply manual corrections.
5. The corresponding word will be highlighted in the original document.
6. Save or download the corrected text.

## Requirements

* Python 3.10+
* Node.js 18+
* Tesseract OCR 5.x
* Arabic Language Pack (ara)
* English Language Pack (eng)
* Poppler
* CorpusFilter Service
* Groq API Key (ALLaM 2 7B)

```
```
