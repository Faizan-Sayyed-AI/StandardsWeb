import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, Plus, Loader2, UserCheck, UserX, Shield, Edit2, ShieldAlert
} from "lucide-react";
import { listUsers, createUser, updateUser, type User } from "@/api/users";
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

  const { data, isLoading } = useQuery({
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
    onError: (err: any) => {
      setFormError(err?.response?.data?.detail ?? "Failed to create user");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => updateUser(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setShowEditRole(false);
      setSelectedUser(null);
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail ?? "Failed to update user");
    },
  });

  const handleDeactivateToggle = (user: User) => {
    const action = user.is_active ? "deactivate" : "reactivate";
    if (confirm(`Are you sure you want to ${action} user "${user.username}"?`)) {
      updateMutation.mutate({
        id: user.id,
        payload: { is_active: !user.is_active },
      });
    }
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
          <Badge className="bg-red-500/15 border border-red-500/30 text-red-400 capitalize hover:bg-red-500/20">
            {userRole}
          </Badge>
        );
      case "manager":
        return (
          <Badge className="bg-teal-500/15 border border-teal-500/30 text-teal-300 capitalize hover:bg-teal-500/20">
            {userRole}
          </Badge>
        );
      default:
        return (
          <Badge className="bg-slate-500/15 border border-slate-500/30 text-slate-400 capitalize hover:bg-slate-500/20">
            {userRole}
          </Badge>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Users className="h-6 w-6 text-indigo-400" />
            User Management
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total} user accounts configured` : "Loading…"}
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)} className="gap-2 bg-indigo-600 hover:bg-indigo-700">
          <Plus className="h-4 w-4" />
          Create User
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
                        u.is_active ? "bg-teal-500/10 text-teal-400" : "bg-red-500/10 text-red-400"
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${u.is_active ? "bg-teal-400" : "bg-red-400"}`} />
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
                        {/* Edit Role */}
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Edit role"
                          onClick={() => handleOpenEditRole(u)}
                          className="h-7 w-7 text-muted-foreground hover:text-indigo-400"
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
                            u.is_active ? "hover:text-red-400" : "hover:text-teal-400"
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
          <div className="flex items-center justify-end gap-2 border-t border-white/8 px-6 py-3">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              Next
            </Button>
          </div>
        )}
      </Card>

      {/* Create User Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="h-5 w-5 text-indigo-400" />
              Create User Account
            </DialogTitle>
            <DialogDescription>
              Add a new user to the Standards tracking system library.
            </DialogDescription>
          </DialogHeader>

          {formError && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400">
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
              <Label htmlFor="create-email">Email Address</Label>
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
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
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
              className="gap-2 bg-indigo-600 hover:bg-indigo-700"
            >
              {createMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Create Account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Role Dialog */}
      <Dialog open={showEditRole} onOpenChange={setShowEditRole}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-indigo-400" />
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
                        ? "border-indigo-500/40 bg-indigo-600/20 text-indigo-300"
                        : "border-white/10 text-muted-foreground hover:border-white/20"
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
              className="gap-2 bg-indigo-600 hover:bg-indigo-700"
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
