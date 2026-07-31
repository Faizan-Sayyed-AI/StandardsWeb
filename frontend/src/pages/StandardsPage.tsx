import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronRight, ChevronUp, Loader2, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import {
  createStandard, listCommittees, listStandards, listStandardsBodies,
  type StandardCreatePayload, type StandardGrouped, type StandardsListParams,
} from "@/api/standards";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge, StatusBadge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate } from "@/lib/utils";

const STATUS_OPTIONS = ["", "active", "withdrawn", "under_review", "replaced", "amended", "revised"];

const STAGE_OPTIONS = [
  { label: "All Stages", value: "" },
  { label: "Published (60.60)", value: "60.60" },
  { label: "Confirmed (90.93)", value: "90.93" },
  { label: "Under Periodical Review (90.20)", value: "90.20" },
  { label: "Withdrawal (95.99)", value: "95.99" },
  { label: "Working Draft (20.x)", value: "20.x" },
  { label: "Committee Draft (30.x)", value: "30.x" },
  { label: "DIS (40.x)", value: "40.x" },
  { label: "FDIS (50.x)", value: "50.x" },
];

const SORT_OPTIONS = [
  { value: "published_date", label: "Stage Date" },
  { value: "updated_at", label: "Last updated" },
  { value: "iso_reference", label: "ISO Reference" },
  { value: "title", label: "Title" },
  { value: "status", label: "Status" },
];

const STANDARDS_BODY_OPTIONS = ["ISO", "IEC", "IEEE", "ASTM", "Other"];

const DEFAULT_CREATE_FORM: StandardCreatePayload = {
  iso_reference: "",
  title: "",
  standards_body: "ISO",
  edition: "",
  tc_committee: "",
  status: "active",
  published_date: "",
  external_url: "",
};

export function StandardsPage() {
  const navigate = useNavigate();
  // Filters, sort and pagination live in the URL query string rather than
  // component state, so they survive navigating into a standard's detail page
  // and back (this component unmounts on navigation, which previously reset
  // every filter). It also makes a filtered view shareable and bookmarkable.
  const [searchParams, setSearchParams] = useSearchParams();

  const qp = (key: string, fallback = "") => searchParams.get(key) ?? fallback;

  const params: StandardsListParams = {
    page: Number(qp("page", "1")) || 1,
    page_size: Number(qp("page_size", "25")) || 25,
    sort_by: qp("sort_by", "published_date"),
    sort_order: qp("sort_order", "desc") === "asc" ? "asc" : "desc",
    status: qp("status") || undefined,
    is_purchased: searchParams.has("purchased")
      ? searchParams.get("purchased") === "true"
      : undefined,
  };
  const search = qp("q");
  const showFilters = qp("filters") === "1";
  const committeeFilter = qp("committee");
  const stageFilter = qp("stage");
  const standardsBodyFilter = qp("body");

  /**
   * Merge updates into the query string. An empty string or undefined removes
   * the key, keeping the URL tidy. Any change resets to page 1 unless the
   * update sets `page` itself. replace:true so typing in the search box does
   * not push a history entry per keystroke.
   */
  const setQp = (
    updates: Record<string, string | number | boolean | undefined>,
    resetPage = true,
  ) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (resetPage && updates.page === undefined) next.set("page", "1");
        for (const [key, value] of Object.entries(updates)) {
          if (value === undefined || value === "") next.delete(key);
          else next.set(key, String(value));
        }
        return next;
      },
      { replace: true },
    );
  };
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const { isAdmin, isManager } = useAuth();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<StandardCreatePayload>(DEFAULT_CREATE_FORM);
  const [otherBody, setOtherBody] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: createStandard,
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["standards", "list"] });
      setShowCreate(false);
      setCreateForm(DEFAULT_CREATE_FORM);
      setOtherBody("");
      setCreateError(null);
      navigate(`/standards/${created.id}`);
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      setCreateError(err?.response?.data?.detail ?? "Failed to create standard");
    },
  });

  const canCreate = isAdmin || isManager;

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const queryParams: StandardsListParams = {
    ...params,
    search: search.trim() || undefined,
    tc_committee: committeeFilter || undefined,
    standards_body: standardsBodyFilter || undefined,
    stage: stageFilter || undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["standards", "list", queryParams],
    queryFn: () => listStandards(queryParams),
    placeholderData: (prev) => prev,
  });

  // Independent of the current page/filters, so the dropdown always lists
  // every committee — not just the ones present on the currently loaded page.
  const { data: committees = [] } = useQuery({
    queryKey: ["standards", "committees"],
    queryFn: listCommittees,
  });

  // Independent of the current page/filters, same reasoning as the
  // committees dropdown above.
  const { data: standardsBodies = [] } = useQuery({
    queryKey: ["standards", "standards-bodies"],
    queryFn: listStandardsBodies,
  });

  const updateSort = (sortBy: string) => {
    setQp({
      sort_by: sortBy,
      sort_order:
        params.sort_by === sortBy
          ? params.sort_order === "asc"
            ? "desc"
            : "asc"
          : "desc",
    });
  };

  const SortIcon = ({ col }: { col: string }) => {
    if (params.sort_by !== col) return <ChevronDown className="h-3 w-3 opacity-30" />;
    return params.sort_order === "asc" ? (
      <ChevronUp className="h-3 w-3 text-indigo-400" />
    ) : (
      <ChevronDown className="h-3 w-3 text-indigo-400" />
    );
  };

  const filterPill = (active: boolean) =>
    `rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
      active
        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
        : "border-border text-muted-foreground hover:border-foreground/20"
    }`;

  const totalPages = data ? Math.ceil(data.total / (params.page_size ?? 25)) : 1;

  return (
    <div className="flex h-full flex-col gap-6">
      {/* Sticky top section: header, search, filters */}
      <div className="flex-shrink-0 space-y-6">
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
        {canCreate && (
          <Button onClick={() => setShowCreate(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            Add Standard
          </Button>
        )}
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
                setQp({ q: e.target.value });
              }}
              className="pl-9"
            />
            {search && (
              <button
                onClick={() => setQp({ q: undefined })}
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
            onClick={() => setQp({ filters: showFilters ? undefined : "1" }, false)}
            className="gap-2"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Filters
          </Button>
        </div>

        {/* Expanded filters */}
        {showFilters && (
          <div className="mt-4 pt-4 border-t border-border space-y-3">
            {/* Row 1 — Status pills */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Status</p>
              <div className="flex gap-1.5 flex-wrap">
                {STATUS_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() =>
                      setQp({ status: s || undefined })
                    }
                    className={filterPill(params.status === (s || undefined))}
                  >
                    {s ? s.replace(/_/g, " ") : "All"}
                  </button>
                ))}
              </div>
            </div>

            {/* Row 2 — Committee dropdown | Stage dropdown | Purchased pills | Sort pills */}
            <div className="flex flex-wrap items-end gap-4">
              {/* Committee dropdown */}
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Committee</p>
                <div className="relative">
                  <select
                    value={committeeFilter}
                    onChange={(e) => {
                      setQp({ committee: e.target.value });
                    }}
                    className="appearance-none min-w-[180px] cursor-pointer rounded-lg border border-input bg-background px-4 py-2 pr-8 text-sm text-foreground focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">All Committees</option>
                    {committees.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                </div>
              </div>

              {/* Standards Body dropdown */}
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Body</p>
                <div className="relative">
                  <select
                    value={standardsBodyFilter}
                    onChange={(e) => {
                      setQp({ body: e.target.value });
                    }}
                    className="appearance-none min-w-[140px] cursor-pointer rounded-lg border border-input bg-background px-4 py-2 pr-8 text-sm text-foreground focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">All Bodies</option>
                    {standardsBodies.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                </div>
              </div>

              {/* Stage dropdown */}
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Stage</p>
                <div className="relative">
                  <select
                    value={stageFilter}
                    onChange={(e) => {
                      setQp({ stage: e.target.value });
                    }}
                    className="appearance-none min-w-[200px] cursor-pointer rounded-lg border border-input bg-background px-4 py-2 pr-8 text-sm text-foreground focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {STAGE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                </div>
              </div>

              {/* Purchased pills */}
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
                        setQp({ purchased: val })
                      }
                      className={filterPill(params.is_purchased === val)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Sort pills */}
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Sort by</p>
                <div className="flex gap-1.5 flex-wrap">
                  {SORT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => updateSort(opt.value)}
                      className={`flex items-center gap-1 ${filterPill(params.sort_by === opt.value)}`}
                    >
                      {opt.label}
                      {params.sort_by === opt.value && <SortIcon col={opt.value} />}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </Card>
      </div>

      {/* Table — independently scrollable, fills remaining height */}
      <Card className="flex flex-1 min-h-0 flex-col overflow-hidden">
        <Table containerClassName="flex-1 min-h-0 overflow-y-auto">
          <TableHeader className="sticky top-0 z-10 bg-background">
            <TableRow className="border-b border-border hover:bg-transparent">
              <TableHead className="w-8" />
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
              <TableHead className="w-48">Stage</TableHead>
              <TableHead className="w-24">Edition</TableHead>
              <TableHead className="w-32">
                <button
                  className="flex items-center gap-1 hover:text-foreground"
                  onClick={() => updateSort("published_date")}
                >
                  Stage Date <SortIcon col="published_date" />
                </button>
              </TableHead>
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
            {isLoading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-64" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-16 rounded-full" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                  <TableCell><Skeleton className="h-4 w-20 ml-auto" /></TableCell>
                </TableRow>
              ))
            ) : (data?.items.length ?? 0) === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="py-16 text-center">
                  <div className="flex flex-col items-center gap-3">
                    <BookOpen className="h-10 w-10 text-muted-foreground/30" />
                    <p className="text-sm font-medium text-muted-foreground">
                      No standards match the current filters
                    </p>
                    <p className="text-xs text-muted-foreground/60">
                      Try adjusting your search or filter criteria
                    </p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              (data?.items ?? []).flatMap((std: StandardGrouped) => {
                const groupKey = std.base_reference ?? std.id;
                const hasVersions = std.versions_count > 1;
                const expanded = hasVersions && expandedGroups.has(groupKey);

                const primaryRow = (
                  <TableRow
                    key={std.id}
                    className="cursor-pointer hover:bg-foreground/4 transition-colors"
                    onClick={() => navigate(`/standards/${std.id}`)}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      {hasVersions && (
                        <button
                          onClick={() => toggleGroup(groupKey)}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs transition-all duration-200 ${
                            expanded
                              ? "bg-indigo-500/20 text-indigo-300"
                              : "bg-secondary text-secondary-foreground"
                          }`}
                        >
                          {expanded ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                          +{std.versions_count - 1} versions
                        </button>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs font-bold text-indigo-400 hover:underline">
                        {std.iso_reference}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <p className="truncate text-foreground">{std.title}</p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {std.standards_body && (
                          <Badge variant="secondary" className="text-[9px] py-0 px-1.5">
                            {std.standards_body}
                          </Badge>
                        )}
                        {std.is_purchased && (
                          <span className="inline-flex items-center bg-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30">
                            ✓ Purchased
                          </span>
                        )}
                      </div>
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
                      {std.stage_name ? (
                        <Badge variant="secondary" className="text-[10px] font-medium py-0.5 px-2 text-left leading-normal whitespace-normal">
                          {std.stage_name}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">{std.edition ?? "—"}</span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(std.published_date)}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {formatDate(std.updated_at)}
                    </TableCell>
                  </TableRow>
                );

                if (!expanded) return [primaryRow];

                const versionRows = std.versions.map((v) => (
                  <TableRow
                    key={v.id}
                    className="cursor-pointer border-l-2 border-indigo-500/30 ml-4 bg-foreground/5 transition-all duration-200 hover:bg-foreground/8"
                    onClick={() => navigate(`/standards/${v.id}`)}
                  >
                    <TableCell />
                    <TableCell>
                      <span className="font-mono text-xs font-bold text-indigo-400 hover:underline">
                        {v.iso_reference}
                      </span>
                    </TableCell>
                    <TableCell colSpan={2} />
                    <TableCell>
                      <StatusBadge status={v.status} />
                    </TableCell>
                    <TableCell>
                      {v.stage_name ? (
                        <Badge variant="secondary" className="text-[10px] font-medium py-0.5 px-2 text-left leading-normal whitespace-normal">
                          {v.stage_name}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell />
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(v.published_date)}
                    </TableCell>
                    <TableCell />
                  </TableRow>
                ));

                return [primaryRow, ...versionRows];
              })
            )}
          </TableBody>
        </Table>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-6 py-3">
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
                onClick={() => setQp({ page: (params.page ?? 1) - 1 }, false)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={(params.page ?? 1) >= totalPages}
                onClick={() => setQp({ page: (params.page ?? 1) + 1 }, false)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Add Standard Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-indigo-400" />
              Add Standard
            </DialogTitle>
            <DialogDescription>
              Manually add a standard from a body with no RSS feed (e.g. ASTM).
            </DialogDescription>
          </DialogHeader>

          {createError && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
              {createError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="std-reference">Reference Number</Label>
              <Input
                id="std-reference"
                placeholder="ASTM D638-14"
                value={createForm.iso_reference}
                onChange={(e) => setCreateForm((f) => ({ ...f, iso_reference: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="std-title">Title</Label>
              <Input
                id="std-title"
                placeholder="Standard Test Method for Tensile Properties of Plastics"
                value={createForm.title}
                onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="std-body">Standards Body</Label>
                <select
                  id="std-body"
                  value={createForm.standards_body}
                  onChange={(e) => setCreateForm((f) => ({ ...f, standards_body: e.target.value }))}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring text-foreground"
                >
                  {STANDARDS_BODY_OPTIONS.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="std-edition">Edition (optional)</Label>
                <Input
                  id="std-edition"
                  placeholder="2014"
                  value={createForm.edition ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, edition: e.target.value }))}
                />
              </div>
            </div>

            {createForm.standards_body === "Other" && (
              <div className="space-y-1.5">
                <Label htmlFor="std-body-other">Body name</Label>
                <Input
                  id="std-body-other"
                  placeholder="e.g. BSI, DIN"
                  value={otherBody}
                  onChange={(e) => setOtherBody(e.target.value)}
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="std-committee">Committee / Working Group (optional)</Label>
                <Input
                  id="std-committee"
                  placeholder="D20"
                  value={createForm.tc_committee ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, tc_committee: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="std-published">Published date (optional)</Label>
                <Input
                  id="std-published"
                  type="date"
                  value={createForm.published_date ?? ""}
                  onChange={(e) => setCreateForm((f) => ({ ...f, published_date: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="std-url">External URL (optional)</Label>
              <Input
                id="std-url"
                placeholder="https://www.astm.org/d0638-14.html"
                value={createForm.external_url ?? ""}
                onChange={(e) => setCreateForm((f) => ({ ...f, external_url: e.target.value }))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { setShowCreate(false); setCreateError(null); }}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                const body = createForm.standards_body === "Other" ? otherBody : createForm.standards_body;
                createMutation.mutate({
                  ...createForm,
                  standards_body: body,
                  edition: createForm.edition || undefined,
                  tc_committee: createForm.tc_committee || undefined,
                  published_date: createForm.published_date || undefined,
                  external_url: createForm.external_url || undefined,
                });
              }}
              disabled={
                createMutation.isPending ||
                !createForm.iso_reference ||
                !createForm.title ||
                (createForm.standards_body === "Other" && !otherBody)
              }
              className="gap-2"
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Add Standard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
