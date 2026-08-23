import { MobileMoneyProviderType, PaymentIntent } from "@prisma/client";
import { prisma } from "../lib/prisma";
import { ApiError } from "../middleware/errorHandler";
import { resolveMobileMoneyProvider } from "./mobileMoneyProviders";
import { isSimulationMode } from "./settingsService";
import { computeBalance, computePaymentStatus } from "./pricingService";
import { notifyOrderStatusChange } from "./notificationService";
import { assertBranchAccess } from "../middleware/auth";

export interface InitiateResult {
  intent: PaymentIntent;
  redirectUrl?: string;
}

/**
 * Starts a mobile money charge for an order's remaining balance (or a
 * partial amount). Mirrors POST /orders/:id/payments (cash) but the money
 * doesn't land immediately — the PaymentIntent stays PENDING until the
 * provider confirms it, via checkPaymentIntent (polling) or a webhook.
 */
export async function initiatePaymentIntent(params: {
  orderId: string;
  provider: MobileMoneyProviderType;
  phone: string;
  amount?: number;
  initiatedById?: string;
}): Promise<InitiateResult> {
  const order = await prisma.order.findUnique({ where: { id: params.orderId } });
  if (!order) throw new ApiError(404, "Order not found");

  const amount = params.amount ?? Number(order.balance);
  if (amount <= 0) throw new ApiError(400, "Cette commande n'a aucun solde à régler");
  if (amount > Number(order.balance) + 0.01) throw new ApiError(400, "Le montant dépasse le solde de la commande");

  const simulate = await isSimulationMode("payments");
  const { provider, simulated } = resolveMobileMoneyProvider(params.provider, simulate);

  const intent = await prisma.paymentIntent.create({
    data: {
      orderId: order.id,
      customerId: order.customerId,
      provider: params.provider,
      phone: params.phone,
      amount,
      status: "PENDING",
      simulated,
      initiatedById: params.initiatedById,
    },
  });

  try {
    const result = await provider.requestPayment({
      phone: params.phone,
      amount,
      reference: intent.id,
      description: `Commande ${order.orderNumber}`,
    });

    const updated = await prisma.paymentIntent.update({
      where: { id: intent.id },
      data:
        result.status === "FAILED"
          ? { status: "FAILED", failureReason: result.failureReason }
          : { providerReference: result.providerReference },
    });

    return { intent: updated, redirectUrl: result.redirectUrl };
  } catch (err) {
    const updated = await prisma.paymentIntent.update({
      where: { id: intent.id },
      data: { status: "FAILED", failureReason: (err as Error).message },
    });
    return { intent: updated };
  }
}

/**
 * Polls the provider for the latest status and finalizes the intent if it
 * has resolved. Safe to call repeatedly — already-finalized intents are
 * returned as-is without contacting the provider again.
 */
export async function checkPaymentIntent(intentId: string): Promise<PaymentIntent> {
  const intent = await prisma.paymentIntent.findUnique({ where: { id: intentId } });
  if (!intent) throw new ApiError(404, "Payment intent not found");
  if (intent.status !== "PENDING") return intent;
  if (!intent.providerReference) return intent;

  const simulate = await isSimulationMode("payments");
  const { provider } = resolveMobileMoneyProvider(intent.provider, simulate || intent.simulated);
  const result = await provider.checkStatus(intent.providerReference);

  if (result.status === "SUCCESS") return finalizeSuccess(intent.id);
  if (result.status === "FAILED") {
    return prisma.paymentIntent.update({
      where: { id: intent.id },
      data: { status: "FAILED", failureReason: result.failureReason },
    });
  }
  return intent;
}

/**
 * Marks a PENDING intent as SUCCESS from an external signal (webhook) and
 * finalizes it. Distinct from checkPaymentIntent so a webhook payload never
 * needs to re-derive the provider or re-poll — it already carries the fact.
 */
export async function markPaymentIntentSucceeded(intentId: string): Promise<PaymentIntent> {
  return finalizeSuccess(intentId);
}

export async function markPaymentIntentFailed(intentId: string, reason: string): Promise<PaymentIntent> {
  const intent = await prisma.paymentIntent.findUnique({ where: { id: intentId } });
  if (!intent) throw new ApiError(404, "Payment intent not found");
  if (intent.status !== "PENDING") return intent;
  return prisma.paymentIntent.update({ where: { id: intent.id }, data: { status: "FAILED", failureReason: reason } });
}

async function finalizeSuccess(intentId: string): Promise<PaymentIntent> {
  let notifyCustomer: { phone: string; message: string } | null = null;

  const result = await prisma.$transaction(async (tx) => {
    const intent = await tx.paymentIntent.findUnique({ where: { id: intentId } });
    if (!intent) throw new ApiError(404, "Payment intent not found");
    if (intent.status !== "PENDING") return intent; // already finalized — idempotent

    const order = await tx.order.findUniqueOrThrow({ where: { id: intent.orderId } });
    const currentPaid = Number(order.paidAmount) + Number(intent.amount);
    const balance = computeBalance(order.total, currentPaid);
    const paymentStatus = computePaymentStatus(order.total, currentPaid);

    const payment = await tx.payment.create({
      data: {
        orderId: order.id,
        customerId: order.customerId,
        amount: intent.amount,
        method: intent.provider,
        reference: intent.providerReference,
        notes: intent.simulated ? "Paiement simulé (mode démo)" : undefined,
        receivedById: intent.initiatedById,
      },
    });

    await tx.order.update({
      where: { id: order.id },
      data: { paidAmount: currentPaid, balance, paymentStatus },
    });

    // Only staff-initiated payments (not customer self-service ones from the
    // portal) attribute to an open cash register — CashTransaction.createdById
    // is required and there is no staff member involved in a portal payment.
    const openRegister = intent.initiatedById
      ? await tx.cashRegister.findFirst({ where: { status: "OPEN", branchId: order.branchId } })
      : null;
    if (openRegister && intent.initiatedById) {
      await tx.cashTransaction.create({
        data: {
          cashRegisterId: openRegister.id,
          type: "SALE",
          amount: intent.amount,
          method: intent.provider,
          description: `Paiement mobile money commande ${order.orderNumber}`,
          orderId: order.id,
          createdById: intent.initiatedById,
        },
      });
    }

    const updatedIntent = await tx.paymentIntent.update({
      where: { id: intent.id },
      data: { status: "SUCCESS", paymentId: payment.id },
    });

    const customer = await tx.customer.findUnique({ where: { id: order.customerId } });
    if (customer) {
      notifyCustomer = {
        phone: customer.phone,
        message: `Paiement de ${Number(intent.amount).toLocaleString("fr-FR")} FCFA reçu pour la commande ${order.orderNumber}. Merci !`,
      };
    }

    return updatedIntent;
  });

  // TS's control-flow narrowing doesn't track assignments made inside the
  // $transaction callback above, so it still sees notifyCustomer as its
  // initial `null` here — the cast reflects the runtime type correctly.
  const pending = notifyCustomer as { phone: string; message: string } | null;
  if (pending) {
    await notifyOrderStatusChange(pending.phone, result.orderId, pending.message);
  }

  return result;
}

/** Branch-scoped visibility check used by staff endpoints before they read/poll an intent. */
export const assertIntentVisible = assertBranchAccess;
