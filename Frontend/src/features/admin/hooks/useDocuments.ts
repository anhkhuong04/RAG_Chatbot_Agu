import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  uploadDocument,
  getDocuments,
  deleteDocument,
  getMetadataOptions,
} from "../api/adminAPI";
import {
  ACADEMIC_YEARS,
  CATEGORIES,
  type UploadFormData,
} from "../../../types/admin";

export const useDocuments = () => {
  const queryClient = useQueryClient();

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: getDocuments,
  });

  const uploadMutation = useMutation({
    mutationFn: (formData: UploadFormData) => {
      if (!formData.file) throw new Error("Vui lòng chọn file PDF");
      return uploadDocument(
        formData.file,
        formData.year,
        formData.category,
        formData.description || undefined,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (docUuid: string) => deleteDocument(docUuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const metadataOptionsQuery = useQuery({
    queryKey: ["admin-metadata-options"],
    queryFn: getMetadataOptions,
    staleTime: 5 * 60 * 1000,
    retry: 1,
    initialData: {
      years: ACADEMIC_YEARS,
      categories: CATEGORIES,
    },
  });

  return {
    documents: documentsQuery.data || [],
    isLoading: documentsQuery.isPending || documentsQuery.isFetching,
    error: documentsQuery.error
      ? "Không thể tải danh sách tài liệu. Vui lòng thử lại."
      : null,

    isUploading: uploadMutation.isPending,
    uploadError: uploadMutation.error
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ? (uploadMutation.error as any).response?.data?.detail ||
        "Lỗi khi upload. Vui lòng thử lại."
      : null,
    uploadSuccess: uploadMutation.isSuccess ? "Upload thành công!" : null,

    uploadDocument: uploadMutation.mutateAsync,
    deleteDocument: deleteMutation.mutateAsync,

    metadataOptions: metadataOptionsQuery.data,
    isLoadingMetadataOptions: metadataOptionsQuery.isPending,
    metadataOptionsError: metadataOptionsQuery.error
      ? "Không thể tải metadata options. Đang dùng dữ liệu mặc định."
      : null,

    refetchDocuments: documentsQuery.refetch,
    resetUploadState: uploadMutation.reset,
  };
};
