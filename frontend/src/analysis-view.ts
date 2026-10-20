import { number, type Doc } from "./api";
/** A view of already-published scores. Never creates trials or recalculates utility. */
export function variantMatrix(experiment: Doc) {
  const variants: Doc[] = experiment.manifest.experiment.variants;
  const keys = [
    ...new Set<string>(variants.flatMap((v) => Object.keys(v.parameters))),
  ];
  const selection = experiment.artifacts.find(
    (a: Doc) => a.key === "final/selection",
  )?.document;
  if (keys.length < 2 || !selection?.scores?.length) return null;
  const axes = keys.slice(0, 2);
  const x = [...new Set(variants.map((v) => String(v.parameters[axes[0]])))];
  const y = [...new Set(variants.map((v) => String(v.parameters[axes[1]])))];
  const cells: Doc[] = [];
  const seen = new Set<string>();
  for (const score of selection.scores) {
    const v = variants.find((v) => v.name === score.variant);
    const value = number(score.evidence?.utility_r_per_candidate);
    if (!v || value === null) continue;
    const i = x.indexOf(String(v.parameters[axes[0]])),
      j = y.indexOf(String(v.parameters[axes[1]]));
    const key = `${i}/${j}`;
    if (seen.has(key)) return null;
    seen.add(key);
    cells.push({
      x: i,
      y: j,
      value,
      variant: v.name,
      evidence: score.evidence,
    });
  }
  return cells.length ? { axes, x, y, cells } : null;
}
export function compatibleRuns(a: Doc, b: Doc) {
  const fields = [
    "dataset",
    "decision_window_ms",
    "fees",
    "execution",
    "code_hash",
  ];
  return (
    fields.every(
      (k) => JSON.stringify(a.manifest[k]) === JSON.stringify(b.manifest[k]),
    ) &&
    JSON.stringify(a.manifest.scenarios.map((s: Doc) => s.quantity)) ===
      JSON.stringify(b.manifest.scenarios.map((s: Doc) => s.quantity))
  );
}
export function comparisonSamples(a: Doc, b: Doc) {
  if (!compatibleRuns(a, b)) return null;
  const points = new Map<number, Doc>();
  for (const r of a.samples)
    points.set(r.at_ms, { at_ms: r.at_ms, a: r.pnl_usdt, b: null });
  for (const r of b.samples)
    points.set(r.at_ms, {
      ...(points.get(r.at_ms) || { at_ms: r.at_ms, a: null }),
      b: r.pnl_usdt,
    });
  return [...points.values()].sort((a, b) => a.at_ms - b.at_ms);
}
