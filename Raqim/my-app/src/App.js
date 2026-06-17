import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import FileUpload from "./components/FileUpload";
import Navbar from "./components/Navbar";
import LoadingPage from "./components/LoadingPage";
import CorrectionChoicePage from "./components/CorrectionChoicePage";
import ReviewPage from "./components/ReviewPage";
import LoginPage from "./components/LoginPage";
import "./App.css";

// التحقق من تسجيل الدخول
const isLoggedIn = () => {
  try {
    return Boolean(JSON.parse(localStorage.getItem("raqim_user")));
  } catch {
    return false;
  }
};

// حارس المسارات: يمنع الوصول إلا بعد تسجيل الدخول
const RequireAuth = ({ children }) => {
  const location = useLocation();
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return children;
};

function App() {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/login" element={<LoginPage mode="login" />} />
        <Route path="/signup" element={<LoginPage mode="signup" />} />
        <Route path="/" element={<RequireAuth><FileUpload /></RequireAuth>} />
        <Route path="/loading" element={<RequireAuth><LoadingPage /></RequireAuth>} />
        <Route path="/correction-choice" element={<RequireAuth><CorrectionChoicePage /></RequireAuth>} />
        <Route path="/review" element={<RequireAuth><ReviewPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;