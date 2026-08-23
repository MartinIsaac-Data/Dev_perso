import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// No real Orange Money / MTN MoMo credentials exist in this environment, so
// these requests fall back to the simulated provider automatically (see
// mobileMoneyProviders.ts) — exercising the exact same PaymentIntent
// lifecycle a real integration would use once real credentials are set.
describe("mobile money payment flow", () => {
  const app = createApp();
  let token: string;
  let serviceId: string;
  let customerId: string;

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;

    const service = await prisma.service.findFirst({ where: { active: true } });
    if (!service) throw new Error("No service found — run `npm run seed` first");
    serviceId = service.id;

    const customer = await prisma.customer.create({
      data: { fullName: "Client Mobile Money", phone: `+237 6${Date.now()}`.slice(0, 17) },
    });
    customerId = customer.id;
  });

  afterAll(async () => {
    await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    await prisma.$disconnect();
  });

  it("initiates an MTN MoMo payment and settles it through the simulated provider", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 2, serviceId }] });
    expect(create.status).toBe(201);
    const orderId = create.body.id;
    const total = Number(create.body.total);

    const initiate = await request(app)
      .post(`/api/orders/${orderId}/mobile-money`)
      .set("Authorization", `Bearer ${token}`)
      .send({ provider: "MTN_MOMO", phone: "+237 670 00 00 00" });

    expect(initiate.status).toBe(201);
    expect(initiate.body.status).toBe("PENDING");
    expect(initiate.body.simulated).toBe(true);
    const intentId = initiate.body.id;

    const poll = await request(app)
      .get(`/api/payment-intents/${intentId}`)
      .set("Authorization", `Bearer ${token}`);

    expect(poll.status).toBe(200);
    expect(poll.body.status).toBe("SUCCESS");
    expect(poll.body.paymentId).toBeTruthy();

    const order = await request(app).get(`/api/orders/${orderId}`).set("Authorization", `Bearer ${token}`);
    expect(Number(order.body.paidAmount)).toBe(total);
    expect(order.body.paymentStatus).toBe("PAID");
    expect(order.body.payments.some((p: { method: string }) => p.method === "MTN_MOMO")).toBe(true);
  });

  it("rejects an amount larger than the order balance", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });

    const res = await request(app)
      .post(`/api/orders/${create.body.id}/mobile-money`)
      .set("Authorization", `Bearer ${token}`)
      .send({ provider: "ORANGE_MONEY", phone: "+237 690 00 00 00", amount: Number(create.body.total) + 5000 });

    expect(res.status).toBe(400);
  });

  it("is idempotent when polled twice after success", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });

    const initiate = await request(app)
      .post(`/api/orders/${create.body.id}/mobile-money`)
      .set("Authorization", `Bearer ${token}`)
      .send({ provider: "ORANGE_MONEY", phone: "+237 690 00 00 00" });
    const intentId = initiate.body.id;

    const first = await request(app).get(`/api/payment-intents/${intentId}`).set("Authorization", `Bearer ${token}`);
    const second = await request(app).get(`/api/payment-intents/${intentId}`).set("Authorization", `Bearer ${token}`);

    expect(first.body.status).toBe("SUCCESS");
    expect(second.body.status).toBe("SUCCESS");
    expect(second.body.paymentId).toBe(first.body.paymentId);
  });
});
