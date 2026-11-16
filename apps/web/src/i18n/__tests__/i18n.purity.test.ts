import { describe, expect, it } from "vitest";

import { STRINGS } from "../strings";

// The parity test proves the two locales cover the same keys; this test proves
// neither locale carries the other's script — a screen must never be a mix of
// Chinese and English (owner's bilingual rule, #1909).
//
// Rules
// -----
// en: no CJK unified ideographs, no CJK punctuation (「」、。，；：（）…), no fullwidth forms.
//     Em dashes (—) and middle dots (·) are typography, not Chinese script — allowed.
// zh: no run composed only of English link-words (the / and / of / to / with / …) —
//     an English sentence pasted into the Chinese table stands out this way.
//     Product names (SpecProof, LLM, HTTP, RBAC …) are not link-words and stay allowed.

const CJK_ANY = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]/;
const EN_LINK_RUN = /\b(?:the|and|of|to|with|for|your|not|is|are|that|this|never|from|into)(?:\s+\b(?:the|and|of|to|with|for|your|not|is|are|that|this|never|from|into)\b){2,}/i;

describe("i18n content purity — no script leaks across locales", () => {
  it("the English table contains zero CJK characters or CJK punctuation", () => {
    const offenders: Array<[string, string]> = [];
    for (const [key, value] of Object.entries(STRINGS.en)) {
      if (CJK_ANY.test(value)) offenders.push([key, value]);
    }
    expect(offenders).toEqual([]);
  });

  it("the Chinese table contains no English link-word sentence runs", () => {
    const offenders: Array<[string, string]> = [];
    for (const [key, value] of Object.entries(STRINGS.zh)) {
      if (EN_LINK_RUN.test(value)) offenders.push([key, value]);
    }
    expect(offenders).toEqual([]);
  });

  it("the Chinese table does not quote Chinese text inside ASCII quotes copied from English", () => {
    // Deliberately light-weight: zh keeps its own fullwidth quotes; if a value
    // wraps CJK in straight ASCII quotes it is almost always a paste artefact.
    const offenders: Array<[string, string]> = [];
    for (const [key, value] of Object.entries(STRINGS.zh)) {
      const hits = value.match(/"[^"\n]*[\u4e00-\u9fff][^"\n]*"/g) ?? [];
      for (const hit of hits) {
        // bare interpolation markers like "{verdict}" are fine — they hold no CJK
        offenders.push([key, hit]);
      }
    }
    expect(offenders).toEqual([]);
  });
});
