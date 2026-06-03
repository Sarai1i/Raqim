from pathlib import Path

root = Path('/home/ubuntu/Raqim/my-app/src')
components = root / 'components'

(root / 'App.js').write_text(r'''import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import FileUpload from "./components/FileUpload";
import Navbar from "./components/Navbar";
import LoadingPage from "./components/LoadingPage";
import CorrectionChoicePage from "./components/CorrectionChoicePage";
import ReviewPage from "./components/ReviewPage";
import LoginPage from "./components/LoginPage";
import "./App.css";

function App() {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/" element={<FileUpload />} />
        <Route path="/login" element={<LoginPage mode="login" />} />
        <Route path="/signup" element={<LoginPage mode="signup" />} />
        <Route path="/loading" element={<LoadingPage />} />
        <Route path="/correction-choice" element={<CorrectionChoicePage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
''', encoding='utf-8')

(components / 'Navbar.js').write_text(r'''import React from "react";
import { Link } from "react-router-dom";

const Navbar = () => {
  return (
    <nav className="rq-navbar" dir="rtl" aria-label="شريط رقيم الرئيسي">
      <div className="rq-navbar__inner">
        <Link className="rq-navbar__brand" to="/" aria-label="العودة إلى الصفحة الرئيسية">
          <span className="rq-navbar__mark">ر</span>
          <span>رقيم</span>
        </Link>
      </div>
    </nav>
  );
};

export default Navbar;
''', encoding='utf-8')

(components / 'LoginPage.js').write_text(r'''import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

const LoginPage = ({ mode = "login" }) => {
  const isSignup = mode === "signup";
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [message, setMessage] = useState("");

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!form.email || !form.password || (isSignup && !form.name)) {
      setMessage("فضلاً أكمل البيانات المطلوبة للمتابعة.");
      return;
    }

    localStorage.setItem("raqim_mock_user", JSON.stringify({
      name: form.name || "مستخدم رقيم",
      email: form.email,
    }));
    setMessage(isSignup ? "تم إنشاء حساب تجريبي بنجاح." : "تم تسجيل الدخول تجريبيًا.");
    setTimeout(() => navigate("/"), 550);
  };

  return (
    <main className="auth-page" dir="rtl">
      <section className="auth-shell">
        <div className="auth-visual-card">
          <span className="eyebrow">تجربة آمنة للمراجعة</span>
          <h1>راجع النصوص العربية بثقة وهدوء.</h1>
          <p>
            حساب رقيم التجريبي يساعدك على الدخول إلى تجربة الرفع والمراجعة بواجهة مرتبة، مع إبقاء قرار التصحيح بيد المستخدم.
          </p>
          <div className="auth-feature-grid">
            <span>مراجعة بصرية</span>
            <span>تصحيح اختياري</span>
            <span>واجهة عربية</span>
          </div>
        </div>

        <form className="auth-card" onSubmit={handleSubmit}>
          <span className="eyebrow">{isSignup ? "إنشاء حساب" : "تسجيل الدخول"}</span>
          <h2>{isSignup ? "ابدأ مع رقيم" : "مرحبًا بعودتك"}</h2>
          <p className="auth-muted">
            هذه واجهة دخول تجريبية مؤقتة، وسيتم ربطها لاحقًا بنظام الحسابات عند اعتماد البنية الخلفية.
          </p>

          {isSignup && (
            <label className="form-field">
              <span>الاسم</span>
              <input name="name" value={form.name} onChange={handleChange} placeholder="اكتب اسمك" />
            </label>
          )}

          <label className="form-field">
            <span>البريد الإلكتروني</span>
            <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="name@example.com" dir="ltr" />
          </label>

          <label className="form-field">
            <span>كلمة المرور</span>
            <input name="password" type="password" value={form.password} onChange={handleChange} placeholder="••••••••" dir="ltr" />
          </label>

          {message && <div className="inline-alert">{message}</div>}

          <button className="rq-button rq-button--primary" type="submit">
            {isSignup ? "إنشاء حساب تجريبي" : "دخول"}
          </button>

          <p className="auth-switch">
            {isSignup ? "لديك حساب؟" : "ليس لديك حساب؟"}{" "}
            <Link to={isSignup ? "/login" : "/signup"}>{isSignup ? "تسجيل الدخول" : "إنشاء حساب"}</Link>
          </p>
        </form>
      </section>
    </main>
  );
};

export default LoginPage;
''', encoding='utf-8')

(components / 'FileUpload.js').write_text(r'''import React, { useState } from "react";
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
''', encoding='utf-8')

(components / 'CorrectionChoicePage.js').write_text(r'''import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import API_BASE_URL from "../config";

const CorrectionChoicePage = () => {
  const navigate = useNavigate();
  const [isAutoCorrecting, setIsAutoCorrecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleAutoCorrection = async () => {
    setIsAutoCorrecting(true);
    setErrorMessage("");

    try {
      const response = await fetch(`${API_BASE_URL}/auto_correct_text`, {
        method: "POST",
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "تعذر إنشاء الملف المصحح.");
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = "raqeim_auto_corrected_text.txt";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error("خطأ أثناء التصحيح الذكي:", error);
      setErrorMessage("تعذر إكمال التصحيح الذكي حاليًا. يمكنك استخدام المراجعة اليدوية أو المحاولة مرة أخرى.");
    } finally {
      setIsAutoCorrecting(false);
    }
  };

  return (
    <main className="choice-page" dir="rtl">
      <section className="choice-shell">
        <div className="choice-intro">
          <span className="step-pill">الخطوة 3 من 3</span>
          <h1>اختر طريقة التصحيح المناسبة</h1>
          <p>
            يمكنك مراجعة الكلمات بنفسك مع اقتراحات مساعدة، أو تنزيل نسخة مصححة ذكيًا. في كل الحالات، يبقى التحكم النهائي بيدك.
          </p>
        </div>

        {errorMessage && <p className="choice-error">{errorMessage}</p>}

        <div className="choice-grid">
          <article className="choice-card choice-card--featured">
            <div className="choice-card__icon">✓</div>
            <h2>التصحيح اليدوي</h2>
            <p>
              قارن الملف الأصلي بالنص المستخرج، راجع الكلمات المظللة، واختر التصحيح المناسب كلمة بكلمة.
            </p>
            <ul>
              <li>مقارنة مباشرة مع الملف الأصلي</li>
              <li>اقتراحات تظهر بجانب الكلمة</li>
              <li>اعتماد التصحيح عند اختيارك فقط</li>
            </ul>
            <button className="rq-button rq-button--primary rq-button--full" onClick={() => navigate("/review")} disabled={isAutoCorrecting}>
              البدء بالمراجعة اليدوية
            </button>
          </article>

          <article className="choice-card">
            <div className="choice-card__icon">✨</div>
            <h2>التصحيح الذكي</h2>
            <p>
              إنشاء ملف نصي مصحح بصورة آلية للاستخدام السريع عندما لا تحتاج إلى مراجعة كل كلمة بنفسك.
            </p>
            <ul>
              <li>مناسب للمسودات السريعة</li>
              <li>تنزيل ملف TXT مباشرة</li>
              <li>يمكن مراجعته لاحقًا يدويًا</li>
            </ul>
            <button className="rq-button rq-button--secondary rq-button--full" onClick={handleAutoCorrection} disabled={isAutoCorrecting}>
              {isAutoCorrecting ? "جارٍ إنشاء الملف..." : "تنزيل نسخة مصححة"}
            </button>
          </article>
        </div>
      </section>
    </main>
  );
};

export default CorrectionChoicePage;
''', encoding='utf-8')

(components / 'LoadingPage.js').write_text(r'''import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import API_BASE_URL from "../config";

const LoadingPage = () => {
  const navigate = useNavigate();
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const checkProcessingStatus = setInterval(async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/processing_status`);

        if (response.data.status === "done") {
          clearInterval(checkProcessingStatus);
          navigate("/correction-choice");
        }

        if (response.data.status === "failed") {
          clearInterval(checkProcessingStatus);
          setErrorMessage(response.data.error || "تعذر استخراج النص من الملف الحالي.");
        }
      } catch (error) {
        const data = error.response?.data;
        if (data?.status === "failed") {
          clearInterval(checkProcessingStatus);
          setErrorMessage(data.error || "تعذر استخراج النص من الملف الحالي.");
          return;
        }
        console.error("خطأ أثناء التحقق من حالة المعالجة:", error);
      }
    }, 1500);

    return () => clearInterval(checkProcessingStatus);
  }, [navigate]);

  return (
    <main className="processing-page" dir="rtl">
      <section className="processing-card">
        <span className="step-pill">الخطوة 2 من 3</span>
        {errorMessage ? (
          <>
            <h1>تعذر تجهيز الملف</h1>
            <p className="processing-error">{errorMessage}</p>
            <button className="rq-button rq-button--primary" onClick={() => navigate("/")}>رفع ملف آخر</button>
          </>
        ) : (
          <>
            <h1>جاري تجهيز النص للمراجعة</h1>
            <p>نرتّب النص المستخرج ونحضّر الكلمات التي تحتاج إلى انتباهك في صفحة مراجعة واضحة.</p>
            <div className="loader" aria-label="جاري المعالجة"></div>
          </>
        )}
      </section>
    </main>
  );
};

export default LoadingPage;
''', encoding='utf-8')

(components / 'ReviewPage.js').write_text(r'''import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import API_BASE_URL from "../config";

const ReviewPage = () => {
  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [highlightedBox, setHighlightedBox] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const [selectedWordIndex, setSelectedWordIndex] = useState(null);
  const [correctionProgress, setCorrectionProgress] = useState(0);
  const [totalHighlightedWords, setTotalHighlightedWords] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [selectedWordInfo, setSelectedWordInfo] = useState(null);
  const [filename, setFilename] = useState("");
  const imageRef = useRef(null);

  useEffect(() => {
    const fetchTextData = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/review`);
        const loadedPages = response.data.pages || [];
        setPages(loadedPages);
        setFilename(response.data.original_file || "");

        const highlightedCount = loadedPages.reduce((acc, page) => {
          return acc + (page.text || []).filter((word) => word.highlighted).length;
        }, 0);
        setTotalHighlightedWords(highlightedCount);
        setCorrectionProgress(highlightedCount === 0 ? 100 : 0);
      } catch (error) {
        console.error("خطأ في تحميل بيانات المراجعة:", error);
      }
    };

    fetchTextData();
  }, []);

  if (pages.length === 0) {
    return (
      <main className="review-page" dir="rtl">
        <section className="processing-card">
          <span className="step-pill">المراجعة</span>
          <h1>جاري تحميل النصوص...</h1>
          <p>سنفتح صفحة المقارنة بمجرد أن تكون بيانات الملف جاهزة.</p>
          <div className="loader" aria-label="جاري التحميل"></div>
        </section>
      </main>
    );
  }

  const currentWords = pages[currentPage]?.text || [];
  const remainingCount = pages.reduce((acc, page) => acc + (page.text || []).filter((word) => word.highlighted).length, 0);

  const buildWordContext = (wordIndex) => {
    const start = Math.max(0, wordIndex - 7);
    const end = Math.min(currentWords.length, wordIndex + 8);
    return currentWords.slice(start, end).map((item) => item.word || "").join(" ").trim();
  };

  const normaliseSuggestionItems = (items, originalWord) => {
    const seen = new Set();
    return (items || [])
      .map((item) => {
        if (typeof item === "string") return { word: item };
        return { word: item.word || item.suggestion || item.text || "" };
      })
      .filter((item) => {
        const candidate = item.word.trim();
        if (!candidate || candidate === originalWord || seen.has(candidate)) return false;
        seen.add(candidate);
        return true;
      });
  };

  const updateOriginalHighlight = (wordData) => {
    if (!imageRef.current || !wordData?.bounding_box) {
      setHighlightedBox(null);
      return;
    }

    const imageRect = imageRef.current.getBoundingClientRect();
    const scaleX = imageRect.width / (wordData.bounding_box.original_width || 1);
    const scaleY = imageRect.height / (wordData.bounding_box.original_height || 1);

    setHighlightedBox({
      x: wordData.bounding_box.x * scaleX,
      y: wordData.bounding_box.y * scaleY,
      w: wordData.bounding_box.w * scaleX,
      h: wordData.bounding_box.h * scaleY,
    });
  };

  const fetchSuggestions = async (wordData, event, wordIndex) => {
    const word = wordData.word || "";
    const rect = event.currentTarget.getBoundingClientRect();
    setMenuPosition({
      top: rect.bottom + window.scrollY + 8,
      left: Math.max(16, Math.min(rect.left + window.scrollX, window.innerWidth - 380)),
    });
    setSuggestions([]);
    setSuggestionError("");
    setSuggestionLoading(true);
    setShowSuggestions(true);
    setInputValue(word);
    setSelectedWordIndex(wordIndex);
    setSelectedWordInfo(wordData);

    try {
      const response = await axios.post(`${API_BASE_URL}/suggest_correction`, {
        word,
        context: buildWordContext(wordIndex),
        confidence: wordData.confidence,
        highlighted: wordData.highlighted,
        page_number: currentPage + 1,
        word_index: wordIndex,
        max_suggestions: 4,
      });

      const nextSuggestions = normaliseSuggestionItems(response.data.suggestions || [], word);
      setSuggestions(nextSuggestions);
      if (nextSuggestions.length === 0) {
        setSuggestionError("لا توجد اقتراحات مؤكدة لهذه الكلمة. يمكنك تعديلها يدويًا أو اعتمادها كما هي.");
      }
    } catch (error) {
      console.error("خطأ أثناء جلب الاقتراحات:", error);
      setSuggestionError("تعذر تجهيز الاقتراحات الآن. يمكنك المتابعة بالتصحيح اليدوي.");
    } finally {
      setSuggestionLoading(false);
    }
  };

  const handleWordClick = (wordData, event, index) => {
    fetchSuggestions(wordData, event, index);
    updateOriginalHighlight(wordData);
  };

  const updateProgress = (pagesToEvaluate = pages) => {
    const correctedCount = pagesToEvaluate.reduce((acc, page) => {
      return acc + (page.text || []).filter((word) => word.corrected && word.wasHighlighted).length;
    }, 0);

    if (totalHighlightedWords > 0) {
      const progress = Math.round((correctedCount / totalHighlightedWords) * 100);
      setCorrectionProgress(progress);
      setStatusMessage(progress === 100
        ? "تمت مراجعة جميع الكلمات المظللة. يمكنك تنزيل النص الآن."
        : "يمكنك تنزيل النص في أي وقت أو متابعة مراجعة الكلمات المتبقية."
      );
    } else {
      setCorrectionProgress(100);
      setStatusMessage("لا توجد كلمات مظللة حاليًا، ويمكنك مراجعة النص يدويًا عند الحاجة.");
    }
  };

  const handleCorrection = async (correction) => {
    if (!correction.trim() || selectedWordIndex === null) return;

    const updatedPages = [...pages];
    const wordData = updatedPages[currentPage].text[selectedWordIndex];
    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      word: correction,
      corrected_word: correction,
      highlighted: false,
      wasHighlighted: true,
      corrected: true,
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();

    try {
      await axios.post(`${API_BASE_URL}/save_correction`, {
        filename,
        original_word: originalWord,
        corrected_word: correction,
        page_number: currentPage + 1,
        word_index: selectedWordIndex,
      });
    } catch (error) {
      console.error("خطأ أثناء حفظ التصحيح:", error);
    }
  };

  const handleMarkCorrect = () => {
    if (selectedWordIndex === null) return;

    const updatedPages = [...pages];
    const wordData = updatedPages[currentPage].text[selectedWordIndex];
    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      corrected_word: wordData.word,
      highlighted: false,
      wasHighlighted: true,
      corrected: true,
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();
  };

  const buildPlainTextFromPages = (pagesToExport = pages) => {
    return pagesToExport
      .map((page) => (page.text || []).map((word) => word.word || "").join(" ").trim())
      .filter(Boolean)
      .join("\n\n");
  };

  const buildCorrectionsPayload = (pagesToSubmit = pages) => {
    return pagesToSubmit.map((page, pageIndex) => ({
      page_number: page.page_number || pageIndex + 1,
      text: (page.text || []).map((word, wordIndex) => {
        const originalWord = word.original_word || word.originalWord || word.word;
        const correctedWord = word.corrected_word || (word.corrected ? word.word : "");
        return {
          index: word.index ?? wordIndex,
          word: originalWord,
          corrected_word: correctedWord,
        };
      }),
    }));
  };

  const submitCorrectionsToServer = async (pagesToSubmit = pages) => {
    if (!filename) return;

    try {
      await axios.post(`${API_BASE_URL}/submit_corrections`, {
        filename,
        corrections: buildCorrectionsPayload(pagesToSubmit),
      });
    } catch (error) {
      console.warn("لم يتم حفظ كل التصحيحات دفعة واحدة، وسيتم تنزيل النص من حالة الواجهة الحالية:", error);
    }
  };

  const handleDownloadCorrectedText = async () => {
    await submitCorrectionsToServer(pages);

    const correctedText = buildPlainTextFromPages(pages);
    const blob = new Blob([correctedText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "raqeim_manual_corrected_text.txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setStatusMessage("تم تنزيل النص حسب التصحيحات الحالية، ويمكنك الاستمرار في المراجعة إذا رغبت.");
  };

  const goToNextWord = () => {
    if (!pages[currentPage]?.text) return;
    let nextIndex = (selectedWordIndex ?? -1) + 1;
    while (nextIndex < pages[currentPage].text.length && !pages[currentPage].text[nextIndex].highlighted) {
      nextIndex++;
    }

    if (nextIndex < pages[currentPage].text.length) {
      setSelectedWordIndex(nextIndex);
      setShowSuggestions(false);
    } else {
      goToNextPage();
    }
  };

  const goToNextPage = () => {
    if (currentPage < pages.length - 1) {
      const nextPageIndex = currentPage + 1;
      const firstHighlightedIndex = pages[nextPageIndex]?.text?.findIndex((word) => word.highlighted) ?? -1;
      setCurrentPage(nextPageIndex);
      setSelectedWordIndex(firstHighlightedIndex >= 0 ? firstHighlightedIndex : null);
      setShowSuggestions(false);
      setHighlightedBox(null);
    }
  };

  const goToPreviousPage = () => {
    if (currentPage > 0) {
      setCurrentPage(currentPage - 1);
      setSelectedWordIndex(null);
      setShowSuggestions(false);
      setHighlightedBox(null);
    }
  };

  return (
    <main className="review-page" dir="rtl">
      <header className="review-topbar">
        <div>
          <span className="step-pill">المراجعة اليدوية</span>
          <h1>قارن الملف الأصلي بالنص المستخرج</h1>
          <p>الكلمات التي تحتاج إلى انتباهك مظللة داخل النص. اضغط على أي كلمة لعرض اقتراحات التصحيح بجانبها.</p>
        </div>
        <button className="rq-button rq-button--primary" onClick={handleDownloadCorrectedText}>تنزيل النص الحالي</button>
      </header>

      <section className="review-progress-card">
        <div className="review-progress-copy">
          <strong>تقدم المراجعة</strong>
          <span>{statusMessage || "ابدأ بالضغط على الكلمات المظللة لمراجعتها."}</span>
        </div>
        <div className="review-progress-track" aria-label={`نسبة التقدم ${correctionProgress}%`}>
          <div className="review-progress-fill" style={{ width: `${correctionProgress}%` }}>
            {correctionProgress}%
          </div>
        </div>
        <span className="remaining-pill">{remainingCount} كلمة تحتاج مراجعة</span>
      </section>

      <section className="review-workspace">
        <article className="review-panel review-panel--original">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">الملف الأصلي</span>
              <h2>معاينة الصفحة</h2>
            </div>
            <span className="page-chip">{currentPage + 1} / {pages.length}</span>
          </div>
          <div className="original-preview">
            <img
              ref={imageRef}
              src={`${API_BASE_URL}/uploads/original_page_${currentPage + 1}.png?t=${Date.now()}`}
              alt="معاينة الصفحة الأصلية"
              className="original-image"
            />
            {highlightedBox && (
              <div
                className="original-word-marker"
                style={{
                  top: highlightedBox.y,
                  left: highlightedBox.x,
                  width: highlightedBox.w,
                  height: highlightedBox.h,
                }}
              />
            )}
          </div>
        </article>

        <article className="review-panel review-panel--text">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">النص المستخرج</span>
              <h2>اضغط على الكلمة للمراجعة</h2>
            </div>
            <span className="legend-dot"><i></i> كلمات تحتاج انتباه</span>
          </div>

          <div className="extracted-text" onClick={(event) => event.stopPropagation()}>
            {currentWords.map((word, index) => {
              const isSelected = selectedWordIndex === index && showSuggestions;
              const className = [
                "review-word",
                word.highlighted ? "review-word--flagged" : "",
                word.corrected ? "review-word--corrected" : "",
                isSelected ? "review-word--selected" : "",
              ].filter(Boolean).join(" ");

              return (
                <span
                  key={index}
                  className={className}
                  onClick={(event) => handleWordClick(word, event, index)}
                  title={word.highlighted ? "كلمة تحتاج مراجعة" : "اضغط للمراجعة"}
                >
                  {word.word}
                </span>
              );
            })}
          </div>
        </article>
      </section>

      {showSuggestions && (
        <aside className="word-suggestions-menu" style={{ top: menuPosition.top, left: menuPosition.left }} dir="rtl">
          <div className="suggestions-head">
            <div>
              <span>الكلمة الحالية</span>
              <strong>{selectedWordInfo?.word || inputValue}</strong>
            </div>
            <button className="suggestions-close" onClick={() => setShowSuggestions(false)} aria-label="إغلاق الاقتراحات">×</button>
          </div>

          <div className="suggestions-section">
            <span className="suggestions-label">اقتراحات التصحيح</span>
            {suggestionLoading && <div className="suggestions-state">جاري تجهيز الاقتراحات...</div>}
            {!suggestionLoading && suggestions.map((suggestion, idx) => {
              const suggestionWord = typeof suggestion === "string" ? suggestion : suggestion.word;
              return (
                <button
                  key={idx}
                  className="suggestion-option"
                  type="button"
                  onClick={() => setInputValue(suggestionWord)}
                >
                  {suggestionWord}
                </button>
              );
            })}
            {!suggestionLoading && suggestionError && <div className="suggestions-state">{suggestionError}</div>}
          </div>

          <label className="manual-correction-field">
            <span>تصحيح يدوي</span>
            <input value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="اكتب التصحيح هنا" />
          </label>

          <div className="suggestions-actions">
            <button className="rq-button rq-button--primary" onClick={() => handleCorrection(inputValue)}>اعتماد التصحيح</button>
            <button className="rq-button rq-button--ghost" onClick={handleMarkCorrect}>الكلمة صحيحة</button>
          </div>
        </aside>
      )}

      <nav className="review-pagination" aria-label="التنقل بين الصفحات">
        <button className="rq-button rq-button--secondary" onClick={goToPreviousPage} disabled={currentPage === 0}>الصفحة السابقة</button>
        <span>الصفحة {currentPage + 1} من {pages.length}</span>
        <button className="rq-button rq-button--secondary" onClick={goToNextPage} disabled={currentPage === pages.length - 1}>الصفحة التالية</button>
      </nav>
    </main>
  );
};

export default ReviewPage;
''', encoding='utf-8')

(root / 'App.css').write_text(r'''@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700;800&display=swap');

:root {
  --rq-ink: #0f172a;
  --rq-muted: #64748b;
  --rq-soft: #f6f9fc;
  --rq-card: #ffffff;
  --rq-line: #dbe7f3;
  --rq-blue-900: #0a2540;
  --rq-blue-800: #123c69;
  --rq-blue-700: #145da0;
  --rq-blue-600: #1d70b8;
  --rq-blue-100: #eaf4ff;
  --rq-cyan: #3fb9d4;
  --rq-gold: #ffe8a3;
  --rq-gold-strong: #f4bf3a;
  --rq-green: #16a34a;
  --rq-danger: #b42318;
  --rq-shadow: 0 20px 60px rgba(15, 23, 42, 0.10);
  --rq-radius-lg: 28px;
  --rq-radius-md: 18px;
  --rq-radius-sm: 12px;
}

* { box-sizing: border-box; }

html, body, #root { min-height: 100%; }

body {
  margin: 0;
  background: radial-gradient(circle at top right, rgba(63, 185, 212, 0.16), transparent 32%), #f7fbff;
  color: var(--rq-ink);
  direction: rtl;
  font-family: 'IBM Plex Sans Arabic', sans-serif !important;
  text-align: right;
}

button, input, textarea, a, span, p, h1, h2, h3, h4, h5, h6, label {
  font-family: 'IBM Plex Sans Arabic', sans-serif !important;
}

a { color: inherit; text-decoration: none; }

.rq-navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid rgba(219, 231, 243, 0.9);
  backdrop-filter: blur(16px);
}

.rq-navbar__inner {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  min-height: 70px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.rq-navbar__brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--rq-blue-900);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.rq-navbar__mark {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(135deg, var(--rq-blue-800), var(--rq-cyan));
  box-shadow: 0 12px 24px rgba(20, 93, 160, 0.22);
}

.eyebrow, .step-pill, .panel-kicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  border-radius: 999px;
  background: var(--rq-blue-100);
  color: var(--rq-blue-700);
  font-size: 13px;
  font-weight: 800;
  padding: 7px 14px;
}

.rq-button {
  border: 0;
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 46px;
  padding: 12px 22px;
  font-size: 15px;
  font-weight: 800;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.rq-button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.rq-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.rq-button--primary {
  background: linear-gradient(135deg, var(--rq-blue-800), var(--rq-blue-600));
  color: #fff;
  box-shadow: 0 14px 26px rgba(20, 93, 160, 0.22);
}

.rq-button--secondary {
  background: #eef6ff;
  color: var(--rq-blue-800);
  border: 1px solid #cfe4fa;
}

.rq-button--ghost {
  background: #fff;
  color: var(--rq-blue-800);
  border: 1px solid var(--rq-line);
}

.rq-button--full { width: 100%; }

.landing-page, .auth-page, .choice-page, .processing-page, .review-page {
  min-height: calc(100vh - 70px);
}

.landing-page {
  padding: 64px 20px;
  background: linear-gradient(180deg, #f7fbff 0%, #eef7ff 100%);
}

.landing-shell {
  width: min(1180px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  align-items: center;
  gap: 34px;
}

.landing-copy h1, .auth-visual-card h1, .choice-intro h1, .review-topbar h1, .processing-card h1 {
  margin: 16px 0 14px;
  color: var(--rq-blue-900);
  font-size: clamp(31px, 4vw, 54px);
  line-height: 1.25;
  letter-spacing: -0.035em;
}

.landing-copy p, .auth-visual-card p, .choice-intro p, .processing-card p, .review-topbar p {
  color: var(--rq-muted);
  font-size: 17px;
  line-height: 1.9;
  margin: 0;
}

.landing-actions {
  margin-top: 28px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.upload-card, .auth-card, .choice-card, .processing-card, .review-panel, .review-progress-card {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(219, 231, 243, 0.95);
  border-radius: var(--rq-radius-lg);
  box-shadow: var(--rq-shadow);
}

.upload-card {
  padding: 30px;
}

.card-header-block h2, .choice-card h2, .auth-card h2, .panel-heading h2 {
  margin: 12px 0 8px;
  color: var(--rq-blue-900);
  font-weight: 800;
}

.card-header-block p, .choice-card p, .auth-muted {
  margin: 0 0 20px;
  color: var(--rq-muted);
  line-height: 1.8;
}

.upload-dropzone {
  align-items: center;
  background: #f8fbff;
  border: 2px dashed #b5cce6;
  border-radius: 22px;
  color: var(--rq-blue-800);
  cursor: pointer;
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
  min-height: 178px;
  padding: 24px;
  position: relative;
  text-align: center;
  transition: 0.2s ease;
}

.upload-dropzone:hover,
.upload-dropzone.is-drag-active,
.upload-dropzone.has-file {
  background: #eef7ff;
  border-color: var(--rq-blue-600);
  box-shadow: 0 0 0 5px rgba(29, 112, 184, 0.08);
}

.upload-file-input {
  height: 1px;
  opacity: 0;
  overflow: hidden;
  position: absolute;
  width: 1px;
}

.upload-dropzone-content {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin: 0;
  width: 100%;
}

.upload-icon {
  align-items: center;
  background: #ffffff;
  border: 1px solid var(--rq-line);
  border-radius: 50%;
  color: var(--rq-blue-700);
  display: inline-flex;
  font-size: 24px;
  font-weight: 800;
  height: 50px;
  justify-content: center;
  margin: 0 auto;
  width: 50px;
}

.upload-main-text { color: var(--rq-blue-900); font-size: 17px; font-weight: 800; }
.upload-sub-text, .status-line { color: var(--rq-muted); font-size: 14px; }
.status-line { text-align: center; margin: 16px 0 0; }

.selected-file-summary {
  background: var(--rq-blue-100);
  border: 1px solid #cfe4fa;
  border-radius: 16px;
  color: var(--rq-blue-800);
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 16px;
  padding: 12px 14px;
}

.selected-file-label { color: var(--rq-muted); font-size: 13px; }
.selected-file-name { direction: ltr; font-weight: 800; overflow-wrap: anywhere; text-align: left; }

.auth-page, .processing-page {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 46px 20px;
}

.auth-shell {
  width: min(1080px, 100%);
  display: grid;
  grid-template-columns: 1fr 430px;
  gap: 24px;
  align-items: stretch;
}

.auth-visual-card {
  padding: 42px;
  border-radius: var(--rq-radius-lg);
  color: #fff;
  background: linear-gradient(135deg, var(--rq-blue-900), var(--rq-blue-700));
  box-shadow: var(--rq-shadow);
}

.auth-visual-card h1, .auth-visual-card p { color: #fff; }
.auth-feature-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 26px; }
.auth-feature-grid span { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18); border-radius: 999px; padding: 8px 14px; }
.auth-card { padding: 30px; }
.form-field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; color: var(--rq-blue-900); font-weight: 800; }
.form-field input, .manual-correction-field input {
  border: 1px solid var(--rq-line);
  border-radius: 14px;
  min-height: 48px;
  padding: 10px 14px;
  outline: none;
  transition: 0.18s ease;
  font-size: 15px;
  background: #fbfdff;
}
.form-field input:focus, .manual-correction-field input:focus { border-color: var(--rq-blue-600); box-shadow: 0 0 0 4px rgba(29, 112, 184, 0.10); }
.inline-alert, .choice-error, .processing-error { border-radius: 14px; padding: 12px 14px; line-height: 1.7; margin-bottom: 16px; }
.inline-alert { background: #effaf3; color: #166534; border: 1px solid #bbf7d0; }
.auth-switch { text-align: center; color: var(--rq-muted); margin: 18px 0 0; }
.auth-switch a { color: var(--rq-blue-700); font-weight: 800; }

.choice-page { padding: 56px 20px; }
.choice-shell { width: min(1080px, 100%); margin: 0 auto; }
.choice-intro { max-width: 760px; margin-bottom: 24px; }
.choice-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.choice-card { padding: 28px; }
.choice-card--featured { border-color: rgba(29, 112, 184, 0.34); box-shadow: 0 24px 70px rgba(20, 93, 160, 0.16); }
.choice-card__icon { width: 48px; height: 48px; border-radius: 16px; display: inline-flex; align-items: center; justify-content: center; background: var(--rq-blue-100); color: var(--rq-blue-700); font-weight: 800; margin-bottom: 12px; }
.choice-card ul { color: var(--rq-muted); line-height: 2; padding-right: 22px; margin: 0 0 22px; }
.choice-error { background: #fff7ed; color: #9a3412; border: 1px solid #fed7aa; }

.processing-card { width: min(560px, 100%); text-align: center; padding: 42px; }
.loader { border: 6px solid #e8f1fb; border-top: 6px solid var(--rq-blue-700); border-radius: 50%; width: 66px; height: 66px; margin: 22px auto 0; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.review-page {
  padding: 30px 20px 54px;
  width: min(1440px, 100%);
  margin: 0 auto;
}

.review-topbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.review-topbar h1 { font-size: clamp(26px, 3vw, 40px); margin-bottom: 8px; }
.review-topbar p { max-width: 760px; }

.review-progress-card {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 1.3fr auto;
  align-items: center;
  gap: 18px;
  padding: 18px 20px;
  margin-bottom: 18px;
}

.review-progress-copy { display: flex; flex-direction: column; gap: 4px; color: var(--rq-muted); line-height: 1.6; }
.review-progress-copy strong { color: var(--rq-blue-900); }
.review-progress-track { height: 18px; border-radius: 999px; background: #e7eff8; overflow: hidden; }
.review-progress-fill { height: 100%; min-width: 42px; background: linear-gradient(135deg, var(--rq-blue-700), var(--rq-cyan)); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; transition: width .3s ease; }
.remaining-pill, .page-chip, .legend-dot { border: 1px solid var(--rq-line); background: #fff; border-radius: 999px; color: var(--rq-blue-800); font-size: 13px; font-weight: 800; padding: 8px 12px; white-space: nowrap; }

.review-workspace {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(380px, 1fr);
  gap: 18px;
  align-items: start;
}

.review-panel { padding: 18px; min-height: 640px; }
.panel-heading { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; margin-bottom: 14px; }
.panel-heading h2 { font-size: 20px; margin: 8px 0 0; }
.legend-dot { display: inline-flex; align-items: center; gap: 8px; }
.legend-dot i { display: inline-block; width: 10px; height: 10px; border-radius: 999px; background: var(--rq-gold-strong); }
.original-preview { position: relative; background: #f8fbff; border: 1px solid var(--rq-line); border-radius: 22px; overflow: auto; max-height: 760px; padding: 10px; }
.original-image { width: 100%; min-width: 320px; height: auto; border-radius: 16px; display: block; }
.original-word-marker { position: absolute; border: 2px solid var(--rq-blue-700); background: rgba(255, 232, 163, .55); box-shadow: 0 0 0 4px rgba(29, 112, 184, .12); border-radius: 6px; pointer-events: none; }

.extracted-text {
  min-height: 560px;
  max-height: 760px;
  overflow: auto;
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid var(--rq-line);
  border-radius: 22px;
  padding: 24px;
  color: #1e293b;
  font-size: 19px;
  line-height: 2.35;
}

.review-word {
  display: inline;
  margin: 0 1px;
  padding: 2px 4px;
  border-radius: 7px;
  cursor: pointer;
  transition: background .16s ease, box-shadow .16s ease, color .16s ease;
}

.review-word:hover { background: #eef6ff; }
.review-word--flagged {
  background: linear-gradient(180deg, rgba(255, 245, 196, .95), rgba(255, 232, 163, .95));
  border-bottom: 2px solid var(--rq-gold-strong);
  box-shadow: inset 0 -1px 0 rgba(180, 83, 9, .22);
  color: #422006;
  font-weight: 700;
}
.review-word--flagged:hover, .review-word--selected {
  background: #ffe08a;
  box-shadow: 0 0 0 3px rgba(244, 191, 58, .25);
}
.review-word--corrected {
  background: #dcfce7;
  color: #166534;
  border-bottom: 2px solid #22c55e;
}

.word-suggestions-menu {
  position: absolute;
  z-index: 1000;
  width: min(360px, calc(100vw - 32px));
  background: #fff;
  border: 1px solid #cfe0f2;
  border-radius: 18px;
  box-shadow: 0 24px 70px rgba(15, 23, 42, .18);
  padding: 14px;
  text-align: right;
}

.word-suggestions-menu::before {
  content: "";
  position: absolute;
  top: -8px;
  right: 24px;
  width: 14px;
  height: 14px;
  background: #fff;
  border-top: 1px solid #cfe0f2;
  border-right: 1px solid #cfe0f2;
  transform: rotate(-45deg);
}

.suggestions-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--rq-line); }
.suggestions-head span, .suggestions-label, .manual-correction-field span { display: block; color: var(--rq-muted); font-size: 12px; font-weight: 800; margin-bottom: 4px; }
.suggestions-head strong { color: var(--rq-blue-900); font-size: 20px; }
.suggestions-close { width: 30px; height: 30px; border: 0; border-radius: 50%; background: #eef6ff; color: var(--rq-blue-900); cursor: pointer; font-size: 20px; }
.suggestions-section { padding: 12px 0; display: flex; flex-direction: column; gap: 8px; }
.suggestion-option { border: 1px solid #e2edf8; background: #f8fbff; border-radius: 12px; color: var(--rq-blue-900); cursor: pointer; font-weight: 800; padding: 10px 12px; text-align: right; transition: .16s ease; }
.suggestion-option:hover { background: var(--rq-blue-100); border-color: #bad7f2; }
.suggestions-state { background: #fff8df; color: #7a4f00; border: 1px solid #f0d77a; border-radius: 12px; padding: 10px; line-height: 1.7; font-size: 13px; }
.manual-correction-field { display: flex; flex-direction: column; gap: 7px; margin-bottom: 12px; }
.suggestions-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.suggestions-actions .rq-button { min-height: 42px; padding: 10px 12px; font-size: 13px; }

.review-pagination { display: flex; align-items: center; justify-content: center; gap: 14px; margin-top: 24px; color: var(--rq-blue-900); font-weight: 800; }

@media (max-width: 980px) {
  .landing-shell, .auth-shell, .choice-grid, .review-workspace, .review-progress-card { grid-template-columns: 1fr; }
  .review-topbar { flex-direction: column; align-items: stretch; }
  .review-progress-card { align-items: stretch; }
  .review-panel { min-height: auto; }
}

@media (max-width: 640px) {
  .rq-navbar__inner { width: min(100% - 24px, 1180px); min-height: 62px; }
  .landing-page, .auth-page, .choice-page, .processing-page, .review-page { padding-left: 12px; padding-right: 12px; }
  .upload-card, .auth-card, .auth-visual-card, .choice-card, .processing-card, .review-panel, .review-progress-card { border-radius: 20px; padding: 20px; }
  .landing-actions, .review-pagination, .suggestions-actions { flex-direction: column; display: flex; }
  .extracted-text { font-size: 17px; line-height: 2.2; padding: 18px; }
}
''', encoding='utf-8')

print('UI redesign files updated without modifying backend files.')
