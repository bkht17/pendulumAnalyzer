import { describe, expect, it } from "vitest";

import { logDomain, logTicks } from "./logScale";

describe("log scale helpers", () => {
  it("pads the domain on both sides", () => {
    const [lo, hi] = logDomain([0.0004, 0.04], 2);
    expect(lo).toBeCloseTo(0.0002);
    expect(hi).toBeCloseTo(0.08);
  });

  it("produces 1-2-5 ticks inside the domain", () => {
    expect(logTicks([0.0003, 0.06])).toEqual([0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05]);
  });
});
