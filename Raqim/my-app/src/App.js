import React from "react";
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
