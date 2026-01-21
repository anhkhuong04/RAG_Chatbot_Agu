import React from "react";
import { MapPin, Phone, Mail, Globe, Facebook } from "lucide-react";

/**
 * Contact Section - Thông tin liên hệ với bản đồ
 * - Bản đồ Google Maps bên trái
 * - Thông tin liên hệ chi tiết bên phải
 */
const Contact: React.FC = () => {
  const contactInfo = [
    {
      icon: MapPin,
      label: "Địa chỉ",
      content: "18 Ung Văn Khiêm, Phường Long Xuyên, tỉnh An Giang",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
    },
    {
      icon: Phone,
      label: "Số điện thoại",
      content: "+84 296 6256565",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
    },
    {
      icon: Phone,
      label: "Hotline Tư vấn tuyển sinh",
      content: "0794.2222.45",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
    },
    {
      icon: Mail,
      label: "Email",
      content: "tuyensinh@agu.edu.vn",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
      isLink: true,
      href: "mailto:tuyensinh@agu.edu.vn",
    },
    {
      icon: Globe,
      label: "Website",
      content: "https://www.agu.edu.vn/vi/tuyen-sinh",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
      isLink: true,
      href: "https://www.agu.edu.vn/vi/tuyen-sinh",
    },
    {
      icon: Facebook,
      label: "Fanpage Tuyển sinh",
      content: "https://www.facebook.com/tuyensinhdhag",
      iconColor: "text-blue-500",
      bgColor: "bg-blue-50",
      isLink: true,
      href: "https://www.facebook.com/tuyensinhdhag",
    },
  ];

  return (
    <section className="py-20 lg:py-28 bg-white">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-8 lg:px-12">
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Thông tin liên hệ
          </h2>
        </div>

        {/* Contact Grid */}
        <div className="grid lg:grid-cols-2 gap-8 items-start">
          {/* Left Column - Google Maps */}
          <div className="order-2 lg:order-1">
            <div className="bg-white rounded-2xl shadow-lg overflow-hidden h-[500px]">
              <iframe
                src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d5094.861215212074!2d105.43233889999999!3d10.3716558!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x310a731e7546fd7b%3A0x953539cd7673d9e5!2zVHLGsOG7nW5nIMSQ4bqhaSBI4buNYyBBbiBHaWFuZyAtIMSQ4bqhaSBI4buNYyBRdeG7kWMgR2lhIFRow6BuaCBQaOG7kSBI4buTIENow60gTWluaA!5e1!3m2!1svi!2s!4v1768531268373!5m2!1svi!2s"
                width="100%"
                height="100%"
                style={{ border: 0 }}
                allowFullScreen
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                title="Bản đồ Trường Đại học"
              ></iframe>
            </div>
          </div>

          {/* Right Column - Contact Information */}
          <div className="order-1 lg:order-2">
            <div className="bg-white rounded-2xl p-8 shadow-lg border border-gray-100 h-[500px] overflow-y-auto">
              <div className="space-y-6">
                {contactInfo.map((item, index) => (
                  <div key={index} className="flex items-start space-x-4">
                    {/* Icon */}
                    <div className="bg-blue-500 p-3 rounded-full flex-shrink-0">
                      <item.icon className="w-6 h-6 text-white" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-gray-900 mb-1">
                        {item.label}
                      </h3>
                      {item.isLink ? (
                        <a
                          href={item.href}
                          className="text-blue-600 hover:text-blue-700 hover:underline break-words"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {item.content}
                        </a>
                      ) : (
                        <p className="text-gray-600 break-words">
                          {item.content}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Contact;
