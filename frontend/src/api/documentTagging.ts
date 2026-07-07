import api from "@/lib/axios";

export interface DocumentTaggingConfig {
  DOCUMENT_TAGGING_URL: string;
  DOCUMENT_TAGGING_API_KEY: string;
}

export async function getDocumentTaggingConfig(): Promise<DocumentTaggingConfig> {
  const { data } = await api.get<DocumentTaggingConfig>("/api/v1/admin/document-tagging-config");
  return data;
}

export async function updateDocumentTaggingConfig(
  payload: DocumentTaggingConfig
): Promise<DocumentTaggingConfig> {
  const { data } = await api.patch<DocumentTaggingConfig>(
    "/api/v1/admin/document-tagging-config",
    payload
  );
  return data;
}
