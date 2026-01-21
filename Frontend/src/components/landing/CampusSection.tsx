import React, { useState, useEffect } from "react";

/**
 * Campus Section - Ảnh/Video campus với overlay
 * - Hiển thị hình ảnh trường
 * - Overlay text welcome
 * - Auto carousel chuyển ảnh 2s với hiệu ứng trượt ngang
 */
const CampusSection: React.FC = () => {
  const campusImages = [
    "/images/photo/anh (1).jpeg",
    "/images/photo/anh (2).jpeg",
    "/images/photo/anh (3).jpeg",
    "/images/photo/anh (4).jpeg",
    "/images/photo/anh (5).jpeg",
  ];

  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prevIndex) => (prevIndex + 1) % campusImages.length);
    }, 8000); // Chuyển ảnh mỗi 8 giây

    return () => clearInterval(interval);
  }, [campusImages.length]);

  const goToPrevious = () => {
    setCurrentIndex((prevIndex) =>
      prevIndex === 0 ? campusImages.length - 1 : prevIndex - 1,
    );
  };

  const goToNext = () => {
    setCurrentIndex((prevIndex) => (prevIndex + 1) % campusImages.length);
  };

  return (
    <section className="py-20 lg:py-28 bg-white">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-8 lg:px-12">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Khám phá{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-orange-500 to-yellow-500">
              Trường Đại học An Giang
            </span>
          </h2>
          <p className="text-lg text-gray-600">
            Môi trường học tập hiện đại, năng động và thân thiện
          </p>
        </div>

        {/* Campus Image with Overlay */}
        <div className="relative rounded-3xl overflow-hidden shadow-2xl group">
          {/* Image Carousel */}
          <div className="aspect-[21/9] relative overflow-hidden bg-gray-900">
            <div
              className="flex transition-transform duration-1000 ease-in-out h-full"
              style={{ transform: `translateX(-${currentIndex * 100}%)` }}
            >
              {campusImages.map((image, index) => (
                <div key={index} className="min-w-full h-full flex-shrink-0">
                  <img
                    src={image}
                    alt={`Campus AGU ${index + 1}`}
                    className="w-full h-full object-cover object-center"
                    loading="lazy"
                    draggable="false"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Previous Button */}
          <button
            onClick={goToPrevious}
            className="absolute left-4 top-1/2 -translate-y-1/2 z-20 bg-white/20 hover:bg-white/40 backdrop-blur-sm text-white p-3 rounded-full transition-all duration-300 opacity-0 group-hover:opacity-100 hover:scale-110"
            aria-label="Previous image"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 19l-7-7 7-7"
              />
            </svg>
          </button>

          {/* Next Button */}
          <button
            onClick={goToNext}
            className="absolute right-4 top-1/2 -translate-y-1/2 z-20 bg-white/20 hover:bg-white/40 backdrop-blur-sm text-white p-3 rounded-full transition-all duration-300 opacity-0 group-hover:opacity-100 hover:scale-110"
            aria-label="Next image"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>

          {/* Overlay gradient */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent"></div>
          {/* Carousel indicators */}
          <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2 flex space-x-2 z-10">
            {campusImages.map((_, index) => (
              <button
                key={index}
                onClick={() => setCurrentIndex(index)}
                className={`w-2 h-2 rounded-full transition-all duration-300 ${
                  index === currentIndex
                    ? "bg-white w-8"
                    : "bg-white/50 hover:bg-white/75"
                }`}
                aria-label={`Go to image ${index + 1}`}
              />
            ))}
          </div>

          {/* Overlay content */}
          <div className="absolute bottom-0 left-0 right-0 p-8 sm:p-12">
            <h3 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white mb-3">
              Welcome to An Giang University
            </h3>
            <p className="text-white/80 text-lg max-w-2xl">
              Nơi ươm mầm tri thức, khơi nguồn sáng tạo và phát triển tài năng
            </p>
          </div>
        </div>

        {/* Info cards below campus image */}
        <div className="grid sm:grid-cols-3 gap-6 mt-8">
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-100 text-center">
            <div className="text-4xl font-bold text-orange-600 mb-2">1999</div>
            <div className="text-gray-600">Năm thành lập</div>
          </div>
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-100 text-center">
            <div className="text-4xl font-bold text-orange-600 mb-2">
              15,000+
            </div>
            <div className="text-gray-600">Sinh viên</div>
          </div>
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-100 text-center">
            <div className="text-4xl font-bold text-orange-600 mb-2">40+</div>
            <div className="text-gray-600">Ngành đào tạo</div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CampusSection;
