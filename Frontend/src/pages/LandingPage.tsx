import React from "react";
import {
  Header,
  Hero,
  CampusSection,
  Contact,
  Footer,
} from "../components/landing";

/**
 * Landing Page - Trang chủ giới thiệu Chatbot Tuyển Sinh
 * Route: "/"
 */
const LandingPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-white">
      {/* Sticky Header */}
      <Header />

      {/* Main Content */}
      <main>
        {/* Hero Section - Trọng tâm của trang */}
        <Hero />

        {/* Campus Section - Ảnh trường */}
        <CampusSection />

        {/* Contact Section - Thông tin liên hệ */}
        <Contact />
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
};

export default LandingPage;
