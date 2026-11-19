import { QueryError } from "@/components/QueryError";
import { apiErrorMessage } from "@/lib/apiError";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, Loader2, Info } from "lucide-react";
import { getDocumentTaggingConfig, updateDocumentTaggingConfig, type DocumentTaggingConfig } from "@/api/documentTagging";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function DocumentTaggingConfigPage() {
  const { data, isError, refetch } = useQuery({ queryKey: ["document-tagging-config"], queryFn: getDocumentTaggingConfig });
  if (isError && !data) return <QueryError subject="settings" onRetry={refetch} />;
  if (!data) return <p role="status">Loading settings…</p>;
  return <SettingsForm config={data} />;
}

function SettingsForm({ config }: { config: DocumentTaggingConfig }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState(config.DOCUMENT_TAGGING_URL);
  const [apiKey, setApiKey] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: updateDocumentTaggingConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document-tagging-config"] });
      setSuccessMsg("Document tagging settings saved.");
      setErrorMsg(null);
      setApiKey("");
      setTimeout(() => setSuccessMsg(null), 5000);
    },
    onError: (err: unknown) => {
      setErrorMsg(apiErrorMessage(err, "Failed to save configuration"));
      setSuccessMsg(null);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) {
      setErrorMsg("Please enter the tagging service URL.");
      return;
    }
    saveMutation.mutate({
      DOCUMENT_TAGGING_URL: url,
      DOCUMENT_TAGGING_API_KEY: apiKey,
    });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          Tagging settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure the external AI service that tags uploaded documents for search.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tagging service</CardTitle>
          <CardDescription>
            Every document upload is sent here in the background; the response is stored and made searchable.
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

              <div className="space-y-1.5">
                <Label htmlFor="tagging-url">Service URL *</Label>
                <Input
                  id="tagging-url"
                  placeholder="https://your-tagging-service.example.com/process-document"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="tagging-key">API Key (optional)</Label>
                <Input
                  id="tagging-key"
                  type="password"
                  placeholder={config?.DOCUMENT_TAGGING_API_KEY ? "Leave blank to keep current key" : "Enter API key"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
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
          <p className="font-semibold">If left unconfigured</p>
          <p className="opacity-90 mt-0.5">
            Document uploads still work normally — tagging is simply skipped until a URL is set here.
          </p>
        </div>
      </div>
    </div>
  );
}
