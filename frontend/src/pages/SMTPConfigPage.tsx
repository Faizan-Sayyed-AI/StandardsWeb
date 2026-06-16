import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings, Save, Server, Loader2, Info } from "lucide-react";
import { getSMTPConfig, updateSMTPConfig, type SMTPConfig } from "@/api/distributionLists";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SMTPConfigPage() {
  const qc = useQueryClient();
  const [host, setHost] = useState("");
  const [port, setPort] = useState(1025);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [useTls, setUseTls] = useState(false);
  const [fromAddress, setFromAddress] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const { data: config, isLoading } = useQuery({
    queryKey: ["smtp-config"],
    queryFn: getSMTPConfig,
  });

  // Populate state on load
  useEffect(() => {
    if (config) {
      setHost(config.SMTP_HOST);
      setPort(config.SMTP_PORT);
      setUser(config.SMTP_USER);
      setPassword(config.SMTP_PASSWORD ?? "");
      setUseTls(config.SMTP_USE_TLS);
      setFromAddress(config.SMTP_FROM_ADDRESS);
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: updateSMTPConfig,
    onSuccess: (newConfig) => {
      qc.invalidateQueries({ queryKey: ["smtp-config"] });
      setSuccessMsg("SMTP configuration saved successfully!");
      setErrorMsg(null);
      setPassword(newConfig.SMTP_PASSWORD ?? "");
      setTimeout(() => setSuccessMsg(null), 5000);
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to save SMTP configuration");
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
          <Settings className="h-6 w-6 text-teal-400" />
          SMTP Server Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure the SMTP mail server used by background workers to deliver standard lifecycle alerts.
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
          {isLoading ? (
            <div className="space-y-4 py-4">
              <div className="h-4 bg-white/5 rounded w-1/4 animate-pulse"></div>
              <div className="h-10 bg-white/5 rounded animate-pulse"></div>
              <div className="h-4 bg-white/5 rounded w-1/3 animate-pulse"></div>
              <div className="h-10 bg-white/5 rounded animate-pulse"></div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {errorMsg && (
                <div className="border border-red-500/20 bg-red-500/10 text-red-400 p-3 rounded-lg text-sm">
                  {errorMsg}
                </div>
              )}
              {successMsg && (
                <div className="border border-teal-500/20 bg-teal-500/10 text-teal-300 p-3 rounded-lg text-sm">
                  {successMsg}
                </div>
              )}

              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2 space-y-1.5">
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
                <Label htmlFor="smtp-from">From Email Address *</Label>
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
                  placeholder={config?.SMTP_PASSWORD ? "******** (masked)" : "Enter password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <div className="flex items-center space-x-2 pt-2 border-t border-white/5 mt-4">
                <input
                  type="checkbox"
                  id="smtp-tls"
                  checked={useTls}
                  onChange={(e) => setUseTls(e.target.checked)}
                  className="h-4 w-4 rounded border-white/10 bg-slate-950 text-teal-600 focus:ring-teal-500 focus:ring-offset-slate-900"
                />
                <Label htmlFor="smtp-tls" className="text-sm cursor-pointer select-none">
                  Use Secure TLS/STARTTLS Connection
                </Label>
              </div>

              <div className="flex justify-end pt-4">
                <Button
                  type="submit"
                  disabled={saveMutation.isPending}
                  className="gap-2 bg-teal-600 hover:bg-teal-700"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save Configuration
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      <div className="rounded-lg border border-teal-500/10 bg-teal-500/5 px-4 py-3 flex gap-3 text-sm text-teal-300">
        <Info className="h-5 w-5 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold">Dynamic Updates</p>
          <p className="opacity-90 mt-0.5">
            SMTP configuration updates are stored immediately in the database and applied on all subsequent transactional email deliveries without worker container restarts.
          </p>
        </div>
      </div>
    </div>
  );
}
