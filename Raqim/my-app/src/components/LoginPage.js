import React, { useState } from "react";
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
