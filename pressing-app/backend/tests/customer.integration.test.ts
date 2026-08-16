import { afterAll, beforeAll, describe, expect, it } from "vitest";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";

describe("customer creation", () => {
  const app = createApp();
  let token: string;
  const createdIds: string[] = [];

  beforeAll(async () => {
    const login = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "Demo1234!" });
    expect(login.status).toBe(200);
    token = login.body.token;
  });

  afterAll(async () => {
    await prisma.customer.deleteMany({ where: { id: { in: createdIds } } });
    await prisma.$disconnect();
  });

  it("rejects invalid login credentials", async () => {
    const res = await request(app)
      .post("/api/auth/login")
      .send({ email: "cashier1@pressing.demo", password: "wrong-password" });
    expect(res.status).toBe(401);
  });

  it("creates a customer and finds it by phone search", async () => {
    const phone = `+225 05${Date.now()}`.slice(0, 17);
    const create = await request(app)
      .post("/api/customers")
      .set("Authorization", `Bearer ${token}`)
      .send({ fullName: "Nouveau Client", phone, type: "INDIVIDUAL" });

    expect(create.status).toBe(201);
    createdIds.push(create.body.id);

    const search = await request(app)
      .get(`/api/customers?search=${encodeURIComponent(phone)}`)
      .set("Authorization", `Bearer ${token}`);
    expect(search.status).toBe(200);
    expect(search.body.data.some((c: { id: string }) => c.id === create.body.id)).toBe(true);
  });

  it("rejects a duplicate phone number", async () => {
    const phone = `+225 06${Date.now()}`.slice(0, 17);
    const first = await request(app)
      .post("/api/customers")
      .set("Authorization", `Bearer ${token}`)
      .send({ fullName: "Premier Client", phone });
    createdIds.push(first.body.id);

    const second = await request(app)
      .post("/api/customers")
      .set("Authorization", `Bearer ${token}`)
      .send({ fullName: "Deuxieme Client", phone });

    expect(second.status).toBe(409);
  });
});
