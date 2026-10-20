import { describe, it, expect } from "vitest";
import {
  variantMatrix,
  compatibleRuns,
  comparisonSamples,
} from "./analysis-view";
describe("published research visualization", () => {
  const e = {
    manifest: {
      experiment: {
        variants: [
          { name: "a", parameters: { lookback: 20, target: 2 } },
          { name: "b", parameters: { lookback: 30, target: 2 } },
        ],
      },
    },
    artifacts: [
      {
        key: "final/selection",
        document: {
          scores: [
            { variant: "a", evidence: { utility_r_per_candidate: ".2" } },
            { variant: "b", evidence: { utility_r_per_candidate: null } },
          ],
        },
      },
    ],
  };
  it("plots only existing scores and preserves the evidence", () => {
    const m = variantMatrix(e)!;
    expect(m.cells).toHaveLength(1);
    expect(m.cells[0].value).toBe(0.2);
    expect(m.cells[0].evidence).toEqual(
      e.artifacts[0].document.scores[0].evidence,
    );
  });
  it("does not average duplicate parameter cells", () => {
    const d = structuredClone(e);
    d.manifest.experiment.variants.push({
      name: "c",
      parameters: { lookback: 20, target: 2 },
    });
    d.artifacts[0].document.scores.push({
      variant: "c",
      evidence: { utility_r_per_candidate: ".5" },
    });
    expect(variantMatrix(d)).toBeNull();
  });
  it("a fixed hypothesis is not an invented parameter grid", () => {
    expect(
      variantMatrix({
        manifest: { experiment: { variants: [{ name: "a", parameters: {} }] } },
        artifacts: [],
      }),
    ).toBeNull();
  });
  const a = {
    manifest: {
      dataset: { hash: "a" },
      decision_window_ms: [0, 10],
      fees: { rate: ".001" },
      execution: { kind: "quote" },
      code_hash: "same",
      scenarios: [{ quantity: "1" }],
    },
    samples: [
      { at_ms: 1, pnl_usdt: "2" },
      { at_ms: 2, pnl_usdt: null },
    ],
  };
  it("compares only matching units and contracts, retaining valuation gaps", () => {
    const b = structuredClone(a);
    b.samples = [{ at_ms: 3, pnl_usdt: "3" }];
    expect(compatibleRuns(a, b)).toBeTruthy();
    expect(comparisonSamples(a, b)).toEqual([
      { at_ms: 1, a: "2", b: null },
      { at_ms: 2, a: null, b: null },
      { at_ms: 3, a: null, b: "3" },
    ]);
  });
  it("refuses to rescale a different tested quantity", () => {
    const b = structuredClone(a);
    b.manifest.scenarios[0].quantity = "2";
    expect(comparisonSamples(a, b)).toBeNull();
  });
});
