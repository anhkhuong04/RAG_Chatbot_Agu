import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";

/**
 * Header Component - Sticky Navigation
 * - Logo trường bên trái
 * - Menu chính giữa
 * - CTA button bên phải
 * - Shadow khi scroll
 */
const Header: React.FC = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled ? "bg-white shadow-md" : "bg-white/95 backdrop-blur-sm"
      }`}
    >
      <div className="max-w-[1400px] mx-auto px-6 sm:px-8 lg:px-12">
        <div className="flex items-center justify-between h-16 lg:h-20">
          {/* Logo */}
          <Link
            to="/"
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="flex items-center space-x-3"
          >
            <img
              src="/images/logo_vi.png"
              alt="Logo Trường Đại học An Giang"
              className="h-10 w-auto lg:h-12"
            />
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center space-x-2">
            <a
              href="https://www.facebook.com/tuyensinhdhag"
              className="px-4 py-1.5 font-medium text-gray-700 rounded-full transition-all duration-300 hover:bg-orange-400 hover:text-gray-900 hover:shadow-sm"
            >
              Tuyển sinh
            </a>
            <a
              href="#contact"
              className="px-4 py-1.5 font-medium text-gray-600 rounded-full transition-all duration-300 hover:bg-orange-400 hover:text-gray-900 hover:shadow-sm"
            >
              Liên hệ
            </a>
          </nav>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 text-gray-600 hover:text-orange-600"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          >
            {isMobileMenuOpen ? (
              <X className="w-6 h-6" />
            ) : (
              <Menu className="w-6 h-6" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
