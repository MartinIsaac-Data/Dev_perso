import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// No Twilio/WhatsApp credentials exist in this environment, so every
// notification falls back to the simulated LogProvider — this confirms
// that fallback still marks each Notification row SENT (not FAILED) and
// that delivery status changes propagate to the order's status and fire
// the customer notification, exactly like a direct order status change.
describe("automatic status notifications", () => {
  const app = createApp();
  let token: string;
  let serviceId: string;
  let customerId: string;
  let customerPhone: string;

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "manager@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;

    const service = await prisma.service.findFirst({ where: { active: true } });
    if (!service) throw new Error("No service found — run `npm run seed` first");
    serviceId = service.id;

    customerPhone = `+237 6${Date.now()}`.slice(0, 17);
    const customer = await prisma.customer.create({ data: { fullName: "Client Livraison Test", phone: customerPhone } });
    customerId = customer.id;
  });

  afterAll(async () => {
    await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    await prisma.$disconnect();
  });

  it("marks a simulated SMS/WhatsApp notification as SENT rather than FAILED", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    expect(create.status).toBe(201);

    const notifications = await prisma.notification.findMany({ where: { relatedOrderId: create.body.id } });
    expect(notifications.length).toBeGreaterThanOrEqual(2);
    const channels = notifications.map((n) => n.channel).sort();
    expect(channels).toEqual(["SMS", "WHATSAPP"]);
    for (const n of notifications) {
      expect(n.status).toBe("SENT");
    }
  });

  it("moves the order to OUT_FOR_DELIVERY and notifies when a delivery goes IN_TRANSIT", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    const orderId = create.body.id;

    for (const status of ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY"]) {
      await request(app)
        .post(`/api/orders/${orderId}/status`)
        .set("Authorization", `Bearer ${token}`)
        .send({ status });
    }

    const delivery = await request(app)
      .post("/api/deliveries")
      .set("Authorization", `Bearer ${token}`)
      .send({ orderId, type: "DELIVERY", address: "Quartier Test" });
    expect(delivery.status).toBe(201);

    const updated = await request(app)
      .put(`/api/deliveries/${delivery.body.id}`)
      .set("Authorization", `Bearer ${token}`)
      .send({ status: "IN_TRANSIT" });
    expect(updated.status).toBe(200);

    const order = await request(app).get(`/api/orders/${orderId}`).set("Authorization", `Bearer ${token}`);
    expect(order.body.status).toBe("OUT_FOR_DELIVERY");

    const notifications = await prisma.notification.findMany({
      where: { relatedOrderId: orderId, message: { contains: "en cours de livraison" } },
    });
    expect(notifications.length).toBeGreaterThanOrEqual(2);
  });

  it("moves the order to DELIVERED and notifies when a delivery is confirmed DELIVERED", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    const orderId = create.body.id;
    for (const status of ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY"]) {
      await request(app)
        .post(`/api/orders/${orderId}/status`)
        .set("Authorization", `Bearer ${token}`)
        .send({ status });
    }
    const delivery = await request(app)
      .post("/api/deliveries")
      .set("Authorization", `Bearer ${token}`)
      .send({ orderId, type: "DELIVERY", address: "Quartier Test" });

    const updated = await request(app)
      .put(`/api/deliveries/${delivery.body.id}`)
      .set("Authorization", `Bearer ${token}`)
      .send({ status: "DELIVERED" });
    expect(updated.status).toBe(200);

    const order = await request(app).get(`/api/orders/${orderId}`).set("Authorization", `Bearer ${token}`);
    expect(order.body.status).toBe("DELIVERED");

    const notifications = await prisma.notification.findMany({
      where: { relatedOrderId: orderId, message: { contains: "a été livrée" } },
    });
    expect(notifications.length).toBeGreaterThanOrEqual(2);
  });

  it("tells a pickup customer they can come collect the order when it's READY", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    const orderId = create.body.id;

    for (const status of ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY"]) {
      await request(app)
        .post(`/api/orders/${orderId}/status`)
        .set("Authorization", `Bearer ${token}`)
        .send({ status });
    }

    const notifications = await prisma.notification.findMany({
      where: { relatedOrderId: orderId, message: { contains: "venir la récupérer" } },
    });
    expect(notifications.length).toBeGreaterThanOrEqual(2);
  });

  it("does not tell a delivery customer to come pick up when the order becomes READY", async () => {
    const create = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    const orderId = create.body.id;

    const delivery = await request(app)
      .post("/api/deliveries")
      .set("Authorization", `Bearer ${token}`)
      .send({ orderId, type: "DELIVERY", address: "Quartier Test" });
    expect(delivery.status).toBe(201);

    for (const status of ["INSPECTION", "PROCESSING", "QUALITY_CHECK", "READY"]) {
      await request(app)
        .post(`/api/orders/${orderId}/status`)
        .set("Authorization", `Bearer ${token}`)
        .send({ status });
    }

    const pickupNotifications = await prisma.notification.findMany({
      where: { relatedOrderId: orderId, message: { contains: "venir la récupérer" } },
    });
    expect(pickupNotifications).toHaveLength(0);

    const deliveryReadyNotifications = await prisma.notification.findMany({
      where: { relatedOrderId: orderId, message: { contains: "sera bientôt livrée" } },
    });
    expect(deliveryReadyNotifications.length).toBeGreaterThanOrEqual(2);
  });
});
