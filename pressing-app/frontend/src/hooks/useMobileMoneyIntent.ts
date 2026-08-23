import { useEffect, useRef, useState } from "react";
import type { AxiosInstance } from "axios";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";

export interface PaymentIntentState {
  id: string;
  status: "PENDING" | "SUCCESS" | "FAILED";
  simulated: boolean;
  failureReason?: string | null;
  redirectUrl?: string;
}

/**
 * Drives the initiate → poll → settle lifecycle for a mobile money payment,
 * shared by the staff order page and the customer portal order page.
 * Polling stops as soon as the intent leaves PENDING (SUCCESS or FAILED).
 * Callers pass a `pollBase` matching which side initiated it: staff intents
 * are polled at /payment-intents/:id, portal (customer) ones at
 * /portal/payment-intents/:id — mirroring the backend's separate staff vs.
 * customer routes for the same underlying PaymentIntent.
 */
export function useMobileMoneyIntent(onSuccess: () => void, client: AxiosInstance = api) {
  const [intent, setIntent] = useState<PaymentIntentState | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(pollRef.current), []);

  function reset() {
    clearTimeout(pollRef.current);
    setIntent(null);
  }

  function schedulePoll(pollUrl: string) {
    pollRef.current = setTimeout(async () => {
      try {
        const res = await client.get<PaymentIntentState>(pollUrl);
        setIntent((prev) => ({ ...res.data, redirectUrl: prev?.redirectUrl }));
        if (res.data.status === "PENDING") {
          schedulePoll(pollUrl);
        } else if (res.data.status === "SUCCESS") {
          toast.success("Paiement confirmé");
          onSuccess();
        }
      } catch {
        schedulePoll(pollUrl);
      }
    }, 2000);
  }

  /**
   * `pollBase` is the poll endpoint's path without the intent id (e.g.
   * "/payment-intents" for staff, "/portal/payment-intents" for the
   * customer portal) — the id is only known once `initiate` resolves.
   */
  async function initiate(initiateUrl: string, pollBase: string, payload: Record<string, unknown>) {
    try {
      const res = await client.post<PaymentIntentState>(initiateUrl, payload);
      setIntent(res.data);
      if (res.data.status === "PENDING") schedulePoll(`${pollBase}/${res.data.id}`);
      else if (res.data.status === "SUCCESS") onSuccess();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return { intent, initiate, reset };
}
