import { QueryError } from "@/components/QueryError";
import { apiErrorMessage } from "@/lib/apiError";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, Server, Loader2, Info } from "lucide-react";
import { getSMTPConfig, updateSMTPConfig, type SMTPConfig } from "@/api/distributionLists";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SMTPConfigPage() {
  const { data, isError, refetch } = useQuery({ queryKey: ["smtp-config"], queryFn: getSMTPConfig });
  if (isError && !data) return <QueryError subject="settings" onRetry={refetch} />;
  if (!data) return <p role="status">Loading settings…</p>;
  return <SettingsForm config={data} />;
}

function SettingsForm({ config }: { config: SMTPConfig }) {
  const qc = useQueryClient();
  const [host, setHost] = useState(config.SMTP_HOST);
  const [port, setPort] = useState(config.SMTP_PORT);
  const [user, setUser] = useState(config.SMTP_USER);
  const [password, setPassword] = useState("");
  const [useTls, setUseTls] = useState(config.SMTP_USE_TLS);
  const [fromAddress, setFromAddress] = useState(config.SMTP_FROM_ADDRESS);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: updateSMTPConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["smtp-config"] });
      setSuccessMsg("SMTP settings saved.");
      setErrorMsg(null);
      setPassword("");
      setTimeout(() => setSuccessMsg(null), 5000);
    },
    onError: (err: unknown) => {
      setErrorMsg(apiErrorMessage(err, "Failed to save SMTP configuration"));
      setSuccessMsg(null);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!host || !port || !fromAddress) {
      setErrorMsg("Please fill in all required fields (Host, Port, From Address).");
      return;
    }
    saveMutation.mutate({
      SMTP_HOST: host,
      SMTP_PORT: port,
      SMTP_USER: user,
      SMTP_PASSWORD: password,
      SMTP_USE_TLS: useTls,
      SMTP_FROM_ADDRESS: fromAddress
    });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          SMTP settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Set the mail server used to send standards alerts.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-5 w-5 text-muted-foreground" />
            Mail Server Configuration
          </CardTitle>
          <CardDescription>
            Dev environment defaults to MailHog catch-all on port 1025.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
              {errorMsg && (
                <div className="border border-danger-line bg-danger-soft text-danger p-3 rounded-lg text-sm">
                  {errorMsg}
                </div>
              )}
              {successMsg && (
                <div className="border border-success-line bg-success-soft text-success p-3 rounded-lg text-sm">
                  {successMsg}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 space-y-1.5">
                  <Label htmlFor="smtp-host">SMTP Host *</Label>
                  <Input
                    id="smtp-host"
                    placeholder="localhost"
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-port">SMTP Port *</Label>
                  <Input
                    id="smtp-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={port}
                    onChange={(e) => setPort(parseInt(e.target.value, 10) || 1025)}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="smtp-from">From Email address *</Label>
                <Input
                  id="smtp-from"
                  placeholder="ists@local"
                  value={fromAddress}
                  onChange={(e) => setFromAddress(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="smtp-user">SMTP Username (optional)</Label>
                <Input
                  id="smtp-user"
                  placeholder="e.g. apikey or user"
                  value={user}
                  onChange={(e) => setUser(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="smtp-pass">SMTP Password (optional)</Label>
                <Input
                  id="smtp-pass"
                  type="password"
                  placeholder={config?.SMTP_PASSWORD ? "Leave blank to keep current password" : "Enter password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <div className="flex items-center space-x-2 pt-2 border-t border-border mt-4">
                <input
                  type="checkbox"
                  id="smtp-tls"
                  checked={useTls}
                  onChange={(e) => setUseTls(e.target.checked)}
                  className="h-4 w-4 rounded border-input bg-background text-success focus:ring-success focus:ring-offset-background"
                />
                <Label htmlFor="smtp-tls" className="text-sm cursor-pointer select-none">
                  Use Secure TLS/STARTTLS Connection
                </Label>
              </div>

              <div className="flex justify-end pt-4">
                <Button
                  type="submit"
                  disabled={saveMutation.isPending}
                  className="gap-2"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save settings
                </Button>
              </div>
            </form>
        </CardContent>
      </Card>

      <div className="rounded-lg border border-success-line bg-success-soft px-4 py-3 flex gap-3 text-sm text-success">
        <Info className="h-5 w-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold">When settings take effect</p>
          <p className="opacity-90 mt-0.5">
            Saved settings apply to the next email delivery.
          </p>
        </div>
      </div>
    </div>
  );
}
