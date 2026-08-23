import crypto from "crypto";
import { MobileMoneyProviderType } from "@prisma/client";

export interface MobileMoneyChargeResult {
  providerReference: string;
  status: "PENDING" | "SUCCESS" | "FAILED";
  failureReason?: string;
  /** Present for redirect-based providers (Orange Money's web payment page). */
  redirectUrl?: string;
}

export interface MobileMoneyRequestParams {
  phone: string;
  amount: number;
  reference: string;
  description: string;
}

export interface MobileMoneyProvider {
  readonly name: MobileMoneyProviderType;
  readonly configured: boolean;
  requestPayment(params: MobileMoneyRequestParams): Promise<MobileMoneyChargeResult>;
  checkStatus(providerReference: string): Promise<MobileMoneyChargeResult>;
}

/**
 * MTN Mobile Money — Collections API (MTN MoMo Developer Portal).
 * https://momodeveloper.mtn.com — "Collection" product.
 * A real deployment needs: MTN_MOMO_SUBSCRIPTION_KEY (Ocp-Apim-Subscription-Key),
 * MTN_MOMO_API_USER, MTN_MOMO_API_KEY (created against that subscription key),
 * MTN_MOMO_TARGET_ENVIRONMENT ("sandbox" or the live environment name MTN
 * assigns, e.g. "mtncameroon"), and MTN_MOMO_BASE_URL (sandbox default below).
 * Flow: OAuth2 client-credentials token -> POST requesttopay (push a
 * pay-with-PIN prompt to the payer's phone) -> GET requesttopay/{id} to poll.
 */
class MtnMomoProvider implements MobileMoneyProvider {
  readonly name = "MTN_MOMO" as const;
  private readonly subscriptionKey = process.env.MTN_MOMO_SUBSCRIPTION_KEY;
  private readonly apiUser = process.env.MTN_MOMO_API_USER;
  private readonly apiKey = process.env.MTN_MOMO_API_KEY;
  private readonly targetEnvironment = process.env.MTN_MOMO_TARGET_ENVIRONMENT || "sandbox";
  private readonly baseUrl = process.env.MTN_MOMO_BASE_URL || "https://sandbox.momodeveloper.mtn.com";
  private cachedToken: { value: string; expiresAt: number } | null = null;

  get configured(): boolean {
    return Boolean(this.subscriptionKey && this.apiUser && this.apiKey);
  }

  private async getToken(): Promise<string> {
    if (this.cachedToken && this.cachedToken.expiresAt > Date.now() + 30_000) {
      return this.cachedToken.value;
    }
    const basicAuth = Buffer.from(`${this.apiUser}:${this.apiKey}`).toString("base64");
    const res = await fetch(`${this.baseUrl}/collection/token/`, {
      method: "POST",
      headers: {
        Authorization: `Basic ${basicAuth}`,
        "Ocp-Apim-Subscription-Key": this.subscriptionKey!,
      },
    });
    if (!res.ok) throw new Error(`MTN MoMo token request failed: ${res.status} ${await res.text()}`);
    const body = (await res.json()) as { access_token: string; expires_in: number };
    this.cachedToken = { value: body.access_token, expiresAt: Date.now() + body.expires_in * 1000 };
    return body.access_token;
  }

  private normalizePhone(phone: string): string {
    // MTN MoMo expects an MSISDN with no leading '+' (e.g. 237670000000).
    return phone.replace(/[^\d]/g, "").replace(/^0+/, "237");
  }

  async requestPayment(params: MobileMoneyRequestParams): Promise<MobileMoneyChargeResult> {
    if (!this.configured) throw new Error("MTN MoMo provider is not configured");
    const token = await this.getToken();
    const referenceId = crypto.randomUUID();

    const res = await fetch(`${this.baseUrl}/collection/v1_0/requesttopay`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Reference-Id": referenceId,
        "X-Target-Environment": this.targetEnvironment,
        "Ocp-Apim-Subscription-Key": this.subscriptionKey!,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        amount: String(Math.round(params.amount)),
        currency: "XAF",
        externalId: params.reference,
        payer: { partyIdType: "MSISDN", partyId: this.normalizePhone(params.phone) },
        payerMessage: params.description,
        payeeNote: params.description,
      }),
    });

    if (res.status !== 202) {
      return { providerReference: referenceId, status: "FAILED", failureReason: `MTN MoMo rejected the request (${res.status})` };
    }
    return { providerReference: referenceId, status: "PENDING" };
  }

  async checkStatus(providerReference: string): Promise<MobileMoneyChargeResult> {
    const token = await this.getToken();
    const res = await fetch(`${this.baseUrl}/collection/v1_0/requesttopay/${providerReference}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Target-Environment": this.targetEnvironment,
        "Ocp-Apim-Subscription-Key": this.subscriptionKey!,
      },
    });
    if (!res.ok) throw new Error(`MTN MoMo status check failed: ${res.status}`);
    const body = (await res.json()) as { status: "PENDING" | "SUCCESSFUL" | "FAILED"; reason?: string };
    if (body.status === "SUCCESSFUL") return { providerReference, status: "SUCCESS" };
    if (body.status === "FAILED") return { providerReference, status: "FAILED", failureReason: body.reason };
    return { providerReference, status: "PENDING" };
  }
}

/**
 * Orange Money — Web Payment API (Orange Developer Center).
 * https://developer.orange.com — "Orange Money Web Payment" product.
 * A real deployment needs: ORANGE_MONEY_CLIENT_ID, ORANGE_MONEY_CLIENT_SECRET
 * (OAuth2 client-credentials app), ORANGE_MONEY_MERCHANT_KEY (issued with the
 * merchant account), and ORANGE_MONEY_COUNTRY_CODE (e.g. "cm" for Cameroon).
 * Unlike MTN's direct USSD push, Orange's public API is redirect-based: we
 * create a web payment session and hand the customer a payment_url where
 * they approve with their Orange Money PIN; we poll transactionstatus (or
 * receive their webhook) to learn the outcome.
 */
class OrangeMoneyProvider implements MobileMoneyProvider {
  readonly name = "ORANGE_MONEY" as const;
  private readonly clientId = process.env.ORANGE_MONEY_CLIENT_ID;
  private readonly clientSecret = process.env.ORANGE_MONEY_CLIENT_SECRET;
  private readonly merchantKey = process.env.ORANGE_MONEY_MERCHANT_KEY;
  private readonly countryCode = process.env.ORANGE_MONEY_COUNTRY_CODE || "cm";
  private readonly baseUrl = process.env.ORANGE_MONEY_BASE_URL || "https://api.orange.com";
  private readonly returnUrl = process.env.ORANGE_MONEY_RETURN_URL || "https://example.com/payment/return";
  private readonly notifUrl = process.env.ORANGE_MONEY_NOTIF_URL || "https://example.com/api/webhooks/orange-money";
  private cachedToken: { value: string; expiresAt: number } | null = null;
  private readonly payTokens = new Map<string, string>();

  get configured(): boolean {
    return Boolean(this.clientId && this.clientSecret && this.merchantKey);
  }

  private async getToken(): Promise<string> {
    if (this.cachedToken && this.cachedToken.expiresAt > Date.now() + 30_000) {
      return this.cachedToken.value;
    }
    const basicAuth = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString("base64");
    const res = await fetch(`${this.baseUrl}/oauth/v3/token`, {
      method: "POST",
      headers: { Authorization: `Basic ${basicAuth}`, "Content-Type": "application/x-www-form-urlencoded" },
      body: "grant_type=client_credentials",
    });
    if (!res.ok) throw new Error(`Orange Money token request failed: ${res.status} ${await res.text()}`);
    const body = (await res.json()) as { access_token: string; expires_in: number };
    this.cachedToken = { value: body.access_token, expiresAt: Date.now() + body.expires_in * 1000 };
    return body.access_token;
  }

  async requestPayment(params: MobileMoneyRequestParams): Promise<MobileMoneyChargeResult> {
    if (!this.configured) throw new Error("Orange Money provider is not configured");
    const token = await this.getToken();

    const res = await fetch(`${this.baseUrl}/orange-money-webpay/${this.countryCode}/v1/webpayment`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        merchant_key: this.merchantKey,
        currency: "XAF",
        order_id: params.reference,
        amount: Math.round(params.amount),
        return_url: this.returnUrl,
        cancel_url: this.returnUrl,
        notif_url: this.notifUrl,
        lang: "fr",
        reference: params.description,
      }),
    });

    if (!res.ok) {
      return { providerReference: params.reference, status: "FAILED", failureReason: `Orange Money rejected the request (${res.status})` };
    }
    const body = (await res.json()) as { payment_url: string; pay_token: string };
    this.payTokens.set(params.reference, body.pay_token);
    return { providerReference: params.reference, status: "PENDING", redirectUrl: body.payment_url };
  }

  async checkStatus(providerReference: string): Promise<MobileMoneyChargeResult> {
    const token = await this.getToken();
    const payToken = this.payTokens.get(providerReference);
    const query = new URLSearchParams({ order_id: providerReference, ...(payToken ? { pay_token: payToken } : {}) });
    const res = await fetch(`${this.baseUrl}/orange-money-webpay/${this.countryCode}/v1/transactionstatus?${query}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Orange Money status check failed: ${res.status}`);
    const body = (await res.json()) as { status: "SUCCESS" | "FAILED" | "PENDING" | "EXPIRED" };
    if (body.status === "SUCCESS") return { providerReference, status: "SUCCESS" };
    if (body.status === "PENDING") return { providerReference, status: "PENDING" };
    return { providerReference, status: "FAILED", failureReason: body.status };
  }
}

/**
 * Demo/simulation provider: no network calls, no real money. Resolves to
 * SUCCESS after being "checked" once (immediate for tests, effectively
 * instant for a live demo click). Used whenever the real provider isn't
 * configured, or the Settings "simulation mode" toggle is on.
 */
class SimulatedMobileMoneyProvider implements MobileMoneyProvider {
  readonly configured = true;
  constructor(public readonly name: MobileMoneyProviderType) {}

  async requestPayment(params: MobileMoneyRequestParams): Promise<MobileMoneyChargeResult> {
    return { providerReference: `SIM-${crypto.randomUUID()}`, status: "PENDING" };
  }

  async checkStatus(providerReference: string): Promise<MobileMoneyChargeResult> {
    return { providerReference, status: "SUCCESS" };
  }
}

const realProviders: Record<MobileMoneyProviderType, MobileMoneyProvider> = {
  MTN_MOMO: new MtnMomoProvider(),
  ORANGE_MONEY: new OrangeMoneyProvider(),
};

export function resolveMobileMoneyProvider(
  type: MobileMoneyProviderType,
  forceSimulate: boolean
): { provider: MobileMoneyProvider; simulated: boolean } {
  const real = realProviders[type];
  if (!forceSimulate && real.configured) return { provider: real, simulated: false };
  return { provider: new SimulatedMobileMoneyProvider(type), simulated: true };
}
