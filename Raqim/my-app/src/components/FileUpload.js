import React, { useState } from "react";
import axios from "axios";
import { Link, useNavigate } from "react-router-dom";
import API_BASE_URL from "../config";

const FileUpload = () => {
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const navigate = useNavigate();

  const handleFileChange = (e) => {
    if (e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setUploadStatus("");
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setUploadStatus("يرجى اختيار ملف أولًا.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setUploadStatus("جارٍ رفع الملف...");
      await axios.post(`${API_BASE_URL}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setUploadStatus("تم رفع الملف بنجاح. سننتقل الآن لمرحلة المعالجة.");
      navigate("/loading");
    } catch (error) {
      setUploadStatus("تعذر رفع الملف. حاول مرة أخرى.");
      console.error("Upload error:", error);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
      setUploadStatus("");
    }
  };

  return (
    <main className="landing-page" dir="rtl">
      <section className="landing-shell">
        <div className="landing-copy">
          <span className="eyebrow">منصة رقيم للمراجعة النصية</span>
          <h1>حوّل ملفاتك إلى نص قابل للمراجعة بثقة.</h1>
          <p>
            ارفع صورة أو ملف PDF، ثم قارن النص المستخرج مع الملف الأصلي، واعتمد التصحيحات التي تراها مناسبة بأسلوب بسيط وواضح.
          </p>
          <div className="landing-actions">
            <Link className="rq-button rq-button--secondary" to="/login">تسجيل الدخول</Link>
            <Link className="rq-button rq-button--ghost" to="/signup">إنشاء حساب</Link>
          </div>
        </div>

        <section className="upload-card" aria-label="رفع ملف للمراجعة">
          <div className="card-header-block">
            <span className="step-pill">الخطوة 1 من 3</span>
            <h2>رفع ملف جديد</h2>
            <p>اختر ملفًا واضحًا يحتوي على نص عربي أو إنجليزي لبدء رحلة المراجعة.</p>
          </div>

          <div
            className={`upload-dropzone ${dragActive ? "is-drag-active" : ""} ${file ? "has-file" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <input
              id="fileInput"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              className="upload-file-input"
              onChange={handleFileChange}
              aria-label="اختيار ملف للمراجعة"
            />
            <label htmlFor="fileInput" className="upload-dropzone-content">
              <span className="upload-icon" aria-hidden="true">↑</span>
              <span className="upload-main-text">اسحب الملف هنا أو اضغط للاختيار</span>
              <span className="upload-sub-text">الصيغ المدعومة: PDF، PNG، JPG، JPEG</span>
            </label>
          </div>

          {file && (
            <div className="selected-file-summary" aria-live="polite">
              <span className="selected-file-label">الملف المختار</span>
              <span className="selected-file-name">{file.name}</span>
            </div>
          )}

          <button className="rq-button rq-button--primary rq-button--full" onClick={handleUpload} disabled={!file}>
            متابعة المراجعة
          </button>

          {uploadStatus && <p className="status-line" aria-live="polite">{uploadStatus}</p>}
        </section>
      </section>
    </main>
  );
};

export default FileUpload;
