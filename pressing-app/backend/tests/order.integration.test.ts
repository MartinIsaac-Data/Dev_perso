import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// Runs against a real PostgreSQL database (DATABASE_URL from .env) that has
// already been seeded — `npm run seed` must be run once before `npm test`.
// It creates its own customer/order data rather than depending on exact
// counts from the demo seed, so it is safe to run repeatedly.
describe("order creation and payment flow", () => {
  const app = createApp();
  let token: string;
  let serviceId: string;
  let customerId: string;

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "manager@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;

    const service = await prisma.service.findFirst({ where: { active: true } });
    if (!service) throw new Error("No service found — run `npm run seed` first");
    serviceId = service.id;

    const customer = await prisma.customer.create({
      data: { fullName: "Client Test Intégration", phone: `+225 07${Date.now()}`.slice(0, 17) },
    });
    customerId = customer.id;
  });

  afterAll(async () => {
    await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    await prisma.$disconnect();
  });

  it("rejects unauthenticated requests", async () => {
    const res = await request(app).get("/api/orders");
    expect(res.status).toBe(401);
  });

  it("creates an order with computed totals and a persisted balance", async () => {
    const res = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({
        customerId,
        items: [
          { category: "SHIRT", articleType: "Chemise", quantity: 2, serviceId },
          { category: "PANTS", articleType: "Pantalon", quantity: 1, serviceId },
        ],
        discount: 0,
        deliveryFee: 0,
      });

    expect(res.status).toBe(201);
    expect(res.body.orderNumber).toMatch(/^PR-\d{8}-/);
    expect(res.body.items).toHaveLength(2);
    expect(Number(res.body.paidAmount)).toBe(0);
    expect(res.body.paymentStatus).toBe("UNPAID");
    expect(Number(res.body.balance)).toBe(Number(res.body.total));
  });

  it("registers a partial payment and updates balance + status", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({
        customerId,
        items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }],
      });

    const orderId = create.body.id;
    const total = Number(create.body.total);
    const partial = Math.floor(total / 2);

    const payment = await request(app)
      .post(`/api/orders/${orderId}/payments`)
      .set("Authorization", `Bearer ${token}`)
      .send({ amount: partial, method: "CASH" });

    expect(payment.status).toBe(201);
    expect(Number(payment.body.paidAmount)).toBe(partial);
    expect(payment.body.paymentStatus).toBe("PARTIAL");
    expect(Number(payment.body.balance)).toBe(total - partial);
  });

  it("rejects an invalid status transition", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });

    const res = await request(app)
      .post(`/api/orders/${create.body.id}/status`)
      .set("Authorization", `Bearer ${token}`)
      .send({ status: "COMPLETED" });

    expect(res.status).toBe(400);
  });

  it("walks an order through its full valid status flow", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });

    const orderId = create.body.id;
    const flow = ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY", "COMPLETED"];
    for (const status of flow) {
      const res = await request(app)
        .post(`/api/orders/${orderId}/status`)
        .set("Authorization", `Bearer ${token}`)
        .send({ status });
      expect(res.status).toBe(200);
      expect(res.body.status).toBe(status);
    }
  });
});
