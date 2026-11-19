import { QueryError } from "@/components/QueryError";
import { ChangeHistoryTimeline } from "@/components/standards/ChangeHistoryTimeline";
import { StandardDocuments } from "@/components/standards/StandardDocuments";
import { Dialog, DialogContent, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BookOpen, Calendar, ExternalLink, FileText,
  GitBranch, Loader2, Package, ScrollText, Tag
} from "lucide-react";
import { getStandard, getStandardHistory, purchaseStandard, type Standard } from "@/api/standards";
import {
  listDocuments
} from "@/api/documents";
import { useAuth } from "@/contexts/useAuth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";

export function StandardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: standard, isLoading } = useQuery({
    queryKey: ["standard", id],
    queryFn: () => getStandard(id!),
    enabled: !!id,
  });

  const queryClient = useQueryClient();
  const { isManager } = useAuth();

  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [purchaseNotes, setPurchaseNotes] = useState("");
  const purchaseMutation = useMutation({
    mutationFn: (notes?: string) => purchaseStandard(id!, notes),
    onSuccess: () => {
      setPurchaseOpen(false);
      queryClient.invalidateQueries({ queryKey: ["standard", id] });
      queryClient.invalidateQueries({ queryKey: ["standard", id, "history"] });
    },
  });

  const { data: history, isError: historyFailed, refetch: retryHistory } = useQuery({
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
        <BookOpen className="h-12 w-12 text-subtle-foreground" />
        <p className="text-lg font-semibold text-foreground">Standard not found</p>
        <Button variant="outline" onClick={() => navigate("/standards")}>
          Back to library
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Dialog open={purchaseOpen} onOpenChange={open => { if (!purchaseMutation.isPending) setPurchaseOpen(open); }}>
        <DialogContent aria-describedby={undefined}>
          <DialogTitle>Record purchase</DialogTitle>
          <form className="space-y-4" onSubmit={event => {
            event.preventDefault();
            if (standard.can_purchase && !purchaseMutation.isPending) purchaseMutation.mutate(purchaseNotes || undefined);
          }}>
            <p className="text-sm">{standard.iso_reference}</p>
            <Label htmlFor="purchase-notes">Purchase notes (optional)</Label>
            <Input id="purchase-notes" value={purchaseNotes} onChange={event => setPurchaseNotes(event.target.value)} />
            <DialogFooter>
              <Button type="button" variant="outline" disabled={purchaseMutation.isPending} onClick={() => setPurchaseOpen(false)}>Cancel</Button>
              <Button disabled={!standard.can_purchase || purchaseMutation.isPending}>Record purchase</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/standards")}
        className="gap-2 text-muted-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to library
      </Button>

      {/* Header card */}
      <Card className="overflow-hidden">
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-soft border border-brand-line text-xs font-bold text-brand">
                  {standard.standards_body ?? "ISO"}
                </div>
                <div>
                  <h1 className="text-xl font-bold text-foreground tracking-tight">
                    {standard.iso_reference}
                  </h1>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {standard.edition ? `Edition ${standard.edition}` : "No edition"}
                  </p>
                </div>
                {standard.is_purchased ? (
                  <span className="text-xs font-medium text-success border border-success-line bg-success-soft rounded-full px-2 py-0.5">
                    ✓ Purchased
                  </span>
                ) : (
                  isManager && (
                    <Button
                      size="sm"
                      onClick={() => { setPurchaseNotes(""); setPurchaseOpen(true); }}
                      disabled={purchaseMutation.isPending || !standard.can_purchase}
                      title={standard.purchase_blocked_reason ?? undefined}
                      className="h-7 px-3  text-xs gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {purchaseMutation.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        "Record purchase"
                      )}
                    </Button>
                  )
                )}
              </div>
              {isManager && !standard.is_purchased && !standard.can_purchase && <p className="text-sm text-muted-foreground">{standard.purchase_blocked_reason}</p>}
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
                  {standard.standards_body ? `View on ${standard.standards_body}` : "View source"}
                </Button>
              </a>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Meta row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { icon: Tag, label: "TC Committee", value: standard.tc_committee ?? "—" },
          {
            icon: GitBranch,
            label: "Stage",
            value: standard.stage_code && standard.stage_name
              ? `${standard.stage_code} — ${standard.stage_name}`
              : (standard.stage_code || standard.stage_name || "—")
          },
          { icon: Calendar, label: "Stage Date", value: formatDate(standard.published_date) },
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
        <div className="flex items-center gap-3 rounded-xl border border-brand-line bg-brand-soft px-4 py-3">
          <GitBranch className="h-4 w-4 text-brand shrink-0" />
          <p className="text-sm text-brand flex-1">
            This is an amendment or corrigendum of{" "}
            <span className="font-semibold text-foreground">
              {parentStandard?.iso_reference ?? "the base standard"}
            </span>
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/standards/${standard.parent_standard_id}`)}
            className="gap-2 border-brand-line text-brand hover:text-brand shrink-0"
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
              <GitBranch className="h-4 w-4 text-warning" />
              Amendments &amp; Corrigenda
              <span className="ml-1 rounded-full bg-warning-soft border border-warning-line px-2 py-0.5 text-[10px] font-semibold text-warning">
                {standard.amendments.length}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="divide-y divide-border">
              {standard.amendments.map((amd: Standard) => (
                <div
                  key={amd.id}
                  className="flex items-center justify-between py-3 gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-warning-soft border border-warning-line shrink-0">
                      <ScrollText className="h-3.5 w-3.5 text-warning" />
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
                  <span className="ml-1 rounded-full bg-foreground/10 px-2 py-0.5 text-[10px]">
                    {history.total}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="documents" className="gap-2">
                <FileText className="h-4 w-4" />
                Documents
                {documentsData && documentsData.total > 0 && (
                  <span className="ml-1 rounded-full bg-foreground/10 px-2 py-0.5 text-[10px]">
                    {documentsData.total}
                  </span>
                )}
              </TabsTrigger>
            </TabsList>

            {/* History tab */}
            <TabsContent value="history">
              {historyFailed && !history ? <QueryError subject="change history" onRetry={retryHistory} /> : history ? <ChangeHistoryTimeline items={history.items} /> : <Skeleton className="h-20 w-full" />}
            </TabsContent>

            {/* Documents tab */}
            <TabsContent value="documents">
              <StandardDocuments
                standardId={id!}
                canUpload={standard.can_upload}
                blockedReason={standard.purchase_blocked_reason}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
