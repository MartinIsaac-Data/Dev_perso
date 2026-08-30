import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { PaymentIntentState } from "@/hooks/useMobileMoneyIntent";

export function MobileMoneyStatus({
  intent,
  onClose,
}: {
  intent: PaymentIntentState;
  onClose: () => void;
}) {
  return (
    <div className="space-y-3 py-2 text-center">
      {intent.simulated && (
        <Badge tone="warning" className="mx-auto">
          Mode simulation — aucun vrai débit
        </Badge>
      )}
      {intent.status === "PENDING" && (
        <>
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-sm font-medium">En attente de confirmation...</p>
          <p className="text-xs text-muted-foreground">
            Validez la demande de paiement reçue sur votre téléphone.
          </p>
          {intent.redirectUrl && (
            <a
              href={intent.redirectUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-block text-sm text-primary underline"
            >
              Ouvrir la page de paiement Orange Money
            </a>
          )}
        </>
      )}
      {intent.status === "SUCCESS" && <p className="text-sm font-medium text-success">Paiement confirmé !</p>}
      {intent.status === "FAILED" && (
        <>
          <p className="text-sm font-medium text-destructive">Paiement échoué</p>
          {intent.failureReason && <p className="text-xs text-muted-foreground">{intent.failureReason}</p>}
        </>
      )}
      {intent.status !== "PENDING" && (
        <Button variant="outline" onClick={onClose} className="mt-2">
          Fermer
        </Button>
      )}
    </div>
  );
}
