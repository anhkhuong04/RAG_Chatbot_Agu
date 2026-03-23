import React from "react";

/**
 * Campus Section - Hiển thị video giới thiệu trường
 */
const CampusSection: React.FC = () => {
  return (
    <section className="py-20 lg:py-28 bg-white">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-8 lg:px-12">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Khám phá{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-500 to-yellow-500">
              Khoa Công nghệ thông tin - Trường Đại học An Giang
            </span>
          </h2>
          <p className="text-lg text-gray-600">
            Môi trường học tập hiện đại, năng động và thân thiện
          </p>
        </div>

        {/* Video Wrapper */}
        <div className="relative rounded-3xl overflow-hidden shadow-2xl bg-gray-900 group aspect-video">
          <iframe
            className="absolute top-0 left-0 w-full h-full"
            src="https://www.youtube.com/embed/eyp7tV6rA38?si=RS0yDDPG67MAfmJ2"
            title="YouTube video player"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            referrerPolicy="strict-origin-when-cross-origin"
            allowFullScreen
          ></iframe>
        </div>
      </div>
    </section>
  );
};

export default CampusSection;
