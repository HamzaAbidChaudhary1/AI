import { describe, expect, it } from "vitest";
import { diffLines } from "./diff";

describe("diffLines", () => {
  it("marks changed fee lines", () => {
    const d = diffLines("a\n- Fee: GBP 127\nb", "a\n- Fee: GBP 135\nb");
    expect(d.filter((l) => l.kind !== "same")).toEqual([
      { kind: "del", text: "- Fee: GBP 127" },
      { kind: "add", text: "- Fee: GBP 135" },
    ]);
  });
});
