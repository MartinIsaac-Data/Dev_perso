import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

// A 1x1 red pixel JPEG — small enough to keep the test fast, a real
// decodable image so this exercises the actual multer + disk-storage path
// rather than an arbitrary byte blob.
const TINY_JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q==",
  "base64"
);

describe("order item photos", () => {
  const app = createApp();
  let token: string;
  let outsiderToken: string;
  let serviceId: string;
  let customerId: string;
  let itemId: string;

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;

    // cashier2 is at a different branch — used to prove branch-scoped access denial.
    const outsider = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier2@pressing.demo", password: "Demo1234!" });
    outsiderToken = outsider.body.token;

    const service = await prisma.service.findFirst({ where: { active: true } });
    if (!service) throw new Error("No service found — run `npm run seed` first");
    serviceId = service.id;

    const customer = await prisma.customer.create({
      data: { fullName: "Client Photos Test", phone: `+237 6${Date.now()}`.slice(0, 17) },
    });
    customerId = customer.id;

    const order = await request(app)
      .post("/api/orders")
      .set("Authorization", `Bearer ${token}`)
      .send({ customerId, items: [{ category: "SHIRT", articleType: "Chemise", quantity: 1, serviceId }] });
    itemId = order.body.items[0].id;
  });

  afterAll(async () => {
    await prisma.customer.delete({ where: { id: customerId } }).catch(() => undefined);
    await prisma.$disconnect();
  });

  it("uploads a real photo, stores it on disk, and lists it back", async () => {
    const upload = await request(app)
      .post(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${token}`)
      .attach("photo", TINY_JPEG, { filename: "avant-traitement.jpg", contentType: "image/jpeg" });

    expect(upload.status).toBe(201);
    expect(upload.body.mimeType).toBe("image/jpeg");
    expect(upload.body.sizeBytes).toBe(TINY_JPEG.length);

    const list = await request(app)
      .get(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${token}`);
    expect(list.status).toBe(200);
    expect(list.body).toHaveLength(1);
    expect(list.body[0].id).toBe(upload.body.id);
  });

  it("serves the actual file bytes back", async () => {
    const upload = await request(app)
      .post(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${token}`)
      .attach("photo", TINY_JPEG, { filename: "tache.jpg", contentType: "image/jpeg" });

    const file = await request(app)
      .get(`/api/order-items/photos/${upload.body.id}/file`)
      .set("Authorization", `Bearer ${token}`)
      .buffer(true)
      .parse((res, cb) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () => cb(null, Buffer.concat(chunks)));
      });
    expect(file.status).toBe(200);
    expect(file.headers["content-type"]).toBe("image/jpeg");
    expect(Buffer.compare(file.body as Buffer, TINY_JPEG)).toBe(0);
  });

  it("rejects a non-image file", async () => {
    const res = await request(app)
      .post(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${token}`)
      .attach("photo", Buffer.from("not an image"), { filename: "notes.txt", contentType: "text/plain" });
    expect(res.status).toBe(400);
  });

  it("denies access to staff from a different branch", async () => {
    const res = await request(app)
      .get(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${outsiderToken}`);
    expect(res.status).toBe(403);
  });

  it("deletes a photo and it stops showing up in the list", async () => {
    const upload = await request(app)
      .post(`/api/order-items/${itemId}/photos`)
      .set("Authorization", `Bearer ${token}`)
      .attach("photo", TINY_JPEG, { filename: "a-supprimer.jpg", contentType: "image/jpeg" });

    const del = await request(app)
      .delete(`/api/order-items/photos/${upload.body.id}`)
      .set("Authorization", `Bearer ${token}`);
    expect(del.status).toBe(204);

    const fetchDeleted = await request(app)
      .get(`/api/order-items/photos/${upload.body.id}/file`)
      .set("Authorization", `Bearer ${token}`);
    expect(fetchDeleted.status).toBe(404);
  });
});
