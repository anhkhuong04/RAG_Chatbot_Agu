// ============================================
// Admin Dashboard Types
// ============================================

export interface DocumentMetadata {
  year: number;
  category: string;
  description?: string;
}

export interface DocumentItem {
  doc_uuid: string;
  filename: string;
  metadata: DocumentMetadata;
  status: "PENDING" | "INDEXED" | "FAILED";
  created_at: string;
  chunk_count?: number;
  error?: string;
}

export interface UploadResponse {
  doc_uuid: string;
  status: string;
}

export interface UploadFormData {
  file: File | null;
  year: number;
  category: string;
  description: string;
}

// ============================================
// Constants for Dropdowns
// ============================================

export const ACADEMIC_YEARS = [2025, 2026];

export const CATEGORIES = ["Tuyển sinh", "Học phí", "Điểm chuẩn", "Khác"];

// Status display mapping
export const STATUS_CONFIG = {
  PENDING: {
    label: "Đang xử lý",
    color: "bg-yellow-100 text-yellow-800",
    icon: "⏳",
  },
  INDEXED: {
    label: "Đã nạp",
    color: "bg-green-100 text-green-800",
    icon: "✅",
  },
  FAILED: {
    label: "Lỗi",
    color: "bg-red-100 text-red-800",
    icon: "❌",
  },
} as const;
