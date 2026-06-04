import React from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();

  let user = null;
  try {
    user = JSON.parse(localStorage.getItem("raqim_user"));
  } catch {
    user = null;
  }

  const handleLogout = () => {
    localStorage.removeItem("raqim_user");
    navigate("/login", { replace: true });
  };

  const onAuthPage = location.pathname === "/login" || location.pathname === "/signup";

  return (
    <nav className="rq-navbar" dir="rtl" aria-label="شريط رقيم الرئيسي">
      <div className="rq-navbar__inner">
        <Link className="rq-navbar__brand" to={user ? "/" : "/login"} aria-label="رقيم">
          <span className="rq-navbar__mark">ر</span>
          <span>رقيم</span>
        </Link>

        {user && !onAuthPage && (
          <div className="rq-navbar__user">
            <span className="rq-navbar__welcome">مرحبًا، {user.name || "مستخدم"}</span>
            <button type="button" className="rq-navbar__logout" onClick={handleLogout}>
              تسجيل الخروج
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;