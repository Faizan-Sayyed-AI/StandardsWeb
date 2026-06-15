import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, BookOpen, Calendar, ExternalLink, FileText,
  GitBranch, Package, ScrollText, Tag,
} from "lucide-react";
import { getStandard, getStandardHistory } from "@/api/standards";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime, timeAgo } from "@/lib/utils";

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

export function StandardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: standard, isLoading } = useQuery({
    queryKey: ["standard", id],
    queryFn: () => getStandard(id!),
    enabled: !!id,
  });

  const { data: history } = useQuery({
    queryKey: ["standard", id, "history"],
    queryFn: () => getStandardHistory(id!, 1, 20),
    enabled: !!id,
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
                {standard.is_purchased && (
                  <span className="text-xs font-medium text-teal-400 border border-teal-500/30 bg-teal-500/10 rounded-full px-2 py-0.5">
                    ✓ Purchased
                  </span>
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { icon: Tag, label: "TC Committee", value: standard.tc_committee ?? "—" },
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
            <p className="text-sm font-semibold text-foreground">{value}</p>
          </Card>
        ))}
      </div>

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
                              <div className="mt-2 rounded-md bg-white/4 p-3 font-mono text-xs text-muted-foreground overflow-auto max-h-40">
                                <pre>{JSON.stringify(item.new_value, null, 2)}</pre>
                              </div>
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
              <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
                <FileText className="h-10 w-10 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">Document management coming in M4</p>
                <p className="text-xs text-muted-foreground/60">
                  PDF attachments and file versioning will be available in the next milestone.
                </p>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
