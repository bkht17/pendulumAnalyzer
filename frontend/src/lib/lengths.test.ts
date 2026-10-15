import { describe, expect, it } from "vitest";

import { parseLengths } from "./lengths";

describe("parseLengths", () => {
  it("accepts the usual ways to type a list", () => {
    expect(parseLengths("60 40 20")).toEqual([60, 40, 20]);
    expect(parseLengths("60; 40;20")).toEqual([60, 40, 20]);
    expect(parseLengths("60, 40, 20")).toEqual([60, 40, 20]);
  });

  it("treats a comma inside a number as the decimal separator", () => {
    expect(parseLengths("62,5 40,2")).toEqual([62.5, 40.2]);
  });

  it("drops garbage and impossible values", () => {
    expect(parseLengths("см 0 -5 abc 700 25")).toEqual([25]);
  });
});
