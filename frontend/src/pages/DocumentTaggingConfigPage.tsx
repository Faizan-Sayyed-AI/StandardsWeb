import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tag, Save, Loader2, Info } from "lucide-react";
import { getDocumentTaggingConfig, updateDocumentTaggingConfig } from "@/api/documentTagging";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function DocumentTaggingConfigPage() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const { data: config, isLoading } = useQuery({
    queryKey: ["document-tagging-config"],
    queryFn: getDocumentTaggingConfig,
  });

  // API key is intentionally excluded here — see SMTPConfigPage.tsx for why
  // preloading a masked secret into an editable field is unsafe.
  useEffect(() => {
    if (config) {
      setUrl(config.DOCUMENT_TAGGING_URL);
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: updateDocumentTaggingConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document-tagging-config"] });
      setSuccessMsg("Document tagging configuration saved successfully!");
      setErrorMsg(null);
      setApiKey("");
      setTimeout(() => setSuccessMsg(null), 5000);
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail ?? "Failed to save configuration");
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
          <Tag className="h-6 w-6 text-teal-400" />
          Document Tagging
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure the external AI service that tags uploaded documents for search.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tagging Service Configuration</CardTitle>
          <CardDescription>
            Every document upload is sent here in the background; the response is stored and made searchable.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4 py-4">
              <div className="h-4 bg-foreground/5 rounded w-1/4 animate-pulse"></div>
              <div className="h-10 bg-foreground/5 rounded animate-pulse"></div>
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

              <div className="space-y-1.5">
                <Label htmlFor="tagging-url">Tagging Service URL *</Label>
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
          <p className="font-semibold">If left unconfigured</p>
          <p className="opacity-90 mt-0.5">
            Document uploads still work normally — tagging is simply skipped until a URL is set here.
          </p>
        </div>
      </div>
    </div>
  );
}
