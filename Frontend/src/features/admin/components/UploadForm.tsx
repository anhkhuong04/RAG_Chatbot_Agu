import { useState, useRef, useEffect } from "react";
import { Upload, FileText, X, Loader2 } from "lucide-react";
import type { UploadFormData } from "../../../types/admin";
import { ACADEMIC_YEARS, CATEGORIES } from "../../../types/admin";

export const getDefaultFormData = (): UploadFormData => ({
  file: null,
  year: ACADEMIC_YEARS[0],
  category: "",
  description: "",
});

interface UploadFormProps {
  onSubmit: (data: UploadFormData) => Promise<boolean>;
  isUploading: boolean;
  defaultValues: UploadFormData;
}

const UPLOAD_STEPS = [
  "Đang tải file lên server...",
  "Đang phân tích tài liệu...",
  "Đang chia chunks & embedding...",
  "Đang lưu vào Knowledge Base...",
];

export const UploadForm = ({
  onSubmit,
  isUploading,
  defaultValues,
}: UploadFormProps) => {
  const [formData, setFormData] = useState<UploadFormData>(defaultValues);
  const [dragActive, setDragActive] = useState(false);
  const [uploadStep, setUploadStep] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Simulate upload progress steps
  useEffect(() => {
    if (!isUploading) {
      setUploadStep(0);
      return;
    }
    const interval = setInterval(() => {
      setUploadStep((prev) =>
        prev < UPLOAD_STEPS.length - 1 ? prev + 1 : prev,
      );
    }, 4000);
    return () => clearInterval(interval);
  }, [isUploading]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFormData((prev: UploadFormData) => ({ ...prev, file: e.target.files![0] }));
    }
  };

  const removeFile = () => {
    setFormData((prev: UploadFormData) => ({ ...prev, file: null }));
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.file) {
      alert("Vui lòng chọn file (PDF, TXT, DOCX, RTF, JPG, PNG)");
      return;
    }

    if (!formData.category) {
      alert("Vui lòng chọn danh mục");
      return;
    }

    const success = await onSubmit(formData);

    if (success) {
      setFormData(defaultValues);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const progressPercent = isUploading
    ? Math.min(((uploadStep + 1) / UPLOAD_STEPS.length) * 100, 95)
    : 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white rounded-xl shadow-sm border border-gray-100 p-6"
    >
      <h2 className="text-base font-semibold text-gray-800 mb-5 flex items-center gap-2">
        <Upload className="w-[18px] h-[18px] text-blue-600" />
        Upload Tài Liệu
      </h2>

      {/* File Drop Zone */}
      <div
        className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-colors mb-5
          ${dragActive ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-gray-300"}
          ${formData.file ? "bg-emerald-50/50 border-emerald-300" : ""}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.docx,.rtf,.jpg,.jpeg,.png"
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isUploading}
        />

        {formData.file ? (
          <div className="flex items-center justify-center gap-3">
            <FileText className="w-7 h-7 text-emerald-600" />
            <div className="text-left">
              <p className="font-medium text-gray-800 text-sm">
                {formData.file.name}
              </p>
              <p className="text-xs text-gray-500">
                {(formData.file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                removeFile();
              }}
              disabled={isUploading}
              className="ml-3 p-1 hover:bg-red-100 rounded-full transition-colors"
            >
              <X className="w-4 h-4 text-red-500" />
            </button>
          </div>
        ) : (
          <div>
            <Upload className="w-10 h-10 mx-auto text-gray-300 mb-2" />
            <p className="text-sm text-gray-600 font-medium">
              Kéo thả hoặc click để chọn
            </p>
            <p className="text-xs text-gray-400 mt-1">
              PDF, TXT, DOCX, RTF, JPG, PNG
            </p>
          </div>
        )}
      </div>

      {/* Form Fields */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1.5">
            Năm học <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.year}
            onChange={(e) =>
              setFormData((prev: UploadFormData) => ({ ...prev, year: Number(e.target.value) }))
            }
            disabled={isUploading}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
          >
            {ACADEMIC_YEARS.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1.5">
            Danh mục <span className="text-red-500">*</span>
          </label>
          <select
            value={formData.category}
            onChange={(e) =>
              setFormData((prev: UploadFormData) => ({ ...prev, category: e.target.value }))
            }
            disabled={isUploading}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            required
          >
            <option value="">-- Chọn --</option>
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Description */}
      <div className="mb-5">
        <label className="block text-xs font-medium text-gray-600 mb-1.5">
          Mô tả (tùy chọn)
        </label>
        <textarea
          value={formData.description}
          onChange={(e) =>
            setFormData((prev: UploadFormData) => ({ ...prev, description: e.target.value }))
          }
          disabled={isUploading}
          placeholder="Nhập mô tả ngắn về tài liệu..."
          rows={2}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors resize-none"
        />
      </div>

      {/* Upload Progress Indicator */}
      {isUploading && (
        <div className="mb-5 p-4 bg-blue-50 rounded-xl border border-blue-100">
          <div className="flex items-center gap-2 mb-3">
            <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
            <span className="text-sm font-medium text-blue-700">
              {UPLOAD_STEPS[uploadStep]}
            </span>
          </div>
          <div className="w-full bg-blue-100 rounded-full h-1.5">
            <div
              className="bg-blue-600 h-1.5 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="flex justify-between mt-1.5">
            <span className="text-[11px] text-blue-500">
              Bước {uploadStep + 1}/{UPLOAD_STEPS.length}
            </span>
            <span className="text-[11px] text-blue-500">
              {Math.round(progressPercent)}%
            </span>
          </div>
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={isUploading || !formData.file || !formData.category}
        className={`w-full py-2.5 px-4 rounded-lg text-sm font-medium text-white transition-all flex items-center justify-center gap-2
          ${isUploading || !formData.file || !formData.category
            ? "bg-gray-300 cursor-not-allowed"
            : "bg-blue-600 hover:bg-blue-700 active:scale-[0.98] shadow-sm"
          }`}
      >
        {isUploading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Đang xử lý...
          </>
        ) : (
          <>
            <Upload className="w-4 h-4" />
            Upload & Nạp Knowledge Base
          </>
        )}
      </button>
    </form>
  );
};
