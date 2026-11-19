import { QueryError } from "@/components/QueryError";
import { apiErrorMessage } from "@/lib/apiError";
import { ConfirmationDialog, type Confirmation } from "@/components/ConfirmationDialog";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, Plus, Loader2, UserCheck, UserX, Shield, Edit2
} from "lucide-react";
import { listUsers, createUser, updateUser, type User, type UserUpdatePayload } from "@/api/users";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";

export function UsersPage() {
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [showEditRole, setShowEditRole] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // Form states
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "manager" | "viewer">("viewer");
  const [editRole, setEditRole] = useState<"admin" | "manager" | "viewer">("viewer");
  const [formError, setFormError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["users", page],
    queryFn: () => listUsers(page, 20),
  });

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowCreate(false);
      setUsername("");
      setEmail("");
      setPassword("");
      setRole("viewer");
      setFormError(null);
    },
    onError: (err: unknown) => {
      setFormError(apiErrorMessage(err, "Failed to create user"));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UserUpdatePayload }) => updateUser(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowEditRole(false);
      setSelectedUser(null);
    },
  });

  const handleDeactivateToggle = (user: User) => {
    const action = user.is_active ? "deactivate" : "reactivate";
    setConfirmation({
      action: action === "deactivate" ? "Deactivate account" : "Reactivate account",
      description: `Are you sure you want to ${action} user "${user.username}"?`,
      onConfirm: () => {
        updateMutation.mutate({
          id: user.id,
          payload: { is_active: !user.is_active },
        });
      },
    });
  };

  const handleOpenEditRole = (user: User) => {
    setSelectedUser(user);
    setEditRole(user.role);
    setShowEditRole(true);
  };

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  const RoleBadge = ({ userRole }: { userRole: string }) => {
    switch (userRole) {
      case "admin":
        return (
          <Badge className="bg-danger-soft border border-danger-line text-danger capitalize hover:bg-danger-soft">
            {userRole}
          </Badge>
        );
      case "manager":
        return (
          <Badge className="bg-success-soft border border-success-line text-success capitalize hover:bg-success-soft">
            {userRole}
          </Badge>
        );
      default:
        return (
          <Badge className="bg-foreground/5 border border-border text-muted-foreground capitalize hover:bg-muted">
            {userRole}
          </Badge>
        );
    }
  };

  if (isError && !data) return <QueryError subject="users" onRetry={refetch} />;

  return (
    <div className="space-y-6">
      <ConfirmationDialog request={confirmation} onClose={() => setConfirmation(null)} />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            Users
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total} user accounts configured` : "Loading…"}
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="gap-2 ">
          <Plus className="h-4 w-4" />
          Create user
        </Button>
      </div>

      {/* Users table */}
      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead className="w-32">Role</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-44">Last Login</TableHead>
              <TableHead className="w-44">Created Date</TableHead>
              <TableHead className="w-32 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              : data?.items.map((u) => (
                  <TableRow key={u.id} className={u.is_active ? "" : "opacity-60"}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-foreground text-sm">{u.username}</p>
                        <p className="text-xs text-muted-foreground">{u.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <RoleBadge userRole={u.role} />
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${
                        u.is_active ? "bg-success-soft text-success" : "bg-danger-soft text-danger"
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${u.is_active ? "bg-success" : "bg-danger"}`} />
                        {u.is_active ? "Active" : "Deactivated"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {u.last_login ? formatDate(u.last_login) : "Never"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">{formatDate(u.created_at)}</span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        {/* Edit role */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Edit role"
                          onClick={() => handleOpenEditRole(u)}
                          className="h-7 w-7 text-muted-foreground hover:text-brand"
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                        {/* Toggle active status */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title={u.is_active ? "Deactivate user" : "Reactivate user"}
                          onClick={() => handleDeactivateToggle(u)}
                          disabled={updateMutation.isPending}
                          className={`h-7 w-7 text-muted-foreground ${
                            u.is_active ? "hover:text-danger" : "hover:text-success"
                          }`}
                        >
                          {u.is_active ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </Card>

      {/* Create user Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-brand" />
              Create user
            </DialogTitle>
            <DialogDescription>
              Add a new user to the Standards tracking system library.
            </DialogDescription>
          </DialogHeader>

          {formError && (
            <div className="rounded-lg border border-danger-line bg-danger-soft px-4 py-2 text-sm text-danger">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="create-username">Username</Label>
              <Input
                id="create-username"
                placeholder="johndoe"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="create-email">Email address</Label>
              <Input
                id="create-email"
                type="email"
                placeholder="john.doe@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="create-password">Initial Password</Label>
              <Input
                id="create-password"
                type="password"
                placeholder="********"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>System Role</Label>
              <div className="flex gap-2">
                {(["viewer", "manager", "admin"] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRole(r)}
                    className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors capitalize ${
                      role === r
                        ? "border-brand-line bg-brand-soft text-brand"
                        : "border-border text-muted-foreground hover:border-border-strong"
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setFormError(null); }}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                createMutation.mutate({
                  username: username.trim(),
                  email: email.trim(),
                  password,
                  role,
                })
              }
              disabled={createMutation.isPending || !username || !email || !password}
              className="gap-2 "
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit role Dialog */}
      <Dialog open={showEditRole} onOpenChange={setShowEditRole}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-brand" />
              Edit User Role
            </DialogTitle>
            <DialogDescription>
              Modify system roles and access levels for user "{selectedUser?.username}".
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>System Role</Label>
              <div className="flex gap-2">
                {(["viewer", "manager", "admin"] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setEditRole(r)}
                    className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors capitalize ${
                      editRole === r
                        ? "border-brand-line bg-brand-soft text-brand"
                        : "border-border text-muted-foreground hover:border-border-strong"
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowEditRole(false); setSelectedUser(null); }}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (selectedUser) {
                  updateMutation.mutate({
                    id: selectedUser.id,
                    payload: { role: editRole },
                  });
                }
              }}
              disabled={updateMutation.isPending}
              className="gap-2 "
            >
              {updateMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
