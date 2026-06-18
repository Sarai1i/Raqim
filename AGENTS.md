# AGENTS.md

## Cursor Cloud specific instructions

Raqim is an Arabic OCR web app with two services under `Raqim/`:

- **Backend** (`Raqim/Backend`): Flask API (`app.py`), default port `5000`. Python deps live in `requirements.txt` (DeepSeek engine) and `requirements-dots.txt` (DotOCR engine).
- **Frontend** (`Raqim/my-app`): Create React App, managed with **pnpm** (`pnpm-lock.yaml` + `pnpm-workspace.yaml`), default port `3000`.

### Running the services
- Backend: `cd Raqim/Backend && ./venv/bin/python app.py` (the update script creates `Raqim/Backend/venv`). Serves on `http://127.0.0.1:5000`.
- Frontend: `cd Raqim/my-app && pnpm start` (use `BROWSER=none` in headless VMs). Serves on `http://localhost:3000`. The frontend reads the backend URL from `REACT_APP_API_BASE_URL` (defaults to `http://127.0.0.1:5000`, see `src/config.js`).
- Auth routes are `/register` and `/login` (NOT `/signup`).

### Important caveats (non-obvious)
- **OCR inference needs an NVIDIA GPU and is NOT installed by the update script.** This VM has no GPU. The heavy OCR stack (`torch`, `transformers`, `tokenizers`, `einops`, `addict`, `easydict` from `requirements.txt`, or `requirements-dots.txt` for DotOCR) plus a multi-GB model download are only required to actually run OCR. Uploading a document for OCR will fail here, but everything else works: account register/login, the review UI, suggestions plumbing, docx export, and the CPU test suite. To do real OCR, install the GPU stack on a CUDA machine and set `OCR_ENGINE` (`deepseek` default, or `dots`).
- **MongoDB is optional.** When no Mongo is reachable, `app.py` automatically falls back to in-memory storage (`_LocalGridFS`/`_LocalCollection`), so no database is needed for development. State is then lost on restart.
- **`poppler-utils` is a required system package** for `pdf2image` (PDF → image). It is installed at the system level (captured in the VM snapshot), not by the update script.
- API keys are optional for basic runs; copy `Raqim/Backend/.env.example` to `.env` to enable Groq/ALLaM or Gemini suggestion features.

### Tests / lint / build
- Backend (CPU-only, OCR is stubbed in these — no GPU needed):
  - `cd Raqim/Backend && ./venv/bin/python -m pytest test_deepseek_infer_settings.py test_upload_processing.py`
  - `./venv/bin/python test_submit_corrections_noop.py`
  - `test_dots_ocr.py` and `evaluate_deepseek.py` require the GPU model and will not run here.
- Frontend: `pnpm build` (production build) and `pnpm test` (CRA/Jest). Lint runs as part of `react-scripts` (one pre-existing `no-unused-vars` warning in `ReviewPage.js`).
