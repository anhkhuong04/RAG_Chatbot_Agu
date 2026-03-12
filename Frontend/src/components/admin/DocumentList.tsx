import { useState, useMemo } from "react";
import {
  FileText,
  Trash2,
  RefreshCw,
  Calendar,
  Tag,
  Hash,
  Search,
} from "lucide-react";
import type { DocumentItem } from "../../types/admin";
import { STATUS_CONFIG, ACADEMIC_YEARS, CATEGORIES } from "../../types/admin";

interface DocumentListProps {
  documents: DocumentItem[];
  isLoading: boolean;
  onDelete: (docUuid: string) => Promise<boolean>;
  onRefresh: () => void;
}

export const DocumentList = ({
  documents,
  isLoading,
  onDelete,
  onRefresh,
}: DocumentListProps) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterYear, setFilterYear] = useState<string>("");
  const [filterCategory, setFilterCategory] = useState<string>("");

  // Filtered documents
  const filtered = useMemo(() => {
    return documents.filter((doc) => {
      const matchesSearch =
        !searchQuery ||
        doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesYear =
        !filterYear || String(doc.metadata.year) === filterYear;
      const matchesCategory =
        !filterCategory || doc.metadata.category === filterCategory;
      return matchesSearch && matchesYear && matchesCategory;
    });
  }, [documents, searchQuery, filterYear, filterCategory]);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("vi-VN", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleDelete = async (doc: DocumentItem) => {
    const confirmed = window.confirm(
      `Bạn có chắc muốn xóa tài liệu "${doc.filename}"?`,
    );

    if (confirmed) {
      await onDelete(doc.doc_uuid);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-800 flex items-center gap-2">
            <FileText className="w-[18px] h-[18px] text-blue-600" />
            Danh Sách Tài Liệu
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {filtered.length}/{documents.length} tài liệu
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      {/* Filters Bar */}
      <div className="px-6 py-3 border-b border-gray-50 bg-gray-50/50 flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Tìm kiếm tên file..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white transition-colors"
          />
        </div>

        {/* Year filter */}
        <select
          value={filterYear}
          onChange={(e) => setFilterYear(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
        >
          <option value="">Tất cả năm</option>
          {ACADEMIC_YEARS.map((y) => (
            <option key={y} value={String(y)}>
              {y}
            </option>
          ))}
        </select>

        {/* Category filter */}
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
        >
          <option value="">Tất cả danh mục</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      {/* Loading State */}
      {isLoading && documents.length === 0 && (
        <div className="text-center py-16">
          <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm text-gray-500">Đang tải danh sách...</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && documents.length === 0 && (
        <div className="text-center py-16">
          <FileText className="w-14 h-14 text-gray-200 mx-auto mb-3" />
          <h3 className="text-sm font-medium text-gray-500 mb-1">
            Chưa có tài liệu nào
          </h3>
          <p className="text-xs text-gray-400">
            Upload file để bắt đầu xây dựng Knowledge Base
          </p>
        </div>
      )}

      {/* No filter results */}
      {!isLoading && documents.length > 0 && filtered.length === 0 && (
        <div className="text-center py-12">
          <Search className="w-10 h-10 text-gray-200 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            Không tìm thấy kết quả phù hợp
          </p>
        </div>
      )}

      {/* Document Table */}
      {filtered.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-3 px-6 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Tên file
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Metadata
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Trạng thái
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Ngày tạo
                </th>
                <th className="text-right py-3 px-6 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Thao tác
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((doc) => {
                const statusConfig =
                  STATUS_CONFIG[doc.status] || STATUS_CONFIG.PENDING;

                return (
                  <tr
                    key={doc.doc_uuid}
                    className="hover:bg-gray-50/50 transition-colors"
                  >
                    {/* Filename */}
                    <td className="py-3.5 px-6">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 bg-red-50 rounded-lg flex items-center justify-center flex-shrink-0">
                          <FileText className="w-4 h-4 text-red-500" />
                        </div>
                        <div className="min-w-0">
                          <p
                            className="text-sm font-medium text-gray-800 truncate max-w-[220px]"
                            title={doc.filename}
                          >
                            {doc.filename}
                          </p>
                          <p className="text-[11px] text-gray-400 font-mono">
                            {doc.doc_uuid.substring(0, 8)}...
                          </p>
                        </div>
                      </div>
                    </td>

                    {/* Metadata Badges */}
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap gap-1.5">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
                          <Calendar className="w-3 h-3" />
                          {doc.metadata.year}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 text-xs font-medium rounded-full">
                          <Tag className="w-3 h-3" />
                          {doc.metadata.category}
                        </span>
                        {doc.chunk_count != null && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">
                            <Hash className="w-3 h-3" />
                            {doc.chunk_count} chunks
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Status */}
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${statusConfig.color}`}
                      >
                        <span>{statusConfig.icon}</span>
                        {statusConfig.label}
                      </span>
                      {doc.error && (
                        <p
                          className="text-[11px] text-red-500 mt-1 truncate max-w-[140px]"
                          title={doc.error}
                        >
                          {doc.error}
                        </p>
                      )}
                    </td>

                    {/* Created Date */}
                    <td className="py-3.5 px-4 text-xs text-gray-500">
                      {formatDate(doc.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-6 text-right">
                      <button
                        onClick={() => handleDelete(doc)}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="Xóa tài liệu"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
