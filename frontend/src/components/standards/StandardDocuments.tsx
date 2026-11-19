import { apiErrorMessage } from "@/lib/apiError";
import { QueryError } from "@/components/QueryError";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ConfirmationDialog, type Confirmation } from "@/components/ConfirmationDialog";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  retagDocument,
  downloadDocumentBlob,
  formatFileSize,
  mimeTypeLabel,
  type Document as IDocument,
} from "@/api/documents";
import { useAuth } from "@/contexts/useAuth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, timeAgo } from "@/lib/utils";

const MIME_BADGE_COLORS: Record<string, string> = {
  PDF: "bg-danger-soft text-danger border-danger-line",
  DOCX: "bg-info-soft text-info border-info-line",
  XLSX: "bg-success-soft text-success border-success-line",
  DOC: "bg-info-soft text-info border-info-line",
  XLS: "bg-success-soft text-success border-success-line",
};

const ACCEPTED_TYPES =
  ".pdf,.doc,.docx,.xls,.xlsx,application/pdf,application/msword," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "application/vnd.ms-excel," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

interface UploadModalProps {
  standardId: string;
  onClose: () => void;
  onSuccess: () => void;
}

function UploadModal({ standardId, onClose, onSuccess }: UploadModalProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [changeNotes, setChangeNotes] = useState("");
  const [progress, setProgress] = useState<number>(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      uploadDocument(standardId, selectedFile!, changeNotes || undefined, setProgress),
    onSuccess: () => {
      onSuccess();
      onClose();
    },
    onError: (err: unknown) => {
      setUploadError(apiErrorMessage(err, "Upload failed. Please try again."));
      setProgress(0);
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setSelectedFile(f);
    setUploadError(null);
    setProgress(0);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0] ?? null;
    setSelectedFile(f);
    setUploadError(null);
    setProgress(0);
  };

  const isUploading = mutation.isPending;

  return (
    <Dialog open onOpenChange={open => { if (!open && !isUploading) onClose(); }}>
      <DialogContent aria-describedby={undefined} className="gap-0 p-0">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft border border-brand-line">
              <Upload className="h-4 w-4 text-brand" />
            </div>
            <div>
              <DialogTitle>Upload document</DialogTitle>
              <p className="text-xs text-muted-foreground">PDF, Word, or Excel</p>
            </div>
          </div>

        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Drop zone */}
          <div
            role="button"
            tabIndex={isUploading ? -1 : 0}
            aria-label="Choose document"
            onKeyDown={event => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                if (!isUploading) fileRef.current?.click();
              }
            }}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => !isUploading && fileRef.current?.click()}
            className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-colors
              ${selectedFile
                ? "border-brand-line bg-brand-soft"
                : "border-border bg-muted/60 hover:border-border-strong hover:bg-muted"
              }
              ${isUploading ? "pointer-events-none opacity-60" : ""}
            `}
          >
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED_TYPES}
              className="hidden"
              onChange={handleFileChange}
              disabled={isUploading}
            />
            {selectedFile ? (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-soft border border-brand-line">
                  <FileText className="h-6 w-6 text-brand" />
                </div>
                <p className="text-sm font-medium text-foreground text-center break-all">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatFileSize(selectedFile.size)}
                </p>
                <p className="text-xs text-brand mt-1">Click to change file</p>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-foreground/5 border border-border">
                  <Upload className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground text-center">
                  <span className="text-foreground font-medium">Click to browse</span>{" "}
                  or drag and drop
                </p>
                <p className="text-xs text-subtle-foreground">PDF, DOCX, XLSX</p>
              </>
            )}
          </div>

          {/* Change notes */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Change Notes <span className="normal-case font-normal">(optional)</span>
            </label>
            <textarea
              value={changeNotes}
              onChange={(e) => setChangeNotes(e.target.value)}
              disabled={isUploading}
              rows={2}
              placeholder="What changed in this version?"
              className="w-full rounded-lg border border-border-strong bg-input px-3 py-2 text-sm text-foreground placeholder:text-subtle-foreground resize-none focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-primary disabled:opacity-50 transition-colors"
            />
          </div>

          {/* Progress bar */}
          {isUploading && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Uploading…</span>
                <span>{progress}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-foreground/10 overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Error */}
          {uploadError && (
            <div className="rounded-lg border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
              {uploadError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-5 border-t border-border">
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={isUploading}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!selectedFile || isUploading}
            onClick={() => mutation.mutate()}
            className="gap-2"
          >
            {isUploading ? (
              <>
                <div className="h-3.5 w-3.5 rounded-full border-2 border-border border-t-white animate-spin" />
                Uploading…
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" />
                Upload
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Documents Tab ──────────────────────────────────────────────────────────────

const TAG_CATEGORY_KEYS = [
  "category_01_metadata",
  "category_02_primary_subject",
  "category_03_technical_methods",
  "category_04_nlp_ai_models",
  "category_05_application_domain",
  "category_06_system_architecture",
  "category_07_statistical_mathematical",
  "category_08_semantic_conceptual",
  "category_09_long_tail_phrases",
] as const;

function flattenTagCategories(rawResponse: Record<string, unknown> | null): string[] {
  if (!rawResponse) return [];
  const tags: string[] = [];
  for (const key of TAG_CATEGORY_KEYS) {
    const values = rawResponse[key];
    if (Array.isArray(values)) {
      for (const v of values) {
        if (typeof v === "string" && v) tags.push(v);
      }
    }
  }
  return tags;
}

interface DocumentsTabProps {
  standardId: string;
  canUpload: boolean;
  blockedReason: string | null;
}

export function StandardDocuments({ standardId, canUpload: stageAllowsUpload, blockedReason }: DocumentsTabProps) {
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const { isAdmin, isManager } = useAuth();
  const queryClient = useQueryClient();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", standardId],
    queryFn: () => listDocuments(standardId),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => deleteDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
      // can_purchase lives on the standard query — removing the last document
      // must re-disable the purchase button.
      queryClient.invalidateQueries({ queryKey: ["standard", standardId] });
      setDeletingId(null);
    },
  });

  const [retaggingId, setRetaggingId] = useState<string | null>(null);
  const retagMutation = useMutation({
    mutationFn: (docId: string) => retagDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
      setRetaggingId(null);
    },
    onError: () => {
      setRetaggingId(null);
    },
  });

  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const handleDownload = async (doc: IDocument) => {
    setDownloadingId(doc.id);
    try {
      await downloadDocumentBlob(doc.id, doc.filename);
    } finally {
      setDownloadingId(null);
    }
  };

  const canManageDocuments = isManager;

  if (isError && !data) return <QueryError subject="documents" onRetry={refetch} />;

  if (isLoading) {
    return (
      <div className="space-y-3 pt-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  const docs = data?.items ?? [];

  return (
    <div className="pt-4 space-y-4">

      <ConfirmationDialog request={confirmation} onClose={() => setConfirmation(null)} />
      {/* Upload button (manager+) */}
      {canManageDocuments && (
        <div className="flex flex-col items-end gap-1">
          <Button
            size="sm"
            onClick={() => setShowUploadModal(true)}
            disabled={!stageAllowsUpload}
            title={!stageAllowsUpload ? (blockedReason ?? undefined) : undefined}
            className="gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload document
          </Button>
          {!stageAllowsUpload && blockedReason && (
            <p className="text-[11px] text-muted-foreground max-w-xs text-right leading-snug">
              {blockedReason}
            </p>
          )}
        </div>
      )}

      {/* Document list */}
      {docs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-foreground/5 border border-border">
            <FileText className="h-7 w-7 text-subtle-foreground" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">No documents uploaded yet</p>
          {canManageDocuments && stageAllowsUpload && (
            <p className="text-xs text-subtle-foreground">
              Click{" "}
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-brand underline underline-offset-2"
              >
                Upload document
              </button>{" "}
              to attach a PDF, DOCX, or XLSX.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2 max-h-[65vh] overflow-y-auto pr-1">
          {docs.map((doc) => {
            const typeLabel = mimeTypeLabel(doc.mime_type);
            const badgeClass =
              MIME_BADGE_COLORS[typeLabel] ?? "bg-foreground/10 text-muted-foreground border-border";
            const isCurrent = doc.is_current;

            return (
              <div
                key={doc.id}
                className={`flex items-center gap-4 rounded-xl border p-4 transition-colors
                  ${isCurrent
                    ? "border-border bg-muted hover:bg-muted"
                    : "border-border/50 bg-muted/60 opacity-60 hover:opacity-80"
                  }`}
              >
                {/* File type icon */}
                <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg bg-muted border border-border">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-0.5">
                    <p className="text-sm font-medium text-foreground truncate">
                      {doc.filename}
                    </p>
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${badgeClass}`}
                    >
                      {typeLabel}
                    </span>
                    <span className="text-[10px] font-medium text-muted-foreground border border-border bg-foreground/5 rounded-full px-2 py-0.5">
                      v{doc.version_number}
                    </span>
                    {isCurrent && (
                      <span className="text-[10px] font-medium text-success border border-success-line bg-success-soft rounded-full px-2 py-0.5">
                        Current
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                    <span>{formatFileSize(doc.file_size_bytes)}</span>
                    <span className="text-subtle-foreground">·</span>
                    <span title={formatDateTime(doc.uploaded_at)}>{timeAgo(doc.uploaded_at)}</span>
                    {doc.change_notes && (
                      <>
                        <span className="text-subtle-foreground">·</span>
                        <span className="italic truncate max-w-[200px]" title={doc.change_notes}>
                          {doc.change_notes}
                        </span>
                      </>
                    )}
                  </div>
                  {doc.tags && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {doc.tags.status === "pending" && (
                        <span className="text-[10px] text-muted-foreground italic">Tagging pending…</span>
                      )}
                      {doc.tags.status === "failed" && (
                        <>
                          <span className="text-[10px] text-danger">Tagging failed</span>
                          {isManager && (
                            <button
                              onClick={() => {
                                setRetaggingId(doc.id);
                                retagMutation.mutate(doc.id);
                              }}
                              disabled={retagMutation.isPending && retaggingId === doc.id}
                              className="inline-flex items-center gap-1 text-[10px] text-brand hover:text-brand underline underline-offset-2"
                            >
                              {retagMutation.isPending && retaggingId === doc.id ? (
                                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-2.5 w-2.5" />
                              )}
                              Retry tagging
                            </button>
                          )}
                        </>
                      )}
                      {doc.tags.status === "ok" && (
                        <>
                          {doc.tags.department && (
                            <Badge variant="secondary" className="text-[9px] py-0 px-1.5">
                              {doc.tags.department}
                            </Badge>
                          )}
                          {flattenTagCategories(doc.tags.raw_response).map((tag, i) => (
                            <Badge key={i} variant="secondary" className="text-[9px] py-0 px-1.5">
                              {tag}
                            </Badge>
                          ))}
                          {doc.tags.summary && (
                            <p className="text-[10px] text-subtle-foreground italic truncate max-w-full basis-full">
                              {doc.tags.summary}
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 flex items-center gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDownload(doc)}
                    disabled={downloadingId === doc.id}
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-success hover:bg-success-soft"
                    title="Download"
                  >
                    {downloadingId === doc.id ? (
                      <div className="h-3.5 w-3.5 rounded-full border-2 border-border-strong border-t-teal-400 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </Button>

                  {isAdmin && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setConfirmation({
                          action: "Delete document version",
                          description: `Delete version ${doc.version_number} of "${doc.filename}"?`,
                          onConfirm: () => {
                            setDeletingId(doc.id);
                            deleteMutation.mutate(doc.id);
                          },
                        });
                      }}
                      disabled={deleteMutation.isPending && deletingId === doc.id}
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-danger hover:bg-danger-soft"
                      title="Delete document version"
                    >
                      {deleteMutation.isPending && deletingId === doc.id ? (
                        <div className="h-3.5 w-3.5 rounded-full border-2 border-border-strong border-t-red-400 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}

          {/* Version count footer */}
          {docs.length > 1 && (
            <p className="text-xs text-subtle-foreground text-center pt-1">
              {docs.length} version{docs.length !== 1 ? "s" : ""} total
              {docs.filter((d) => !d.is_current).length > 0 &&
                ` · ${docs.filter((d) => !d.is_current).length} archived`}
            </p>
          )}
        </div>
      )}

      {/* Upload modal */}
      {showUploadModal && (
        <UploadModal
          standardId={standardId}
          onClose={() => setShowUploadModal(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
            // can_purchase lives on the standard query; without this the
            // purchase button stays disabled until a manual refresh.
            queryClient.invalidateQueries({ queryKey: ["standard", standardId] });
          }}
        />
      )}
    </div>
  );
}
