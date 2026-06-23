import { useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BookOpen, Calendar, Copy, Download, ExternalLink, FileText,
  GitBranch, Loader2, Package, ScrollText, Tag, Trash2, Upload, X,
} from "lucide-react";
import { getStandard, getStandardHistory, purchaseStandard, type Standard } from "@/api/standards";
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  downloadDocumentBlob,
  formatFileSize,
  mimeTypeLabel,
  type Document as IDocument,
} from "@/api/documents";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime, timeAgo } from "@/lib/utils";

// ── JSON snapshot block with copy-to-clipboard ────────────────────────────────

function JsonSnapshot({ value }: { value: Record<string, unknown> }) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(value, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="mt-2 max-w-full overflow-hidden">
      <div className="relative rounded-lg border border-slate-700/50 bg-slate-900/60 p-3">
        <button
          onClick={handleCopy}
          title="Copy JSON"
          className="absolute right-2 top-2 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-slate-400 hover:bg-white/8 hover:text-slate-200 transition-colors"
        >
          {copied ? (
            <span className="text-teal-400">✓ Copied</span>
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
        <div className="max-h-48 overflow-y-auto overflow-x-auto pr-10">
          <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all">
            {text}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ── History tab helpers ────────────────────────────────────────────────────────

const EVENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  new: Package,
  updated: GitBranch,
  amended: ScrollText,
  replaced: ArrowLeft,
  withdrawn: Tag,
};

const EVENT_COLORS: Record<string, string> = {
  new: "border-teal-500/30 bg-teal-500/10 text-teal-400",
  updated: "border-blue-500/30 bg-blue-500/10 text-blue-400",
  amended: "border-yellow-500/30 bg-yellow-500/10 text-yellow-400",
  replaced: "border-orange-500/30 bg-orange-500/10 text-orange-400",
  withdrawn: "border-red-500/30 bg-red-500/10 text-red-400",
};

const MIME_BADGE_COLORS: Record<string, string> = {
  PDF:  "bg-red-500/15 text-red-400 border-red-500/25",
  DOCX: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  XLSX: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  DOC:  "bg-blue-500/15 text-blue-400 border-blue-500/25",
  XLS:  "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
};

const ACCEPTED_TYPES =
  ".pdf,.doc,.docx,.xls,.xlsx,application/pdf,application/msword," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "application/vnd.ms-excel," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// ── Upload Modal ───────────────────────────────────────────────────────────────

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
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setUploadError(detail ?? "Upload failed. Please try again.");
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
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget && !isUploading) onClose(); }}
    >
      <div className="relative w-full max-w-lg mx-4 rounded-2xl border border-white/10 bg-[#0f1117] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/8">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600/20 border border-indigo-500/20">
              <Upload className="h-4 w-4 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">Upload Document</h2>
              <p className="text-xs text-muted-foreground">PDF, DOCX, or XLSX · max 50 MB</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isUploading}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/8 hover:text-foreground transition-colors disabled:opacity-40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => !isUploading && fileRef.current?.click()}
            className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 cursor-pointer transition-colors
              ${selectedFile
                ? "border-indigo-500/50 bg-indigo-500/5"
                : "border-white/15 bg-white/3 hover:border-white/25 hover:bg-white/5"
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
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600/20 border border-indigo-500/20">
                  <FileText className="h-6 w-6 text-indigo-400" />
                </div>
                <p className="text-sm font-medium text-foreground text-center break-all">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatFileSize(selectedFile.size)}
                </p>
                <p className="text-xs text-indigo-400 mt-1">Click to change file</p>
              </>
            ) : (
              <>
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/5 border border-white/10">
                  <Upload className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground text-center">
                  <span className="text-foreground font-medium">Click to browse</span>{" "}
                  or drag and drop
                </p>
                <p className="text-xs text-muted-foreground/60">PDF, DOCX, XLSX</p>
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
              className="w-full rounded-lg border border-white/10 bg-white/4 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500/50 disabled:opacity-50 transition-colors"
            />
          </div>

          {/* Progress bar */}
          {isUploading && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Uploading…</span>
                <span>{progress}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-teal-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Error */}
          {uploadError && (
            <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {uploadError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-5 border-t border-white/8">
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
            className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {isUploading ? (
              <>
                <div className="h-3.5 w-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
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
      </div>
    </div>
  );
}

// ── Documents Tab ──────────────────────────────────────────────────────────────

interface DocumentsTabProps {
  standardId: string;
}

function DocumentsTab({ standardId }: DocumentsTabProps) {
  const { isAdmin, isManager } = useAuth();
  const queryClient = useQueryClient();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["documents", standardId],
    queryFn: () => listDocuments(standardId),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => deleteDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", standardId] });
      setDeletingId(null);
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

  const canUpload = isAdmin || isManager;

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
      {/* Upload button (manager+) */}
      {canUpload && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => setShowUploadModal(true)}
            className="gap-2 bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/20 transition-all"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload Document
          </Button>
        </div>
      )}

      {/* Document list */}
      {docs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5 border border-white/10">
            <FileText className="h-7 w-7 text-muted-foreground/40" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">No documents uploaded yet</p>
          {canUpload && (
            <p className="text-xs text-muted-foreground/60">
              Click{" "}
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-indigo-400 underline underline-offset-2"
              >
                Upload Document
              </button>{" "}
              to attach a PDF, DOCX, or XLSX.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {docs.map((doc) => {
            const typeLabel = mimeTypeLabel(doc.mime_type);
            const badgeClass =
              MIME_BADGE_COLORS[typeLabel] ?? "bg-white/10 text-muted-foreground border-white/15";
            const isCurrent = doc.is_current;

            return (
              <div
                key={doc.id}
                className={`flex items-center gap-4 rounded-xl border p-4 transition-colors
                  ${isCurrent
                    ? "border-white/10 bg-white/4 hover:bg-white/6"
                    : "border-white/5 bg-white/2 opacity-60 hover:opacity-80"
                  }`}
              >
                {/* File type icon */}
                <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg bg-white/6 border border-white/8">
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
                    <span className="text-[10px] font-medium text-white/40 border border-white/10 bg-white/5 rounded-full px-2 py-0.5">
                      v{doc.version_number}
                    </span>
                    {isCurrent && (
                      <span className="text-[10px] font-medium text-teal-400 border border-teal-500/30 bg-teal-500/10 rounded-full px-2 py-0.5">
                        Current
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                    <span>{formatFileSize(doc.file_size_bytes)}</span>
                    <span className="text-white/20">·</span>
                    <span title={formatDateTime(doc.uploaded_at)}>{timeAgo(doc.uploaded_at)}</span>
                    {doc.change_notes && (
                      <>
                        <span className="text-white/20">·</span>
                        <span className="italic truncate max-w-[200px]" title={doc.change_notes}>
                          {doc.change_notes}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 flex items-center gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDownload(doc)}
                    disabled={downloadingId === doc.id}
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-teal-400 hover:bg-teal-500/10"
                    title="Download"
                  >
                    {downloadingId === doc.id ? (
                      <div className="h-3.5 w-3.5 rounded-full border-2 border-white/30 border-t-teal-400 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </Button>

                  {isAdmin && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm(`Delete version ${doc.version_number} of "${doc.filename}"?`)) {
                          setDeletingId(doc.id);
                          deleteMutation.mutate(doc.id);
                        }
                      }}
                      disabled={deleteMutation.isPending && deletingId === doc.id}
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-red-400 hover:bg-red-500/10"
                      title="Soft-delete this version"
                    >
                      {deleteMutation.isPending && deletingId === doc.id ? (
                        <div className="h-3.5 w-3.5 rounded-full border-2 border-white/30 border-t-red-400 animate-spin" />
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
            <p className="text-xs text-muted-foreground/50 text-center pt-1">
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
          onSuccess={() =>
            queryClient.invalidateQueries({ queryKey: ["documents", standardId] })
          }
        />
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export function StandardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: standard, isLoading } = useQuery({
    queryKey: ["standard", id],
    queryFn: () => getStandard(id!),
    enabled: !!id,
  });

  const queryClient = useQueryClient();
  const { isAdmin, isManager } = useAuth();

  const purchaseMutation = useMutation({
    mutationFn: (notes?: string) => purchaseStandard(id!, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["standard", id] });
      queryClient.invalidateQueries({ queryKey: ["standard", id, "history"] });
    },
    onError: () => {
      alert("Failed to purchase standard");
    }
  });

  const handlePurchase = () => {
    const notes = prompt("Enter purchase notes (optional):");
    if (notes !== null) {
      purchaseMutation.mutate(notes || undefined);
    }
  };

  const { data: history } = useQuery({
    queryKey: ["standard", id, "history"],
    queryFn: () => getStandardHistory(id!, 1, 20),
    enabled: !!id,
  });

  const { data: documentsData } = useQuery({
    queryKey: ["documents", id],
    queryFn: () => listDocuments(id!),
    enabled: !!id,
  });

  const { data: parentStandard } = useQuery({
    queryKey: ["standard", standard?.parent_standard_id],
    queryFn: () => getStandard(standard!.parent_standard_id!),
    enabled: !!standard?.parent_standard_id,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (!standard) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center space-y-4">
        <BookOpen className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-lg font-semibold text-foreground">Standard not found</p>
        <Button variant="outline" onClick={() => navigate("/standards")}>
          Back to library
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(-1)}
        className="gap-2 text-muted-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Library
      </Button>

      {/* Header card */}
      <Card className="overflow-hidden">
        {/* Gradient top bar */}
        <div className="h-1.5 w-full bg-gradient-to-r from-indigo-600 via-teal-500 to-blue-600" />
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600/20 border border-indigo-500/20 text-xs font-bold text-indigo-300">
                  ISO
                </div>
                <div>
                  <h1 className="text-xl font-bold text-foreground tracking-tight">
                    {standard.iso_reference}
                  </h1>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {standard.edition ? `Edition ${standard.edition}` : "No edition"}
                  </p>
                </div>
                <StatusBadge status={standard.status} />
                {standard.is_purchased ? (
                  <span className="text-xs font-medium text-teal-400 border border-teal-500/30 bg-teal-500/10 rounded-full px-2 py-0.5">
                    ✓ Purchased
                  </span>
                ) : (
                  (isAdmin || isManager) && (
                    <Button
                      size="sm"
                      onClick={handlePurchase}
                      disabled={purchaseMutation.isPending}
                      className="h-7 px-3 bg-teal-600 hover:bg-teal-700 text-xs gap-1"
                    >
                      {purchaseMutation.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        "Mark as Purchased"
                      )}
                    </Button>
                  )
                )}
              </div>
              <p className="text-base text-foreground leading-relaxed max-w-2xl">
                {standard.title}
              </p>
            </div>

            {standard.external_url && (
              <a
                href={standard.external_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0"
              >
                <Button variant="outline" size="sm" className="gap-2">
                  <ExternalLink className="h-3.5 w-3.5" />
                  View on ISO.org
                </Button>
              </a>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Meta row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { icon: Tag, label: "TC Committee", value: standard.tc_committee ?? "—" },
          { 
            icon: GitBranch, 
            label: "ISO Stage", 
            value: standard.stage_code && standard.stage_name 
              ? `${standard.stage_code} — ${standard.stage_name}` 
              : (standard.stage_code || standard.stage_name || "—") 
          },
          { icon: Calendar, label: "Stage Date", value: formatDate(standard.published_date) },
          { icon: Calendar, label: "Last Updated", value: formatDate(standard.updated_at) },
          { icon: Calendar, label: "Added", value: formatDate(standard.created_at) },
          {
            icon: Package,
            label: "Purchased",
            value: standard.is_purchased
              ? formatDate(standard.purchased_at)
              : "Not purchased",
          },
        ].map(({ icon: Icon, label, value }) => (
          <Card key={label} className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">
                {label}
              </p>
            </div>
            <p className="text-sm font-semibold text-foreground break-words">{value}</p>
          </Card>
        ))}
      </div>

      {/* Base Standard banner — shown when this record is an amendment */}
      {standard.parent_standard_id && (
        <div className="flex items-center gap-3 rounded-xl border border-indigo-500/25 bg-indigo-500/8 px-4 py-3">
          <GitBranch className="h-4 w-4 text-indigo-400 shrink-0" />
          <p className="text-sm text-indigo-300 flex-1">
            This is an amendment or corrigendum of{" "}
            <span className="font-semibold text-foreground">
              {parentStandard?.iso_reference ?? "the base standard"}
            </span>
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/standards/${standard.parent_standard_id}`)}
            className="gap-2 border-indigo-500/30 text-indigo-300 hover:text-indigo-200 shrink-0"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            View Base Standard
          </Button>
        </div>
      )}

      {/* Amendments card — shown on base standards that have child amendments */}
      {standard.amendments && standard.amendments.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <GitBranch className="h-4 w-4 text-yellow-400" />
              Amendments &amp; Corrigenda
              <span className="ml-1 rounded-full bg-yellow-500/15 border border-yellow-500/25 px-2 py-0.5 text-[10px] font-semibold text-yellow-400">
                {standard.amendments.length}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="divide-y divide-white/6">
              {standard.amendments.map((amd: Standard) => (
                <div
                  key={amd.id}
                  className="flex items-center justify-between py-3 gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-yellow-500/10 border border-yellow-500/20 shrink-0">
                      <ScrollText className="h-3.5 w-3.5 text-yellow-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-foreground">
                        {amd.iso_reference}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {amd.stage_code && amd.stage_name
                          ? `Stage ${amd.stage_code} — ${amd.stage_name}`
                          : (amd.stage_code ?? "—")}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <StatusBadge status={amd.status} />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/standards/${amd.id}`)}
                      className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground gap-1"
                    >
                      View
                      <ExternalLink className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs: History | Documents */}
      <Card>
        <CardContent className="p-6">
          <Tabs defaultValue="history">
            <TabsList>
              <TabsTrigger value="history" className="gap-2">
                <GitBranch className="h-4 w-4" />
                Change History
                {history && (
                  <span className="ml-1 rounded-full bg-white/10 px-2 py-0.5 text-[10px]">
                    {history.total}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="documents" className="gap-2">
                <FileText className="h-4 w-4" />
                Documents
                {documentsData && documentsData.total > 0 && (
                  <span className="ml-1 rounded-full bg-white/10 px-2 py-0.5 text-[10px]">
                    {documentsData.total}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>

            {/* History tab */}
            <TabsContent value="history">
              {history && history.items.length > 0 ? (
                <div className="relative">
                  {/* Timeline line */}
                  <div className="absolute left-[18px] top-2 bottom-0 w-px bg-white/8" />
                  <div className="space-y-4 pl-12">
                    {history.items.map((item) => {
                      const Icon = EVENT_ICONS[item.event_type] ?? GitBranch;
                      const colorClass =
                        EVENT_COLORS[item.event_type] ?? "border-white/10 bg-white/5 text-muted-foreground";
                      return (
                        <div key={item.id} className="relative">
                          {/* Timeline dot */}
                          <div
                            className={`absolute -left-10 flex h-7 w-7 items-center justify-center rounded-full border ${colorClass}`}
                          >
                            <Icon className="h-3.5 w-3.5" />
                          </div>
                          <div className="rounded-lg border border-white/8 bg-white/4 p-4">
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <StatusBadge status={item.event_type} />
                                <span className="text-xs text-muted-foreground capitalize">
                                  via {item.source}
                                </span>
                              </div>
                              <time className="text-xs text-muted-foreground">
                                {formatDateTime(item.created_at)}
                              </time>
                            </div>
                            {item.new_value && (
                              <JsonSnapshot value={item.new_value} />
                            )}
                            {item.notes && (
                              <p className="mt-2 text-xs text-muted-foreground">{item.notes}</p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
                  <GitBranch className="h-10 w-10 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">No change history yet</p>
                  <p className="text-xs text-muted-foreground/60">
                    History is recorded automatically when RSS feeds are polled.
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Documents tab */}
            <TabsContent value="documents">
              <DocumentsTab standardId={id!} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
