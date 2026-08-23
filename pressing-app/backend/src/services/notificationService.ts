import { NotificationChannel } from "@prisma/client";
import { prisma } from "../lib/prisma";
import { isSimulationMode } from "./settingsService";

export interface NotificationProvider {
  readonly name: string;
  readonly configured: boolean;
  send(recipient: string, message: string, subject?: string): Promise<void>;
}

/**
 * Fallback provider for every channel: writes the message to the console
 * (and it's always persisted as a Notification row by notify() below). Used
 * whenever a real provider isn't configured, or the Settings "simulation
 * mode" toggle is on — so a live demo never depends on real SMS credit or a
 * live WhatsApp Business account.
 */
class LogProvider implements NotificationProvider {
  constructor(public readonly name: string) {}
  readonly configured = true;

  async send(recipient: string, message: string): Promise<void> {
    // eslint-disable-next-line no-console
    console.log(`[notification:${this.name}] -> ${recipient}: ${message}`);
  }
}

/**
 * Twilio SMS (twilio.com). Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
 * TWILIO_FROM_NUMBER — a Twilio phone number capable of sending SMS to the
 * target country.
 */
class TwilioSmsProvider implements NotificationProvider {
  readonly name = "sms";
  private readonly accountSid = process.env.TWILIO_ACCOUNT_SID;
  private readonly authToken = process.env.TWILIO_AUTH_TOKEN;
  private readonly fromNumber = process.env.TWILIO_FROM_NUMBER;

  get configured(): boolean {
    return Boolean(this.accountSid && this.authToken && this.fromNumber);
  }

  async send(recipient: string, message: string): Promise<void> {
    const auth = Buffer.from(`${this.accountSid}:${this.authToken}`).toString("base64");
    const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${this.accountSid}/Messages.json`, {
      method: "POST",
      headers: {
        Authorization: `Basic ${auth}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ To: recipient, From: this.fromNumber!, Body: message }),
    });
    if (!res.ok) throw new Error(`Twilio SMS send failed: ${res.status} ${await res.text()}`);
  }
}

/**
 * WhatsApp Business Cloud API (developers.facebook.com/docs/whatsapp).
 * Needs WHATSAPP_BUSINESS_TOKEN (a permanent system-user access token) and
 * WHATSAPP_PHONE_ID (the sender's registered phone number id). Sends a
 * plain text message — Meta requires the recipient to have messaged the
 * business number in the last 24h for free-form text, otherwise a
 * pre-approved template must be used instead; that's a deployment-specific
 * choice left to whoever sets up the WhatsApp Business account.
 */
class WhatsAppCloudProvider implements NotificationProvider {
  readonly name = "whatsapp";
  private readonly token = process.env.WHATSAPP_BUSINESS_TOKEN;
  private readonly phoneId = process.env.WHATSAPP_PHONE_ID;
  private readonly apiVersion = process.env.WHATSAPP_API_VERSION || "v19.0";

  get configured(): boolean {
    return Boolean(this.token && this.phoneId);
  }

  async send(recipient: string, message: string): Promise<void> {
    const to = recipient.replace(/[^\d]/g, "");
    const res = await fetch(`https://graph.facebook.com/${this.apiVersion}/${this.phoneId}/messages`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ messaging_product: "whatsapp", to, type: "text", text: { body: message } }),
    });
    if (!res.ok) throw new Error(`WhatsApp send failed: ${res.status} ${await res.text()}`);
  }
}

/**
 * Resend (resend.com) transactional email API. Needs RESEND_API_KEY and
 * RESEND_FROM_EMAIL (a sender address on a domain verified in the Resend
 * dashboard).
 */
class ResendEmailProvider implements NotificationProvider {
  readonly name = "email";
  private readonly apiKey = process.env.RESEND_API_KEY;
  private readonly from = process.env.RESEND_FROM_EMAIL;

  get configured(): boolean {
    return Boolean(this.apiKey && this.from);
  }

  async send(recipient: string, message: string, subject?: string): Promise<void> {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: this.from,
        to: recipient,
        subject: subject || "Pressing Étoile",
        text: message,
      }),
    });
    if (!res.ok) throw new Error(`Resend send failed: ${res.status} ${await res.text()}`);
  }
}

const realProviders: Partial<Record<NotificationChannel, NotificationProvider>> = {
  SMS: new TwilioSmsProvider(),
  WHATSAPP: new WhatsAppCloudProvider(),
  EMAIL: new ResendEmailProvider(),
};

async function resolveProvider(channel: NotificationChannel): Promise<NotificationProvider> {
  const real = realProviders[channel];
  const simulate = await isSimulationMode("notifications");
  if (!simulate && real?.configured) return real;
  return new LogProvider(real?.name ?? channel.toLowerCase());
}

export async function notify(
  channel: NotificationChannel,
  recipient: string,
  message: string,
  opts: { subject?: string; relatedOrderId?: string } = {}
) {
  const provider = await resolveProvider(channel);
  const record = await prisma.notification.create({
    data: {
      channel,
      recipient,
      subject: opts.subject,
      message,
      relatedOrderId: opts.relatedOrderId,
      status: "PENDING",
    },
  });

  try {
    await provider.send(recipient, message, opts.subject);
    await prisma.notification.update({
      where: { id: record.id },
      data: { status: "SENT", sentAt: new Date() },
    });
  } catch {
    await prisma.notification.update({ where: { id: record.id }, data: { status: "FAILED" } });
  }
}

/**
 * Sends an order status update to the customer on every channel that makes
 * sense for a status change: SMS (always reaches a basic phone) and
 * WhatsApp (richer, and free for the customer to receive). Both are fired
 * in parallel and independently — one channel failing never blocks or
 * fails the other, matching notify()'s own fire-and-record behavior.
 */
export async function notifyOrderStatusChange(
  customerPhone: string,
  orderId: string,
  message: string
): Promise<void> {
  await Promise.all([
    notify("SMS", customerPhone, message, { relatedOrderId: orderId }),
    notify("WHATSAPP", customerPhone, message, { relatedOrderId: orderId }),
  ]);
}
