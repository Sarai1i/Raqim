import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import API_BASE_URL from "../config";

const MailIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" />
  </svg>
);

const LockIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </svg>
);

const EyeIcon = ({ off }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {off ? (
      <>
        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a13.16 13.16 0 0 1-1.67 2.68" />
        <path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 8 10 8a9.12 9.12 0 0 0 5.39-1.61" />
        <line x1="2" y1="2" x2="22" y2="22" />
      </>
    ) : (
      <>
        <path d="M2 12s3-8 10-8 10 8 10 8-3 8-10 8-10-8-10-8Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    )}
  </svg>
);

const LoginPage = ({ mode = "login" }) => {
  const navigate = useNavigate();
  const [tab, setTab] = useState(mode === "signup" ? "signup" : "login");
  const isSignup = tab === "signup";

  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [message, setMessage] = useState("");
  const [isError, setIsError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const switchTab = (nextTab) => {
    setTab(nextTab);
    setMessage("");
    setIsError(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setMessage("");
    setIsError(false);

    if (!form.email || !form.password || (isSignup && !form.name)) {
      setIsError(true);
      setMessage("فضلاً أكمل البيانات المطلوبة للمتابعة.");
      return;
    }

    setLoading(true);
    try {
      const endpoint = isSignup ? "/register" : "/login";
      const payload = isSignup
        ? { name: form.name, email: form.email, password: form.password }
        : { email: form.email, password: form.password };

      const response = await axios.post(`${API_BASE_URL}${endpoint}`, payload);
      localStorage.setItem("raqim_user", JSON.stringify(response.data.user));

      // انتقال مباشر بدون رسالة نجاح
      setIsError(false);
      navigate("/");
    } catch (error) {
      setIsError(true);
      const serverMessage = error.response?.data?.error;
      setMessage(serverMessage || "تعذّر الاتصال بالخادم. تأكد من تشغيل الـ Backend.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="auth-page" dir="rtl">
      <section className="auth-shell">
        {/* اللوحة الكحلية بالزخرفة */}
        <aside className="auth-hero">
          <div className="auth-hero-pattern" aria-hidden="true" />
          <div className="auth-hero-content">
            <div className="auth-logo">رقَيم</div>
            <div className="auth-hero-divider">
              <span className="line" />
              <span className="star">✦</span>
              <span className="line" />
            </div>
            <p className="auth-hero-tagline">
              منظّم نصوصك،<br />ارتقِ بجودة كتابتك.
            </p>
          </div>
          <div className="auth-hero-mesh" aria-hidden="true" />
        </aside>

        {/* بطاقة النموذج */}
        <div className="auth-panel">
          <form className="auth-form" onSubmit={handleSubmit}>
            <h1 className="auth-title">مرحبًا بك في رقيم</h1>
            <p className="auth-subtitle">سجّل الدخول لمراجعة النصوص وتصحيحها بسهولة</p>

            <div className="auth-tabs" role="tablist">
              <button type="button" className={`auth-tab ${!isSignup ? "is-active" : ""}`} onClick={() => switchTab("login")}>
                تسجيل الدخول
              </button>
              <button type="button" className={`auth-tab ${isSignup ? "is-active" : ""}`} onClick={() => switchTab("signup")}>
                حساب جديد
              </button>
            </div>

            {isSignup && (
              <label className="auth-field">
                <span className="auth-field-label">الاسم</span>
                <div className="auth-input-wrap">
                  <input name="name" value={form.name} onChange={handleChange} placeholder="اكتب اسمك" />
                </div>
              </label>
            )}

            <label className="auth-field">
              <span className="auth-field-label">البريد الإلكتروني</span>
              <div className="auth-input-wrap">
                <span className="auth-input-icon auth-input-icon--lead"><MailIcon /></span>
                <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="name@example.com" dir="ltr" />
              </div>
            </label>

            <label className="auth-field">
              <span className="auth-field-label">كلمة المرور</span>
              <div className="auth-input-wrap">
                <button type="button" className="auth-input-icon auth-input-icon--lead auth-eye" onClick={() => setShowPassword((v) => !v)} tabIndex={-1} aria-label="إظهار كلمة المرور">
                  <EyeIcon off={showPassword} />
                </button>
                <input name="password" type={showPassword ? "text" : "password"} value={form.password} onChange={handleChange} placeholder="••••••••" dir="ltr" />
                <span className="auth-input-icon auth-input-icon--trail"><LockIcon /></span>
              </div>
            </label>

            {message && (
              <div className={`auth-alert ${isError ? "auth-alert--error" : "auth-alert--ok"}`}>
                {message}
              </div>
            )}

            <button className="auth-submit" type="submit" disabled={loading}>
              {loading ? "جارٍ المعالجة..." : "متابعة"}
            </button>

            <p className="auth-switch">
              {isSignup ? "لديك حساب؟ " : "ليس لديك حساب؟ "}
              <button type="button" className="auth-switch-link" onClick={() => switchTab(isSignup ? "login" : "signup")}>
                {isSignup ? "تسجيل الدخول" : "أنشئ حسابًا"}
              </button>
            </p>
          </form>
        </div>
      </section>
    </main>
  );
};

export default LoginPage;