import React from "react";
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
