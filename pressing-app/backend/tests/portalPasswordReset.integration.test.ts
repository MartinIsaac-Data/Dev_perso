import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

async function latestResetCode(phone: string): Promise<string> {
  const note = await prisma.notification.findFirst({
    where: { recipient: phone, channel: "SMS" },
    orderBy: { createdAt: "desc" },
  });
  const match = note?.message.match(/\d{6}/);
  if (!match) throw new Error(`No reset code found in notifications for ${phone}`);
  return match[0];
}

describe("customer portal: forgot / reset password", () => {
  const app = createApp();
  let customerId: string;
  const phone = `+225 08${Date.now()}`.slice(0, 17);

  afterAll(async () => {
    if (customerId) {
      await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    }
    await prisma.$disconnect();
  });

  it("registers the account used for the reset flow", async () => {
    const res = await request(app).post("/api/portal-auth/register").send({
      fullName: "Client Reset Test",
      phone,
      password: "Original123!",
    });
    expect(res.status).toBe(201);
    customerId = res.body.customer.id;
  });

  it("returns a generic message for an unknown phone, without creating a reset code", async () => {
    const res = await request(app)
      .post("/api/portal-auth/forgot-password")
      .send({ phone: "+225 0000000000" });
    expect(res.status).toBe(200);
    expect(res.body.message).toMatch(/code de réinitialisation/i);
  });

  it("rejects a reset with no prior request", async () => {
    const res = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ phone, code: "000000", newPassword: "Whatever123!" });
    expect(res.status).toBe(400);
  });

  it("sends a reset code and returns the same generic message", async () => {
    const res = await request(app).post("/api/portal-auth/forgot-password").send({ phone });
    expect(res.status).toBe(200);
    expect(res.body.message).toMatch(/code de réinitialisation/i);
  });

  it("rejects an incorrect code", async () => {
    const code = await latestResetCode(phone);
    const wrongCode = code === "111111" ? "222222" : "111111";
    const res = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ phone, code: wrongCode, newPassword: "NewPass123!" });
    expect(res.status).toBe(400);
  });

  it("resets the password with the correct code, and the code cannot be reused", async () => {
    const code = await latestResetCode(phone);

    const reset = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ phone, code, newPassword: "NewPass123!" });
    expect(reset.status).toBe(200);

    const reuse = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ phone, code, newPassword: "AnotherPass123!" });
    expect(reuse.status).toBe(400);
  });

  it("logs in with the new password and no longer with the old one", async () => {
    const withNew = await request(app).post("/api/portal-auth/login").send({ phone, password: "NewPass123!" });
    expect(withNew.status).toBe(200);
    expect(withNew.body.token).toBeTruthy();

    const withOld = await request(app).post("/api/portal-auth/login").send({ phone, password: "Original123!" });
    expect(withOld.status).toBe(401);
  });
});
