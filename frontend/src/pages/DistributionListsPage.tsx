import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Trash2, Mail, Users, ToggleLeft, Settings, Info, Loader2, ArrowRight
} from "lucide-react";
import {
  listDistributionLists,
  createDistributionList,
  updateDistributionList,
  deleteDistributionList,
  listMembers,
  addMember,
  removeMember,
  listTriggerMappings,
  createTriggerMapping,
  deleteTriggerMapping,
  type DistributionList,
  type DistributionListMember,
  type TriggerMapping
} from "@/api/distributionLists";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

const EVENT_TYPES = [
  { value: "new", label: "New Publication" },
  { value: "updated", label: "Standard Updated / Revised" },
  { value: "amended", label: "Standard Amended" },
  { value: "withdrawn", label: "Standard Withdrawn" },
  { value: "replaced", label: "Standard Replaced" },
  { value: "purchased", label: "Standard Purchased" },
  { value: "document_uploaded", label: "Document Uploaded" },
  { value: "status_change", label: "Critical Feed Poll Failure / Status Change" },
];

export function DistributionListsPage() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"lists" | "mappings">("lists");
  
  // Lists Dialogs & Form State
  const [showCreateList, setShowCreateList] = useState(false);
  const [listName, setListName] = useState("");
  const [listDesc, setListDesc] = useState("");
  const [listError, setListError] = useState<string | null>(null);

  // Selected List for managing members
  const [selectedList, setSelectedList] = useState<DistributionList | null>(null);
  
  // Add Member Form State
  const [memberEmail, setMemberEmail] = useState("");
  const [memberName, setMemberName] = useState("");
  const [memberError, setMemberError] = useState<string | null>(null);

  // Trigger Mapping Dialog State
  const [showCreateMapping, setShowCreateMapping] = useState(false);
  const [mappingEvent, setMappingEvent] = useState(EVENT_TYPES[0].value);
  const [mappingListId, setMappingListId] = useState("");
  const [mappingNotifyAll, setMappingNotifyAll] = useState(false);
  const [mappingError, setMappingError] = useState<string | null>(null);

  // Queries
  const { data: lists, isLoading: loadingLists } = useQuery({
    queryKey: ["distribution-lists"],
    queryFn: listDistributionLists,
  });

  const { data: members, isLoading: loadingMembers } = useQuery({
    queryKey: ["members", selectedList?.id],
    queryFn: () => listMembers(selectedList!.id),
    enabled: !!selectedList,
  });

  const { data: mappings, isLoading: loadingMappings } = useQuery({
    queryKey: ["trigger-mappings"],
    queryFn: listTriggerMappings,
    enabled: activeTab === "mappings",
  });

  // Mutations
  const createListMutation = useMutation({
    mutationFn: createDistributionList,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["distribution-lists"] });
      setShowCreateList(false);
      setListName("");
      setListDesc("");
      setListError(null);
    },
    onError: (err: any) => {
      setListError(err?.response?.data?.detail ?? "Failed to create list");
    }
  });

  const deleteListMutation = useMutation({
    mutationFn: deleteDistributionList,
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ["distribution-lists"] });
      if (selectedList?.id === variables) {
        setSelectedList(null);
      }
    }
  });

  const addMemberMutation = useMutation({
    mutationFn: ({ listId, email, name }: { listId: string; email: string; name?: string }) =>
      addMember(listId, { email, name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["members", selectedList?.id] });
      qc.invalidateQueries({ queryKey: ["distribution-lists"] });
      setMemberEmail("");
      setMemberName("");
      setMemberError(null);
    },
    onError: (err: any) => {
      setMemberError(err?.response?.data?.detail ?? "Failed to add member");
    }
  });

  const removeMemberMutation = useMutation({
    mutationFn: ({ listId, email }: { listId: string; email: string }) =>
      removeMember(listId, email),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["members", selectedList?.id] });
      qc.invalidateQueries({ queryKey: ["distribution-lists"] });
    }
  });

  const createMappingMutation = useMutation({
    mutationFn: createTriggerMapping,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trigger-mappings"] });
      setShowCreateMapping(false);
      setMappingError(null);
    },
    onError: (err: any) => {
      setMappingError(err?.response?.data?.detail ?? "Failed to create mapping");
    }
  });

  const deleteMappingMutation = useMutation({
    mutationFn: deleteTriggerMapping,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trigger-mappings"] });
    }
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Mail className="h-6 w-6 text-teal-400" />
            Notifications & Distribution Lists
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure email distribution groups and map system events to specific lists.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-white/10 gap-2">
        <button
          onClick={() => setActiveTab("lists")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-[2px] ${
            activeTab === "lists"
              ? "border-teal-500 text-teal-300"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Distribution Lists
        </button>
        <button
          onClick={() => setActiveTab("mappings")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-[2px] ${
            activeTab === "mappings"
              ? "border-teal-500 text-teal-300"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          Event Trigger Mappings
        </button>
      </div>

      {activeTab === "lists" ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* List panel */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold text-foreground">Distribution Lists</h2>
              <Button size="sm" onClick={() => setShowCreateList(true)} className="gap-2 bg-teal-600 hover:bg-teal-700">
                <Plus className="h-4 w-4" />
                New List
              </Button>
            </div>

            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>List Name</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="w-24 text-center">Members</TableHead>
                    <TableHead className="w-24 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingLists ? (
                    Array.from({ length: 3 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                      </TableRow>
                    ))
                  ) : lists?.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center py-6 text-muted-foreground">
                        No distribution lists created yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    lists?.map((list) => (
                      <TableRow
                        key={list.id}
                        onClick={() => setSelectedList(list)}
                        className={`cursor-pointer transition-colors ${
                          selectedList?.id === list.id ? "bg-teal-500/10 hover:bg-teal-500/15" : ""
                        }`}
                      >
                        <TableCell className="font-semibold text-teal-300 flex items-center gap-2">
                          <Users className="h-4 w-4 text-muted-foreground" />
                          {list.name}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {list.description ?? "No description"}
                        </TableCell>
                        <TableCell className="text-center font-mono font-medium text-sm">
                          {list.member_count}
                        </TableCell>
                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => {
                              if (confirm(`Are you sure you want to delete list "${list.name}"? This deletes all members.`)) {
                                deleteListMutation.mutate(list.id);
                              }
                            }}
                            className="h-8 w-8 text-muted-foreground hover:text-red-400"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
          </div>

          {/* Members Panel */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-foreground">
              {selectedList ? `Members: ${selectedList.name}` : "Select a list"}
            </h2>

            {selectedList ? (
              <div className="space-y-4">
                {/* Add member form */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-bold flex items-center gap-1.5">
                      <Plus className="h-4 w-4" /> Add Recipient
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {memberError && (
                      <div className="text-xs border border-red-500/20 bg-red-500/10 text-red-400 p-2 rounded">
                        {memberError}
                      </div>
                    )}
                    <div className="space-y-1">
                      <Label htmlFor="mem-email" className="text-xs">Email Address</Label>
                      <Input
                        id="mem-email"
                        placeholder="john.doe@company.local"
                        value={memberEmail}
                        onChange={(e) => setMemberEmail(e.target.value)}
                        className="h-9"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="mem-name" className="text-xs">Display Name (optional)</Label>
                      <Input
                        id="mem-name"
                        placeholder="John Doe"
                        value={memberName}
                        onChange={(e) => setMemberName(e.target.value)}
                        className="h-9"
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={() => addMemberMutation.mutate({ listId: selectedList.id, email: memberEmail, name: memberName || undefined })}
                      disabled={!memberEmail || addMemberMutation.isPending}
                      className="w-full mt-2 bg-teal-600 hover:bg-teal-700 h-9"
                    >
                      {addMemberMutation.isPending && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
                      Add to List
                    </Button>
                  </CardContent>
                </Card>

                {/* Members list */}
                <Card className="max-h-[350px] overflow-y-auto">
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader className="sticky top-0 bg-slate-900 z-10">
                        <TableRow>
                          <TableHead className="py-2 text-xs">Recipient</TableHead>
                          <TableHead className="py-2 text-right w-16"></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {loadingMembers ? (
                          Array.from({ length: 3 }).map((_, i) => (
                            <TableRow key={i}>
                              <TableCell><Skeleton className="h-3 w-full" /></TableCell>
                              <TableCell><Skeleton className="h-3 w-full" /></TableCell>
                            </TableRow>
                          ))
                        ) : members?.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={2} className="text-center py-4 text-xs text-muted-foreground">
                              No members in this list.
                            </TableCell>
                          </TableRow>
                        ) : (
                          members?.map((member) => (
                            <TableRow key={member.id}>
                              <TableCell className="py-2">
                                <div>
                                  <p className="text-sm font-medium text-foreground">{member.name ?? "—"}</p>
                                  <p className="text-xs text-muted-foreground font-mono">{member.email}</p>
                                </div>
                              </TableCell>
                              <TableCell className="py-2 text-right">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={() =>
                                    removeMemberMutation.mutate({ listId: selectedList.id, email: member.email })
                                  }
                                  className="h-7 w-7 text-muted-foreground hover:text-red-400"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card className="flex flex-col items-center justify-center p-6 text-center text-muted-foreground border-dashed">
                <Info className="h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">Select a distribution list on the left to manage its members.</p>
              </Card>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-foreground">Event Trigger Mappings</h2>
            <Button size="sm" onClick={() => {
              if (lists && lists.length > 0) {
                setMappingListId(lists[0].id);
              }
              setShowCreateMapping(true);
            }} disabled={!lists || lists.length === 0} className="gap-2 bg-teal-600 hover:bg-teal-700">
              <Plus className="h-4 w-4" />
              Add Mapping
            </Button>
          </div>

          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Event Type</TableHead>
                  <TableHead className="w-12 text-center"></TableHead>
                  <TableHead>Target Distribution List</TableHead>
                  <TableHead className="w-32 text-center">In-App Alert (All)</TableHead>
                  <TableHead className="w-24 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loadingMappings ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                      <TableCell></TableCell>
                      <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-full" /></TableCell>
                    </TableRow>
                  ))
                ) : mappings?.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-6 text-muted-foreground">
                      No trigger mappings configured.
                    </TableCell>
                  </TableRow>
                ) : (
                  mappings?.map((mapping) => (
                    <TableRow key={mapping.id}>
                      <TableCell className="font-semibold text-foreground text-sm">
                        {EVENT_TYPES.find((e) => e.value === mapping.event_type)?.label ?? mapping.event_type}
                      </TableCell>
                      <TableCell className="text-center">
                        <ArrowRight className="h-4 w-4 text-muted-foreground" />
                      </TableCell>
                      <TableCell className="font-medium text-teal-300 text-sm">
                        {mapping.list_name}
                      </TableCell>
                      <TableCell className="text-center">
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                          mapping.notify_all_users ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/30" : "bg-white/5 text-muted-foreground"
                        }`}>
                          {mapping.notify_all_users ? "Yes" : "No"}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            if (confirm(`Remove mapping for event "${mapping.event_type}"?`)) {
                              deleteMappingMutation.mutate(mapping.id);
                            }
                          }}
                          className="h-8 w-8 text-muted-foreground hover:text-red-400"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}

      {/* Dialog for creating a list */}
      <Dialog open={showCreateList} onOpenChange={setShowCreateList}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Distribution List</DialogTitle>
            <DialogDescription>Create a new group for email notifications.</DialogDescription>
          </DialogHeader>

          {listError && (
            <div className="border border-red-500/20 bg-red-500/10 text-red-400 p-3 rounded-lg text-sm">
              {listError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="list-name">List Name</Label>
              <Input
                id="list-name"
                placeholder="Engineering Team"
                value={listName}
                onChange={(e) => setListName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="list-desc">Description (optional)</Label>
              <Input
                id="list-desc"
                placeholder="Recipients for technical and standard revisions"
                value={listDesc}
                onChange={(e) => setListDesc(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreateList(false); setListError(null); }}>
              Cancel
            </Button>
            <Button
              onClick={() => createListMutation.mutate({ name: listName, description: listDesc || undefined })}
              disabled={createListMutation.isPending || !listName}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {createListMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
              Create List
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog for creating a trigger mapping */}
      <Dialog open={showCreateMapping} onOpenChange={setShowCreateMapping}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Trigger Mapping</DialogTitle>
            <DialogDescription>Map a system lifecycle event to a distribution list.</DialogDescription>
          </DialogHeader>

          {mappingError && (
            <div className="border border-red-500/20 bg-red-500/10 text-red-400 p-3 rounded-lg text-sm">
              {mappingError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="map-event">Event Type</Label>
              <select
                id="map-event"
                value={mappingEvent}
                onChange={(e) => setMappingEvent(e.target.value)}
                className="flex h-10 w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {EVENT_TYPES.map((e) => (
                  <option key={e.value} value={e.value}>{e.label}</option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="map-list">Target Distribution List</Label>
              <select
                id="map-list"
                value={mappingListId}
                onChange={(e) => setMappingListId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-white/10 bg-slate-950 px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {lists?.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center space-x-2 pt-2">
              <input
                type="checkbox"
                id="map-notify-all"
                checked={mappingNotifyAll}
                onChange={(e) => setMappingNotifyAll(e.target.checked)}
                className="h-4 w-4 rounded border-white/10 bg-slate-950 text-teal-600 focus:ring-teal-500 focus:ring-offset-slate-900"
              />
              <Label htmlFor="map-notify-all" className="text-sm cursor-pointer select-none">
                Also broadcast in-app notification to all users
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreateMapping(false); setMappingError(null); }}>
              Cancel
            </Button>
            <Button
              onClick={() => createMappingMutation.mutate({ event_type: mappingEvent, list_id: mappingListId, notify_all_users: mappingNotifyAll })}
              disabled={createMappingMutation.isPending || !mappingListId}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {createMappingMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
              Save Mapping
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
