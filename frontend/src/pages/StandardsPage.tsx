import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronUp, Search, SlidersHorizontal, X } from "lucide-react";
import { listStandards, type StandardsListParams } from "@/api/standards";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";

const STATUS_OPTIONS = ["", "active", "withdrawn", "replaced", "amended", "revised"];
const SORT_OPTIONS = [
  { value: "updated_at", label: "Last updated" },
  { value: "iso_reference", label: "ISO Reference" },
  { value: "title", label: "Title" },
  { value: "status", label: "Status" },
];

export function StandardsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useState<StandardsListParams>({
    page: 1,
    page_size: 25,
    sort_by: "updated_at",
    sort_order: "desc",
  });
  const [search, setSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const queryParams: StandardsListParams = {
    ...params,
    search: search.trim() || undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["standards", "list", queryParams],
    queryFn: () => listStandards(queryParams),
    placeholderData: (prev) => prev,
  });

  const updateSort = (sortBy: string) => {
    setParams((p) => ({
      ...p,
      sort_by: sortBy,
      sort_order:
        p.sort_by === sortBy ? (p.sort_order === "asc" ? "desc" : "asc") : "desc",
      page: 1,
    }));
  };

  const SortIcon = ({ col }: { col: string }) => {
    if (params.sort_by !== col) return <ChevronDown className="h-3 w-3 opacity-30" />;
    return params.sort_order === "asc" ? (
      <ChevronUp className="h-3 w-3 text-indigo-400" />
    ) : (
      <ChevronDown className="h-3 w-3 text-indigo-400" />
    );
  };

  const totalPages = data ? Math.ceil(data.total / (params.page_size ?? 25)) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-indigo-400" />
            Standards Library
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total.toLocaleString()} standards` : "Loading…"}
          </p>
        </div>
      </div>

      {/* Search + filters bar */}
      <Card className="p-4">
        <div className="flex gap-3 flex-wrap">
          {/* Search */}
          <div className="relative flex-1 min-w-56">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search ISO reference, title, committee…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setParams((p) => ({ ...p, page: 1 }));
              }}
              className="pl-9"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Filter toggle */}
          <Button
            variant={showFilters ? "default" : "outline"}
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
            className="gap-2"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Filters
          </Button>
        </div>

        {/* Expanded filters */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t border-white/8 flex flex-wrap gap-3">
            {/* Status filter */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Status</p>
              <div className="flex gap-1.5 flex-wrap">
                {STATUS_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() =>
                      setParams((p) => ({ ...p, status: s || undefined, page: 1 }))
                    }
                    className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                      params.status === (s || undefined)
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
                    }`}
                  >
                    {s || "All"}
                  </button>
                ))}
              </div>
            </div>

            {/* Purchased filter */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Purchased</p>
              <div className="flex gap-1.5">
                {[
                  { label: "All", val: undefined },
                  { label: "Yes", val: true },
                  { label: "No", val: false },
                ].map(({ label, val }) => (
                  <button
                    key={label}
                    onClick={() =>
                      setParams((p) => ({ ...p, is_purchased: val, page: 1 }))
                    }
                    className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                      params.is_purchased === val
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Sort */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Sort by</p>
              <div className="flex gap-1.5 flex-wrap">
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => updateSort(opt.value)}
                    className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                      params.sort_by === opt.value
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
                    }`}
                  >
                    {opt.label}
                    {params.sort_by === opt.value && (
                      <SortIcon col={opt.value} />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* Table */}
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-36">
                <button
                  className="flex items-center gap-1 hover:text-foreground"
                  onClick={() => updateSort("iso_reference")}
                >
                  Reference <SortIcon col="iso_reference" />
                </button>
              </TableHead>
              <TableHead>
                <button
                  className="flex items-center gap-1 hover:text-foreground"
                  onClick={() => updateSort("title")}
                >
                  Title <SortIcon col="title" />
                </button>
              </TableHead>
              <TableHead className="w-28">Committee</TableHead>
              <TableHead className="w-28">
                <button
                  className="flex items-center gap-1 hover:text-foreground"
                  onClick={() => updateSort("status")}
                >
                  Status <SortIcon col="status" />
                </button>
              </TableHead>
              <TableHead className="w-24">Edition</TableHead>
              <TableHead className="w-28 text-right">
                <button
                  className="flex items-center gap-1 ml-auto hover:text-foreground"
                  onClick={() => updateSort("updated_at")}
                >
                  Updated <SortIcon col="updated_at" />
                </button>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-64" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-16 rounded-full" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-20 ml-auto" /></TableCell>
                  </TableRow>
                ))
              : data?.items.map((std) => (
                  <TableRow
                    key={std.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/standards/${std.id}`)}
                  >
                    <TableCell>
                      <span className="font-mono text-xs font-semibold text-indigo-300">
                        {std.iso_reference}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <p className="truncate text-foreground">{std.title}</p>
                      {std.is_purchased && (
                        <span className="text-[10px] text-teal-400">✓ Purchased</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {std.tc_committee ?? "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={std.status} />
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">{std.edition ?? "—"}</span>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {formatDate(std.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-white/8 px-6 py-3">
            <p className="text-xs text-muted-foreground">
              Showing {(((params.page ?? 1) - 1) * (params.page_size ?? 25)) + 1}–
              {Math.min((params.page ?? 1) * (params.page_size ?? 25), data.total)} of{" "}
              {data.total}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={(params.page ?? 1) <= 1}
                onClick={() => setParams((p) => ({ ...p, page: (p.page ?? 1) - 1 }))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(params.page ?? 1) >= totalPages}
                onClick={() => setParams((p) => ({ ...p, page: (p.page ?? 1) + 1 }))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
