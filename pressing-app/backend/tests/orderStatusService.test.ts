import { describe, expect, it } from "vitest";
import { canTransition, nextPossibleStatuses } from "../src/services/orderStatusService";

describe("canTransition", () => {
  it("allows the standard forward flow", () => {
    expect(canTransition("RECEIVED", "INSPECTION")).toBe(true);
    expect(canTransition("INSPECTION", "PROCESSING")).toBe(true);
    expect(canTransition("PROCESSING", "QUALITY_CHECK")).toBe(true);
    expect(canTransition("QUALITY_CHECK", "READY")).toBe(true);
    expect(canTransition("READY", "OUT_FOR_DELIVERY")).toBe(true);
    expect(canTransition("OUT_FOR_DELIVERY", "DELIVERED")).toBe(true);
    expect(canTransition("DELIVERED", "COMPLETED")).toBe(true);
  });

  it("rejects skipping stages", () => {
    expect(canTransition("RECEIVED", "READY")).toBe(false);
    expect(canTransition("RECEIVED", "COMPLETED")).toBe(false);
  });

  it("rejects moving backwards past quality check", () => {
    expect(canTransition("READY", "RECEIVED")).toBe(false);
  });

  it("allows sending an item back from quality check to processing", () => {
    expect(canTransition("QUALITY_CHECK", "PROCESSING")).toBe(true);
  });

  it("has no transitions out of terminal states", () => {
    expect(nextPossibleStatuses("COMPLETED")).toEqual([]);
    expect(nextPossibleStatuses("CANCELLED")).toEqual([]);
  });

  it("rejects a no-op transition", () => {
    expect(canTransition("READY", "READY")).toBe(false);
  });
});
