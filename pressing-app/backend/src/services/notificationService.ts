import { NotificationChannel } from "@prisma/client";
import { prisma } from "../lib/prisma";

export interface NotificationProvider {
  readonly name: string;
  readonly configured: boolean;
  send(recipient: string, message: string, subject?: string): Promise<void>;
}

/**
 * Default provider for every channel: writes the message to the console and
 * lets the caller persist it as a Notification row. No real SMS/WhatsApp/
 * Email is sent — wiring a real provider means implementing this interface
 * (see SmsProvider/EmailProvider/WhatsAppProvider below) and setting the
 * matching *_PROVIDER env var, without touching call sites.
 */
class LogProvider implements NotificationProvider {
  constructor(public readonly name: string) {}
  readonly configured = true;

  async send(recipient: string, message: string): Promise<void> {
    // eslint-disable-next-line no-console
    console.log(`[notification:${this.name}] -> ${recipient}: ${message}`);
  }
}

// Placeholders: real providers would call Twilio / WhatsApp Business API /
// SMTP here. They are not implemented because no API key is configured in
// this environment — see backend/.env.example.
class UnconfiguredProvider implements NotificationProvider {
  constructor(public readonly name: string) {}
  readonly configured = false;

  async send(): Promise<void> {
    throw new Error(`${this.name} provider is not configured. Set the matching env vars.`);
  }
}

function resolveProvider(channel: NotificationChannel): NotificationProvider {
  switch (channel) {
    case "SMS":
      return process.env.SMS_PROVIDER ? new UnconfiguredProvider("sms") : new LogProvider("sms");
    case "EMAIL":
      return process.env.EMAIL_PROVIDER
        ? new UnconfiguredProvider("email")
        : new LogProvider("email");
    case "WHATSAPP":
      return process.env.WHATSAPP_PROVIDER
        ? new UnconfiguredProvider("whatsapp")
        : new LogProvider("whatsapp");
  }
}

export async function notify(
  channel: NotificationChannel,
  recipient: string,
  message: string,
  opts: { subject?: string; relatedOrderId?: string } = {}
) {
  const provider = resolveProvider(channel);
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
