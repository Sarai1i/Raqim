import React, { useEffect, useState } from "react";
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
