import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

describe("customer portal: registration, login, self-service order", () => {
  const app = createApp();
  let token: string;
  let customerId: string;
  let serviceId: string;
  const phone = `+225 09${Date.now()}`.slice(0, 17);

  beforeAll(async () => {
    const service = await prisma.service.findFirst({ where: { active: true } });
    if (!service) throw new Error("No service found — run `npm run seed` first");
    serviceId = service.id;
  });

  afterAll(async () => {
    if (customerId) {
      await prisma.order.deleteMany({ where: { customerId } });
      await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    }
    await prisma.$disconnect();
  });

  it("registers a new customer account", async () => {
    const res = await request(app).post("/api/portal-auth/register").send({
      fullName: "Client Portail Test",
      phone,
      password: "Portail123!",
    });
    expect(res.status).toBe(201);
    expect(res.body.token).toBeTruthy();
    expect(res.body.customer.phone).toBe(phone);
    token = res.body.token;
    customerId = res.body.customer.id;
  });

  it("rejects a second registration on the same phone", async () => {
    const res = await request(app).post("/api/portal-auth/register").send({
      fullName: "Doublon",
      phone,
      password: "Autre123!",
    });
    expect(res.status).toBe(409);
  });

  it("logs in with the registered credentials", async () => {
    const res = await request(app).post("/api/portal-auth/login").send({ phone, password: "Portail123!" });
    expect(res.status).toBe(200);
    expect(res.body.token).toBeTruthy();
  });

  it("rejects a wrong password", async () => {
    const res = await request(app).post("/api/portal-auth/login").send({ phone, password: "wrong" });
    expect(res.status).toBe(401);
  });

  it("a customer token cannot access staff-only routes", async () => {
    const res = await request(app).get("/api/orders").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(401);
  });

  it("lists active services without authentication", async () => {
    const res = await request(app).get("/api/portal/services");
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
  });

  it("creates a self-service order with computed pricing, no payment required", async () => {
    const res = await request(app)
      .post("/api/portal/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({
        fulfillment: "PICKUP",
        items: [{ category: "SHIRT", articleType: "Chemise", quantity: 2, serviceId }],
      });
    expect(res.status).toBe(201);
    expect(res.body.status).toBe("RECEIVED");
    expect(res.body.paymentStatus).toBe("UNPAID");
    expect(Number(res.body.paidAmount)).toBe(0);
    expect(Number(res.body.balance)).toBe(Number(res.body.total));
    expect(res.body.items).toHaveLength(1);
    expect(res.body.branchId).toBeTruthy();
  });

  it("is visible to branch-scoped staff (regression: online orders were invisible without a branchId)", async () => {
    const created = await request(app)
      .post("/api/portal/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({
        fulfillment: "PICKUP",
        items: [{ category: "PANTS", articleType: "Pantalon", quantity: 1, serviceId }],
      });
    expect(created.status).toBe(201);

    const staffLogin = await request(app)
      .post("/api/auth/login")
      .send({ email: "manager@pressing.demo", password: "Demo1234!" });
    expect(staffLogin.status).toBe(200);

    const staffView = await request(app)
      .get(`/api/orders?search=${created.body.orderNumber}`)
      .set("Authorization", `Bearer ${staffLogin.body.token}`);
    expect(staffView.status).toBe(200);
    expect(staffView.body.data.some((o: { id: string }) => o.id === created.body.id)).toBe(true);
  });

  it("requires a delivery address when fulfillment is DELIVERY and the customer has none on file", async () => {
    const res = await request(app)
      .post("/api/portal/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({
        fulfillment: "DELIVERY",
        items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }],
      });
    expect(res.status).toBe(400);
  });

  it("lists only the caller's own orders", async () => {
    const res = await request(app).get("/api/portal/orders").set("Authorization", `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body.length).toBeGreaterThan(0);
    expect(res.body.every((o: { customerId: string }) => o.customerId === customerId)).toBe(true);
  });
});
