import { describe, expect, it } from "vitest";
import { hintForRage, hintsForRage } from "./rage";

describe("hintForRage", () => {
  it("maps known rage signatures to concrete hints", () => {
    expect(hintForRage("button.btn|批 准").key).toBe("approve");
    expect(hintForRage("button.primary|Sign & seal").key).toBe("tour-seal");
    expect(hintForRage("button.tour-seal|盖印").key).toBe("tour-seal");
    expect(hintForRage("a|jobs/new").key).toBe("new-verification");
    expect(hintForRage("button|Run verification").key).toBe("run");
    expect(hintForRage("input|Provider base URL").key).toBe("model-path");
  });

  it("falls back to the generic hint for unknown signatures", () => {
    expect(hintForRage("div.card|任何地方").key).toBe("generic");
    expect(hintForRage("").key).toBe("generic");
  });
});

describe("hintsForRage", () => {
  it("dedupes by hint key, sums counts, and respects the cap", () => {
    const out = hintsForRage(
      [
        { target: "button|approve a", count: 2 },
        { target: "button|Approve b", count: 1 },
        { target: "button|stamp seal 盖印", count: 3 },
        { target: "div|nothing matches the rules here", count: 4 },
        { target: "span|still nothing", count: 1 },
      ],
      2,
    );
    expect(out).toHaveLength(2);
    expect(out[0].key).toBe("approve");
    expect(out[0].count).toBe(3);
    expect(out[1].key).toBe("tour-seal");
    expect(out[1].count).toBe(3);
  });
});
