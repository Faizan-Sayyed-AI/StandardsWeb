import api from "@/lib/axios";
import type { Page } from "@/api/standards";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Document {
  id: string;
  standard_id: string;
  version_number: number;
  filename: string;
  file_size_bytes: number;
  sha256_checksum: string;
  mime_type: string;
  change_notes: string | null;
  uploaded_by: string;
  uploaded_at: string;
  is_current: boolean;
}

export interface DocumentDownloadResponse {
  document_id: string;
  filename: string;
  download_url: string;
  expires_in_seconds: number | null;
}

export interface UploadProgressCallback {
  (percentCompleted: number): void;
}

// ── API functions ─────────────────────────────────────────────────────────────

/** List all document versions for a standard (newest first). */
export async function listDocuments(
  standardId: string,
  page = 1,
  pageSize = 50
): Promise<Page<Document>> {
  const { data } = await api.get<Page<Document>>(
    `/api/v1/standards/${standardId}/documents`,
    { params: { page, page_size: pageSize } }
  );
  return data;
}

/**
 * Upload a new document version.
 * Uses multipart/form-data with Axios onUploadProgress for progress tracking.
 *
 * @param standardId  UUID of the standard to attach the document to
 * @param file        The File object from the file picker
 * @param changeNotes Optional description of what changed in this version
 * @param onProgress  Callback fired with percent (0–100) as upload progresses
 */
export async function uploadDocument(
  standardId: string,
  file: File,
  changeNotes?: string,
  onProgress?: UploadProgressCallback
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  if (changeNotes) {
    formData.append("change_notes", changeNotes);
  }

  const { data } = await api.post<Document>(
    `/api/v1/standards/${standardId}/documents`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percent);
        }
      },
    }
  );
  return data;
}

/**
 * Authenticated document download.
 *
 * Uses the Axios instance (carries Bearer token) to request the download
 * endpoint and then triggers a browser save-file dialog via a Blob URL.
 *
 * - Local storage: backend returns the file as a binary stream.
 * - S3 storage: backend returns a 307 redirect which Axios follows,
 *   downloading the file from the pre-signed S3 URL automatically.
 */
export async function downloadDocumentBlob(
  documentId: string,
  filename: string
): Promise<void> {
  const { data } = await api.get<Blob>(
    `/api/v1/documents/${documentId}/download`,
    { responseType: "blob" }
  );
  const blobUrl = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Free the object URL shortly after to avoid memory leak
  setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
}

/** Soft-delete a document version (admin only). */
export async function deleteDocument(documentId: string): Promise<void> {
  await api.delete(`/api/v1/documents/${documentId}`);
}

// ── Helpers ────────────────────────────────────────────────────────────────────

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function mimeTypeLabel(mimeType: string): string {
  const map: Record<string, string> = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/msword": "DOC",
    "application/vnd.ms-excel": "XLS",
  };
  return map[mimeType] ?? mimeType.split("/")[1]?.toUpperCase() ?? "FILE";
}
