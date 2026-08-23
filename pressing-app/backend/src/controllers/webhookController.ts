import { Request, Response } from "express";
import { prisma } from "../lib/prisma";
import { markPaymentIntentFailed, markPaymentIntentSucceeded } from "../services/paymentIntentService";

/**
 * Orange Money calls notif_url with a payload including order_id — which we
 * set to our PaymentIntent id when creating the web payment session (see
 * mobileMoneyProviders.ts: OrangeMoneyProvider.requestPayment). No public
 * webhook signature scheme is documented for this API, so
 * ORANGE_MONEY_WEBHOOK_SECRET (appended by us as ?key=... on notif_url) is
 * required in production; requests without a matching key are rejected.
 */
export async function orangeMoneyWebhook(req: Request, res: Response) {
  const expected = process.env.ORANGE_MONEY_WEBHOOK_SECRET;
  if (expected && req.query.key !== expected) {
    return res.status(401).json({ error: "Invalid webhook key" });
  }
  const { order_id: intentId, status } = req.body as { order_id?: string; status?: string };
  if (!intentId) return res.status(400).json({ error: "Missing order_id" });

  if (status === "SUCCESS") await markPaymentIntentSucceeded(intentId);
  else if (status === "FAILED" || status === "EXPIRED") await markPaymentIntentFailed(intentId, status);

  res.json({ received: true });
}

/**
 * MTN MoMo's Collections "requesttopay" flow is poll-driven by default (see
 * checkPaymentIntent, which calls GET .../requesttopay/{id}) rather than
 * webhook-driven. This endpoint exists for the optional callback some MTN
 * subscriptions support; same shared-secret convention as Orange's.
 */
export async function mtnMomoWebhook(req: Request, res: Response) {
  const expected = process.env.MTN_MOMO_WEBHOOK_SECRET;
  if (expected && req.query.key !== expected) {
    return res.status(401).json({ error: "Invalid webhook key" });
  }
  const { referenceId, status } = req.body as { referenceId?: string; status?: string };
  if (!referenceId) return res.status(400).json({ error: "Missing referenceId" });

  const intent = await prisma.paymentIntent.findFirst({ where: { providerReference: referenceId } });
  if (!intent) return res.status(404).json({ error: "Unknown payment intent" });

  if (status === "SUCCESSFUL") await markPaymentIntentSucceeded(intent.id);
  else if (status === "FAILED") await markPaymentIntentFailed(intent.id, status);

  res.json({ received: true });
}
