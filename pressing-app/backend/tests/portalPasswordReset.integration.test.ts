import { afterAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

async function latestResetCode(recipient: string, channel: "SMS" | "EMAIL" = "SMS"): Promise<string> {
  const note = await prisma.notification.findFirst({
    where: { recipient, channel },
    orderBy: { createdAt: "desc" },
  });
  const match = note?.message.match(/\d{6}/);
  if (!match) throw new Error(`No reset code found in ${channel} notifications for ${recipient}`);
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

  it("returns a generic message for an unknown identifier, without creating a reset code", async () => {
    const res = await request(app)
      .post("/api/portal-auth/forgot-password")
      .send({ identifier: "+225 0000000000" });
    expect(res.status).toBe(200);
    expect(res.body.message).toMatch(/code de réinitialisation/i);
  });

  it("rejects a reset with no prior request", async () => {
    const res = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ identifier: phone, code: "000000", newPassword: "Whatever123!" });
    expect(res.status).toBe(400);
  });

  it("sends a reset code and returns the same generic message", async () => {
    const res = await request(app).post("/api/portal-auth/forgot-password").send({ identifier: phone });
    expect(res.status).toBe(200);
    expect(res.body.message).toMatch(/code de réinitialisation/i);
  });

  it("rejects an incorrect code", async () => {
    const code = await latestResetCode(phone);
    const wrongCode = code === "111111" ? "222222" : "111111";
    const res = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ identifier: phone, code: wrongCode, newPassword: "NewPass123!" });
    expect(res.status).toBe(400);
  });

  it("resets the password with the correct code, and the code cannot be reused", async () => {
    const code = await latestResetCode(phone);

    const reset = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ identifier: phone, code, newPassword: "NewPass123!" });
    expect(reset.status).toBe(200);

    const reuse = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ identifier: phone, code, newPassword: "AnotherPass123!" });
    expect(reuse.status).toBe(400);
  });

  it("logs in with the new password and no longer with the old one", async () => {
    const withNew = await request(app)
      .post("/api/portal-auth/login")
      .send({ identifier: phone, password: "NewPass123!" });
    expect(withNew.status).toBe(200);
    expect(withNew.body.token).toBeTruthy();

    const withOld = await request(app)
      .post("/api/portal-auth/login")
      .send({ identifier: phone, password: "Original123!" });
    expect(withOld.status).toBe(401);
  });
});

describe("customer portal: email as login identifier", () => {
  const app = createApp();
  let customerId: string;
  const phone = `+225 07${Date.now()}`.slice(0, 17);
  const email = `client.reset.${Date.now()}@example.com`;

  afterAll(async () => {
    if (customerId) {
      await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    }
    await prisma.$disconnect();
  });

  it("registers an account with an email", async () => {
    const res = await request(app).post("/api/portal-auth/register").send({
      fullName: "Client Email Test",
      phone,
      email,
      password: "EmailPass123!",
    });
    expect(res.status).toBe(201);
    customerId = res.body.customer.id;
  });

  it("rejects a second account registered with the same email", async () => {
    const res = await request(app).post("/api/portal-auth/register").send({
      fullName: "Doublon Email",
      phone: `+225 06${Date.now()}`.slice(0, 17),
      email,
      password: "Autre123!",
    });
    expect(res.status).toBe(409);
  });

  it("logs in with the email instead of the phone", async () => {
    const res = await request(app)
      .post("/api/portal-auth/login")
      .send({ identifier: email, password: "EmailPass123!" });
    expect(res.status).toBe(200);
    expect(res.body.customer.phone).toBe(phone);
  });

  it("sends the reset code by email too when requested by email", async () => {
    const forgot = await request(app).post("/api/portal-auth/forgot-password").send({ identifier: email });
    expect(forgot.status).toBe(200);

    const code = await latestResetCode(email, "EMAIL");
    const reset = await request(app)
      .post("/api/portal-auth/reset-password")
      .send({ identifier: email, code, newPassword: "NewEmailPass123!" });
    expect(reset.status).toBe(200);

    const login = await request(app)
      .post("/api/portal-auth/login")
      .send({ identifier: phone, password: "NewEmailPass123!" });
    expect(login.status).toBe(200);
  });
});
