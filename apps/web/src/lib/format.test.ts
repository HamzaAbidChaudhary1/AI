import { describe, expect, it } from "vitest";
import { dateTime, money } from "./format";
import { parseSseBlock } from "./api";

describe("money", () => {
  it("always shows the currency code", () => {
    expect(money(1500000, "PKR", "en")).toBe("PKR 15,000");
    expect(money(12750, "GBP", "en")).toBe("GBP 127.50");
    expect(money(1500000, "PKR", "ur")).toMatch(/^PKR /);
  });
});

describe("dateTime", () => {
  it("renders in Asia/Karachi", () => {
    expect(dateTime("2026-11-01T20:30:00Z", "en")).toContain("2 Nov 2026"); // 01:30 next day PKT
  });
});

describe("parseSseBlock", () => {
  it("parses event + json data", () => {
    expect(parseSseBlock('event: progress\ndata: {"step":"x"}')).toEqual({ event: "progress", data: { step: "x" } });
  });
});

describe("latin run isolation", () => {
  const LATIN_RUN = /(\([^()؀-ۿ]+\)|[A-Za-z0-9£$€][A-Za-z0-9£$€ ,.;'’&/%+-]*[A-Za-z0-9.%])/g;
  it("keeps bracketed terms whole and colons outside", () => {
    expect("(Biometrics): yes".split(LATIN_RUN).filter((_, i) => i % 2 === 1)).toEqual(["(Biometrics)", "yes"]);
    expect("حکومتی ویزا فیس: GBP 127".split(LATIN_RUN).filter((_, i) => i % 2 === 1)).toEqual(["GBP 127"]);
  });
});
