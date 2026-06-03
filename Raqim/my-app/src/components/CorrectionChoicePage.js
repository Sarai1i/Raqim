import React, { useState } from "react";
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
