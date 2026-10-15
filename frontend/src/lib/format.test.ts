import { describe, expect, it } from "vitest";

import { clock, digitsForSigma, ms, num, plural, pm, pValue } from "./format";

describe("format", () => {
  it("uses a decimal comma", () => {
    expect(num(1.23456, 3)).toBe("1,235");
    expect(num(null)).toBe("—");
  });

  it("rounds value to the precision of its uncertainty", () => {
    expect(digitsForSigma(0.0023)).toBe(4);
    expect(pm(1.42161, 0.0023)).toBe("1,4216 ± 0,0023");
    expect(pm(9.80788, 0.00036)).toBe("9,80788 ± 0,00036");
    expect(pm(2.5, null, 2)).toBe("2,50");
  });

  it("formats milliseconds with adaptive precision", () => {
    expect(ms(0.00042)).toBe("0,42 мс");
    expect(ms(0.047)).toBe("47,0 мс");
  });

  it("formats stopwatch readings", () => {
    expect(clock(9.876)).toBe("9,87");
    expect(clock(62.345)).toBe("1:02,34");
  });

  it("handles tiny p-values and Russian plurals", () => {
    expect(pValue(1e-9)).toBe("< 0,001");
    expect([1, 2, 5, 11, 22].map((n) => plural(n, "замер", "замера", "замеров"))).toEqual([
      "замер",
      "замера",
      "замеров",
      "замеров",
      "замера",
    ]);
  });
});
