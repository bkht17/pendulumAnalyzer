import { describe, expect, it } from "vitest";

import { amplitudeFactor, equivalentLength, logspace } from "./physics";

describe("physics", () => {
  it("matches the series expansion used by the backend", () => {
    expect(amplitudeFactor(null)).toBe(1);
    expect(amplitudeFactor(15)).toBeCloseTo(1.0043005, 6);
  });

  it("spans a log range inclusively", () => {
    const xs = logspace(1, 100, 3);
    expect(xs[0]).toBeCloseTo(1);
    expect(xs[1]).toBeCloseTo(10);
    expect(xs[2]).toBeCloseTo(100);
  });

  it("converts a period to the equivalent ideal-pendulum length", () => {
    // T₀ серии 40 см из реальной записи: центр качания ≈ на 3 см ниже точки замера.
    expect(equivalentLength(1.31493, 9.81)).toBeCloseTo(42.97, 1);
  });
});
