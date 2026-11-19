import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export interface Confirmation {
  action: string;
  description: string;
  onConfirm: () => void;
}

export function ConfirmationDialog({ request, onClose }: { request: Confirmation | null; onClose: () => void }) {
  return (
    <Dialog open={!!request} onOpenChange={open => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{request?.action}</DialogTitle>
          <DialogDescription>{request?.description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => { request?.onConfirm(); onClose(); }}>{request?.action}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
