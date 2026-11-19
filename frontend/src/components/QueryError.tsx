import { Button } from "@/components/ui/button";

export function QueryError({ subject, onRetry }: { subject: string; onRetry: () => void }) {
  return (
    <section role="alert" className="space-y-3 rounded-lg border bg-card p-5">
      <h2 className="font-semibold">Could not load {subject}</h2>
      <Button variant="outline" onClick={onRetry}>Try again</Button>
    </section>
  );
}
