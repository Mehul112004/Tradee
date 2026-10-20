import { describe, it, expect, vi, afterEach } from "vitest";
import { number, fmt, percent, query, date, request, ApiError } from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("financial display and request boundaries", () => {
  it("keeps missing, nonfinite and zero distinct", () => {
    expect(number(null)).toBeNull();
    expect(number(false)).toBeNull();
    expect(number(" ")).toBeNull();
    expect(number("")).toBeNull();
    expect(number(undefined)).toBeNull();
    expect(number("NaN")).toBeNull();
    expect(number(Infinity)).toBeNull();
    expect(number("0")).toBe(0);
    expect(fmt(null)).toBe("—");
    expect(fmt("0")).toBe("0.00");
  });
  it("does not reinterpret fractions or round authoritative source strings in place", () => {
    expect(percent(".026528125")).toBe("2.65%");
    expect(percent(null)).toBe("—");
    expect(fmt("8.489", 3)).toBe("8.489");
  });
  it("keeps explicit zero cutoffs and encodes symbols", () => {
    expect(query({ at_ms: 0, symbol: "A/B", omit: null })).toBe(
      "at_ms=0&symbol=A%2FB",
    );
  });
  it("timezone is explicit and epoch zero is valid", () => {
    expect(date(0, "UTC")).toContain("00:00:00");
    expect(date(0, "Asia/Kolkata")).toContain("05:30:00");
  });
  it("rejects protected source errors without turning them into empty datasets", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 423,
        json: async () => ({ error: { message: "Final holdout locked" } }),
      }),
    );
    await expect(request("runs/x")).rejects.toThrow("Final holdout locked");
  });
  it("validates service envelopes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: [] }) }),
    );
    await expect(request("runs")).rejects.toThrow("Invalid service response");
  });
});
