import React from "react";
import { useNavigate } from "react-router-dom";
import { MessageCircle, ArrowRight } from "lucide-react";

/**
 * Hero Section - Trọng tâm của trang
 * - Grid 2 cột: Nội dung bên trái, Illustration bên phải
 * - Headline với gradient text
 * - CTA buttons điều hướng tới /chat
 */
const Hero: React.FC = () => {
  const navigate = useNavigate();

  const handleMainCTA = () => {
    navigate("/chat");
  };

  return (
    <section className="min-h-[85vh] lg:min-h-[90vh] flex items-center pt-20 lg:pt-24 pb-12 bg-white">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-8 lg:px-12 w-full">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left Column - Content */}
          <div className="order-2 lg:order-1 text-center lg:text-left">
            {/* Badge */}
            <div className="inline-flex items-center px-4 py-2 bg-orange-50 rounded-full mb-6 animate-fade-in">
              <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
              <span className="text-sm font-medium text-orange-700">
                Trợ lý AI sẵn sàng hỗ trợ 24/7
              </span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 leading-tight mb-6 animate-slide-up">
              Trợ lý{" "}
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-500 to-yellow-500">
                tuyển sinh
              </span>
            </h1>

            {/* Subtitle */}
            <p className="text-lg sm:text-xl text-gray-600 mb-8 max-w-xl mx-auto lg:mx-0 animate-slide-up animation-delay-200">
              Khoa Công nghệ thông tin - Trường Đại học An Giang. Giải đáp mọi
              thắc mắc về ngành học, điểm chuẩn, học phí và quy chế tuyển sinh.
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start animate-slide-up animation-delay-400">
              {/* Primary CTA */}
              <button
                onClick={handleMainCTA}
                className="group flex items-center justify-center space-x-4 px-20 py-9
                          bg-gradient-to-r from-orange-500 to-yellow-500
                          text-white text-2xl font-bold
                          rounded-full
                          hover:from-orange-600 hover:to-yellow-600
                          transition-all duration-300
                          shadow-2xl
                          transform hover:-translate-y-2 hover:scale-[1.02]
                          "
              >
                <MessageCircle className="w-5 h-5" />
                <span>Trò chuyện với trợ lý</span>
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </button>
            </div>
          </div>

          {/* Right Column - Illustration */}
          <div className="order-1 lg:order-2 flex justify-center lg:justify-end">
            <div className="relative w-full max-w-md lg:max-w-lg animate-float">
              {/* Background decoration */}
              <div className="absolute inset-0 bg-gradient-to-r from-orange-400/20 to-yellow-400/20 rounded-full blur-3xl"></div>

              {/* Main illustration - Placeholder SVG */}
              <div className="relative">
                <svg
                  viewBox="0 0 500 500"
                  className="w-full h-auto"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Background circle */}
                  <circle
                    cx="250"
                    cy="250"
                    r="200"
                    fill="url(#gradient1)"
                    fillOpacity="0.1"
                  />

                  {/* Chat bubbles */}
                  <rect
                    x="120"
                    y="150"
                    width="180"
                    height="60"
                    rx="20"
                    fill="#2563eb"
                  />
                  <rect
                    x="200"
                    y="230"
                    width="160"
                    height="50"
                    rx="20"
                    fill="#8b5cf6"
                  />
                  <rect
                    x="140"
                    y="300"
                    width="200"
                    height="55"
                    rx="20"
                    fill="#3b82f6"
                  />

                  {/* Robot/AI icon */}
                  <circle cx="320" cy="120" r="50" fill="url(#gradient2)" />
                  <circle cx="305" cy="110" r="8" fill="white" />
                  <circle cx="335" cy="110" r="8" fill="white" />
                  <path
                    d="M305 130 Q320 145 335 130"
                    stroke="white"
                    strokeWidth="4"
                    fill="none"
                    strokeLinecap="round"
                  />

                  {/* Antenna */}
                  <line
                    x1="320"
                    y1="70"
                    x2="320"
                    y2="55"
                    stroke="#8b5cf6"
                    strokeWidth="3"
                  />
                  <circle cx="320" cy="50" r="8" fill="#8b5cf6" />

                  {/* Decorative dots */}
                  <circle
                    cx="100"
                    cy="200"
                    r="6"
                    fill="#3b82f6"
                    fillOpacity="0.5"
                  />
                  <circle
                    cx="400"
                    cy="300"
                    r="8"
                    fill="#8b5cf6"
                    fillOpacity="0.5"
                  />
                  <circle
                    cx="380"
                    cy="180"
                    r="5"
                    fill="#2563eb"
                    fillOpacity="0.5"
                  />

                  {/* Gradients */}
                  <defs>
                    <linearGradient
                      id="gradient1"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="100%"
                    >
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                    <linearGradient
                      id="gradient2"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="100%"
                    >
                      <stop offset="0%" stopColor="#2563eb" />
                      <stop offset="100%" stopColor="#7c3aed" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
