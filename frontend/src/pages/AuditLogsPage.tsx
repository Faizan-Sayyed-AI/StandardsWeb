import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Layers, Download, Search, ChevronDown, ChevronUp, Clock, ShieldAlert, Database, Laptop
} from "lucide-react";
import { getAuditLogs, exportAuditLogsCsv } from "@/api/admin";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/utils";

export function AuditLogsPage() {
  const [page, setPage] = useState(1);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const queryParams = {
    page,
    page_size: 20,
    actor: actor.trim() || undefined,
    action: action.trim() || undefined,
    resource_type: resourceType.trim() || undefined,
    start_date: startDate ? new Date(startDate).toISOString() : undefined,
    end_date: endDate ? new Date(endDate).toISOString() : undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", queryParams],
    queryFn: () => getAuditLogs(queryParams),
  });

  const handleExportCsv = async () => {
    try {
      const exportParams = {
        actor: actor.trim() || undefined,
        action: action.trim() || undefined,
        resource_type: resourceType.trim() || undefined,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
      };
      const csvBlob = await exportAuditLogsCsv(exportParams);
      const url = window.URL.createObjectURL(csvBlob);
      const link = document.createElement("a");
      const dateStr = new Date().toISOString().split("T")[0];
      link.href = url;
      link.setAttribute("download", `audit_logs_${dateStr}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert("Failed to export audit logs CSV");
    }
  };

  const totalPages = data ? data.pages : 1;

  const toggleRow = (id: number) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Layers className="h-6 w-6 text-indigo-400" />
            Audit Logs
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total.toLocaleString()} immutable audit trail events` : "Loading logs…"}
          </p>
        </div>
        <Button onClick={handleExportCsv} className="gap-2 bg-indigo-600 hover:bg-indigo-700">
          <Download className="h-4 w-4" />
          Export to CSV
        </Button>
      </div>

      {/* Filters bar */}
      <Card className="p-4">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
          <div className="space-y-1.5">
            <Label htmlFor="filter-actor" className="text-xs text-muted-foreground">Actor</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                id="filter-actor"
                placeholder="Username, email or UUID"
                value={actor}
                onChange={(e) => { setActor(e.target.value); setPage(1); }}
                className="pl-8 text-xs h-9 bg-slate-950/40 border-white/10"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-action" className="text-xs text-muted-foreground">Action</Label>
            <Input
              id="filter-action"
              placeholder="e.g. user.created"
              value={action}
              onChange={(e) => { setAction(e.target.value); setPage(1); }}
              className="text-xs h-9 bg-slate-950/40 border-white/10"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-resource" className="text-xs text-muted-foreground">Resource Type</Label>
            <Input
              id="filter-resource"
              placeholder="e.g. user, standard"
              value={resourceType}
              onChange={(e) => { setResourceType(e.target.value); setPage(1); }}
              className="text-xs h-9 bg-slate-950/40 border-white/10"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-start" className="text-xs text-muted-foreground">Start Date</Label>
            <Input
              id="filter-start"
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); setPage(1); }}
              className="text-xs h-9 bg-slate-950/40 border-white/10 text-muted-foreground"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="filter-end" className="text-xs text-muted-foreground">End Date</Label>
            <Input
              id="filter-end"
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setPage(1); }}
              className="text-xs h-9 bg-slate-950/40 border-white/10 text-muted-foreground"
            />
          </div>
        </div>
      </Card>

      {/* Logs Table */}
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead className="w-44">Timestamp</TableHead>
              <TableHead className="w-44">Action</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead className="w-32">Resource</TableHead>
              <TableHead className="w-36">IP Address</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              : data?.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground text-sm">
                      No audit events match your filters.
                    </TableCell>
                  </TableRow>
                ) : (
                  data?.items.map((log) => (
                    <>
                      <TableRow
                        key={log.id}
                        className="cursor-pointer hover:bg-white/4 transition-colors"
                        onClick={() => toggleRow(log.id)}
                      >
                        <TableCell className="text-center">
                          {expandedRow === log.id ? (
                            <ChevronUp className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          )}
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
                            <Clock className="h-3 w-3 text-indigo-400/80" />
                            {formatDateTime(log.created_at)}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="font-mono text-xs font-semibold text-teal-300">
                            {log.action}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-foreground font-medium">
                            {log.actor_username ?? (
                              <span className="text-muted-foreground/60 italic flex items-center gap-1">
                                <Laptop className="h-3 w-3" />
                                system
                              </span>
                            )}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                            <Database className="h-3 w-3 text-indigo-400/60" />
                            {log.resource_type}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs font-mono text-muted-foreground/85">
                            {log.ip_address ?? "—"}
                          </span>
                        </TableCell>
                      </TableRow>
                      
                      {expandedRow === log.id && (
                        <TableRow className="bg-slate-900/40 hover:bg-slate-900/40">
                          <TableCell colSpan={6} className="px-12 py-4">
                            <div className="space-y-2">
                              <div className="flex justify-between text-[10px] text-muted-foreground/80 uppercase font-semibold tracking-wider">
                                <span>Audit Metadata Context Payload</span>
                                {log.resource_id && <span>Resource ID: {log.resource_id}</span>}
                              </div>
                              <pre className="text-[11px] font-mono bg-slate-950/70 border border-white/5 p-3.5 rounded-lg overflow-x-auto text-slate-300 leading-relaxed max-w-full">
                                {JSON.stringify(log.payload, null, 2)}
                              </pre>
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  ))
                )}
          </TableBody>
        </Table>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-white/8 px-6 py-3">
            <p className="text-xs text-muted-foreground">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
