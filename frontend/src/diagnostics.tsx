import { useEffect, useState } from "react";
import { useWorkspace } from "./context";
import { useResource, number, query, type Doc } from "./api";
import { Panel, Json, Table, Badge, Empty, Hash, Time } from "./components";
import { Bars, Plot, TimePlot, CandleChart } from "./charts";
import { variantMatrix } from "./analysis-view";
export function Distribution({ data }: { data: Doc }) {
  return (
    <>
      <Bars
        label={`Mature net R distribution, n=${data.mature}; omitted ${data.omitted}`}
        values={data.bins.map((b: Doc) => ({ name: b.name, value: b.count }))}
      />
      <p className="muted padded">
        {data.mature} mature outcomes · {data.omitted} unresolved/unknown
        omitted · fixed net-R bins
      </p>
      <Json value={data.bins} title="Exact rows in each distribution bin" />
    </>
  );
}
export function PortfolioDiagnostics() {
  const c = useWorkspace();
  const { data, error } = useResource<Doc>(
    c.workspace,
    `sessions/${c.session}/analytics?${query({ at_ms: c.at })}`,
    !!c.session,
  );
  const f = data?.funded;
  if (error || !f?.drawdown) return null;
  return (
    <>
      <div className="grid halves">
        <Panel
          title="Drawdown from known peak"
          sub="USDT · initial capital baseline; unknown valuations stay gaps"
        >
          <TimePlot
            rows={f.drawdown}
            series={[
              { key: "drawdown_usdt", name: "Drawdown USDT", color: "#d57e9a" },
            ]}
            label="Funded wallet drawdown in USDT"
          />
          <Json value={f.drawdown} title="Exact drawdown samples and units" />
        </Panel>
        <Panel
          title="Risk versus frozen limits"
          sub="Current value and equity-scaled policy limit, in USDT"
        >
          <Plot
            label="Risk usage versus frozen limits in USDT"
            option={{
              xAxis: {
                type: "category",
                data: f.risk.map((r: Doc) =>
                  r.name.replace("_usdt", "").replaceAll("_", " "),
                ),
                axisLabel: { fontSize: 9, rotate: 15 },
              },
              yAxis: {
                type: "value",
                splitLine: { lineStyle: { color: "#202938" } },
              },
              legend: { textStyle: { color: "#96a6bc" } },
              series: [
                {
                  name: "Value",
                  type: "bar",
                  data: f.risk.map((r: Doc) => number(r.value)),
                },
                {
                  name: "Limit",
                  type: "bar",
                  data: f.risk.map((r: Doc) => number(r.limit)),
                },
              ],
            }}
          />
          <Json value={f.risk} title="Exact values, limits and contributors" />
        </Panel>
      </div>
      <div className="grid halves">
        <Panel
          title="Funded net-R distribution"
          sub="Mature admissions only; exact rows remain available"
        >
          <Distribution data={f.distribution} />
        </Panel>
        <Panel
          title="Evidence lineage"
          sub="Curated references for the selected paper cycle"
        >
          <div className="lineage">
            {data!.lineage.nodes.map((n: Doc, i: number) => (
              <div key={n.hash}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <b>{n.label}</b>
                  <small>{n.kind.toUpperCase()}</small>
                </div>
                <Hash value={n.hash} />
              </div>
            ))}
          </div>
          <Json value={data!.lineage} title="Lineage and access scope" />
        </Panel>
      </div>
    </>
  );
}
export function SignalDiagnostics({ signal }: { signal: Doc }) {
  const c = useWorkspace();
  const d = signal;
  const candidate = d.candidate;
  const snapshot = d.trade_intent?.feature_snapshot;
  const dataset = snapshot?.dataset_hash;
  const data = useResource<Doc>(
    c.workspace,
    `market?${query({ dataset_hash: dataset, symbol: candidate.symbol, timeframe: candidate.timeframe, at_ms: c.at, start_ms: Math.max(0, candidate.context_start_ms - 600000), end_ms: d.paper_outcome?.outcome_known_ms ? d.paper_outcome.outcome_known_ms + 60000 : candidate.expires_ms })}`,
    !!dataset,
  );
  const events = [
    {
      kind: "detected",
      event: candidate.detected_ms,
      available: snapshot?.evaluation_as_of_ms,
      recorded: d.recording?.first_detection_ms,
    },
    {
      kind: "admission",
      event: d.entry_ms,
      available: d.decision?.admitted_ms,
      recorded: d.recording?.first_admission_ms,
    },
    {
      kind: "outcome known",
      event: d.paper_outcome?.outcome_known_ms,
      available: d.paper_outcome?.outcome_known_ms,
      recorded: d.recording?.first_outcome_ms,
    },
    {
      kind: "Telegram attempt",
      event: d.delivery?.attempted_ms,
      available: d.delivery?.updated_ms,
      recorded: null,
    },
  ].filter((e) => e.event != null);
  return (
    <>
      <Panel
        title="Trade context · retrospective paper review"
        sub="Actual recorded OHLCV; selected as-of cursor still limits available evidence"
      >
        {data.data ? (
          <CandleChart data={data.data} signals={[signal]} />
        ) : (
          <Empty title="Chart evidence not available for this cursor" />
        )}
      </Panel>
      <Plot
        label="Signal event time and availability time in UTC"
        height={220}
        option={{
          xAxis: { type: "time" },
          yAxis: { type: "category", data: events.map((e) => e.kind) },
          series: [
            {
              name: "Event time",
              type: "scatter",
              symbolSize: 10,
              data: events.map((e, i) => [e.event, i]),
            },
            {
              name: "Source usable time",
              type: "scatter",
              symbol: "diamond",
              symbolSize: 9,
              data: events
                .filter((e) => e.available != null)
                .map((e) => [e.available, events.indexOf(e)]),
            },
          ],
          legend: { top: 0, textStyle: { color: "#99a5ba" } },
        }}
      />
      <Table
        rows={events}
        columns={[
          { label: "Transition", render: (e) => e.kind },
          { label: "Event time", render: (e) => <Time value={e.event} /> },
          { label: "C14 recorded", render: (e) => <Time value={e.recorded} /> },
          {
            label: "Source usable time",
            render: (e) => <Time value={e.available} />,
          },
        ]}
      />
    </>
  );
}
export function ResearchDiagnostics({ experiment }: { experiment: Doc }) {
  const matrix = variantMatrix(experiment);
  const contract = experiment.manifest.experiment;
  const splits = [
    ...contract.folds.map((f: Doc) => f.split),
    contract.holdout.split,
  ];
  const artifacts = experiment.artifacts;
  const development = artifacts.find(
    (a: Doc) => a.key === "report/development",
  )?.document;
  const folds = development?.evidence?.groups?.fold || {};
  const evidence = artifacts
    .filter((a: Doc) => a.document.evidence?.uncertainty)
    .map((a: Doc) => ({ name: a.key, ...a.document.evidence }));
  return (
    <>
      <div className="grid halves">
        <Panel
          title="Chronological ownership"
          sub="UTC windows · train / test; holdout contract visible, results gated"
        >
          <Plot
            label="Training and evaluation fold boundaries in UTC"
            option={{
              xAxis: { type: "time" },
              yAxis: { type: "category", data: splits.map((s) => s.name) },
              legend: { textStyle: { color: "#99a8be" } },
              series: ["train", "test"].map((kind, i) => ({
                name: kind,
                type: "line",
                showSymbol: true,
                lineStyle: { width: 9, opacity: 0.6 },
                data: splits.flatMap((s: Doc, j: number) => [
                  [s[kind].start_ms, j],
                  [s[kind].end_ms, j],
                  [null, null],
                ]),
              })),
            }}
          />
          <Json
            value={splits}
            title="Exact split boundaries, purge and cutoff contract"
          />
        </Panel>
        <Panel
          title="Development fold utility"
          sub="Selected net R / all candidate opportunities; not mean funded R"
        >
          <Bars
            label="Development utility R per candidate by fold"
            values={Object.entries(folds).map(([name, v]) => ({
              name,
              value: (v as Doc).utility_r_per_candidate,
            }))}
          />
          <Json
            value={development?.evidence}
            title="Producer interval, coverage and trial budget"
          />
        </Panel>
      </div>
      <Panel
        title="Development parameter matrix"
        sub="Published final-selection utility R per candidate; registered variants only"
      >
        {matrix ? (
          <Plot
            label="Registered two-parameter development utility heatmap"
            option={{
              tooltip: { trigger: "item" },
              xAxis: { type: "category", name: matrix.axes[0], data: matrix.x },
              yAxis: { type: "category", name: matrix.axes[1], data: matrix.y },
              visualMap: {
                min: Math.min(...matrix.cells.map((c) => c.value)),
                max: Math.max(...matrix.cells.map((c) => c.value)),
                orient: "horizontal",
                bottom: 0,
                inRange: { color: ["#77495e", "#716499", "#6acbb2"] },
              },
              series: [
                {
                  type: "heatmap",
                  data: matrix.cells.map((c) => [c.x, c.y, c.value]),
                },
              ],
            }}
          />
        ) : (
          <Empty title="No eligible two-parameter score grid">
            A fixed hypothesis, missing scores, or duplicate parameter cells
            cannot support this heatmap. Exact variants and stress evidence stay
            inspectable.
          </Empty>
        )}
        <Json
          value={matrix?.cells || contract.variants}
          title="Registered cells, scores and source evidence"
        />
      </Panel>
      <Panel
        title="Stored evidence intervals"
        sub="Producer utility R per opportunity · only published bounds"
      >
        <Plot
          label="Stored research utility and lower upper bounds"
          option={{
            xAxis: { type: "category", data: evidence.map((e: Doc) => e.name) },
            yAxis: { type: "value", scale: true },
            legend: { textStyle: { color: "#99a8be" } },
            series: [
              {
                name: "Utility",
                type: "scatter",
                symbolSize: 12,
                data: evidence.map((e: Doc) =>
                  number(e.utility_r_per_candidate),
                ),
              },
              {
                name: "Lower bound",
                type: "scatter",
                symbol: "rect",
                data: evidence.map((e: Doc) => number(e.uncertainty.lower)),
              },
              {
                name: "Upper bound",
                type: "scatter",
                symbol: "rect",
                data: evidence.map((e: Doc) => number(e.uncertainty.upper)),
              },
            ],
          }}
        />
        <Json
          value={contract.variants.map((v: Doc) => ({
            name: v.name,
            parameters: v.parameters,
            neighbor_of: v.neighbor_of,
            stress_of: v.stress_of,
          }))}
          title="Registered variants and stress neighborhood"
        />
      </Panel>
    </>
  );
}
export function ModelDiagnostics({ model }: { model: Doc }) {
  const cohorts: Doc[] = Object.entries(model.cohorts).map(([hash, c]) => ({
    hash,
    ...(c as Doc),
  }));
  return (
    <>
      <Plot
        label="Conditional cohort mean net R and stored block bootstrap bounds"
        option={{
          xAxis: {
            type: "category",
            data: cohorts.map((c) => Object.values(c.attributes).join(" / ")),
          },
          yAxis: { type: "value", scale: true },
          legend: { textStyle: { color: "#96a5b9" } },
          series: [
            {
              name: "Mean net R",
              type: "scatter",
              symbolSize: 11,
              data: cohorts.map((c) => number(c.statistics.mean_net_r)),
            },
            {
              name: "Lower",
              type: "scatter",
              symbol: "rect",
              data: cohorts.map((c) => number(c.uncertainty.lower_mean_net_r)),
            },
            {
              name: "Upper",
              type: "scatter",
              symbol: "rect",
              data: cohorts.map((c) => number(c.uncertainty.upper_mean_net_r)),
            },
          ],
        }}
      />
      {(model.evaluations || []).length === 0 ? (
        <Empty title="No frozen later-period scoring artifact">
          Reliability and net-R error diagnostics require a published C10 frozen
          evaluation. Cohort positive fractions alone are not calibration
          evidence.
        </Empty>
      ) : (
        (model.evaluations || []).map((e: Doc) => (
          <div key={e.evaluation_hash}>
            <Plot
              label="Stored empirical frequency reliability diagnostics"
              option={{
                tooltip: { trigger: "item" },
                xAxis: {
                  type: "value",
                  min: 0,
                  max: 1,
                  name: "Mean empirical prediction",
                },
                yAxis: {
                  type: "value",
                  min: 0,
                  max: 1,
                  name: "Observed positive fraction",
                },
                series: [
                  {
                    type: "scatter",
                    symbolSize: 12,
                    data: e.metrics.reliability_bins.map((b: Doc) => [
                      number(b.mean_empirical_prediction),
                      number(b.observed_positive_fraction),
                      b.count,
                    ]),
                  },
                ],
              }}
            />
            <Json
              value={e}
              title="Frozen scoring: matched denominator, net-R errors and reliability bins"
            />
          </div>
        ))
      )}
    </>
  );
}

export function ForwardDiagnostics({ report }: { report: Doc }) {
  const r = report;
  const reviews = r.reviews || [];
  const tracks = ["independent", "portfolio"];
  return (
    <>
      <div className="grid halves">
        <Panel
          title="Fixed review bounds"
          sub="Stored admitted mean net R and bounds; missing bounds stay empty"
        >
          <Plot
            label="Fixed review net R mean and stored intervals"
            option={{
              xAxis: { type: "time" },
              yAxis: { type: "value", scale: true },
              legend: { textStyle: { color: "#96a5b9" } },
              series: [
                {
                  name: "Admitted mean net R",
                  type: "scatter",
                  symbolSize: 10,
                  data: reviews.map((v: Doc) => [
                    v.deadline_ms,
                    number(v.mean_net_r),
                  ]),
                },
                {
                  name: "Lower",
                  type: "scatter",
                  symbol: "rect",
                  data: reviews.map((v: Doc) => [
                    v.deadline_ms,
                    number(v.net_lower),
                  ]),
                },
                {
                  name: "Upper",
                  type: "scatter",
                  symbol: "rect",
                  data: reviews.map((v: Doc) => [
                    v.deadline_ms,
                    number(v.net_upper),
                  ]),
                },
              ],
            }}
          />
          <Json
            value={reviews}
            title="Review evidence and insufficient-data reasons"
          />
        </Panel>
        <Panel
          title="Forward maturity coverage"
          sub="Track denominators are distinct; no automatic pooling"
        >
          <Bars
            label="Forward row counts by independent and portfolio track"
            values={tracks.map((k) => ({
              name: k + " rows",
              value: r.summary[k].count,
            }))}
          />
          <Json
            value={r.summary}
            title="Exact track counts, maturity states and net subtotals"
          />
        </Panel>
      </div>
      <Panel
        title="Frozen forecast versus observed paper label"
        sub="Matched rows only · descriptive net R; no new significance test"
      >
        <Plot
          label="Frozen C10 mean net R versus mature paper net R"
          option={{
            tooltip: { trigger: "item" },
            xAxis: {
              type: "value",
              name: "Frozen prediction · net R",
              scale: true,
            },
            yAxis: { type: "value", name: "Mature paper net R", scale: true },
            series: tracks.map((track) => ({
              name: track,
              type: "scatter",
              symbolSize: 9,
              data: r.rows
                .filter(
                  (x: Doc) =>
                    x.track === track &&
                    x.status === "mature" &&
                    number(x.predicted_mean_net_r) !== null &&
                    number(x.net_r) !== null,
                )
                .map((x: Doc) => [
                  Number(x.predicted_mean_net_r),
                  Number(x.net_r),
                ]),
            })),
            legend: { textStyle: { color: "#96a5b9" } },
          }}
        />
        <p className="muted padded">
          This compares each frozen prediction with its paper label. It does not
          pool backtest and forward periods or certify calibration.
        </p>
      </Panel>
    </>
  );
}
export function OperationsDiagnostics({ session }: { session: Doc }) {
  const cycles = session.cycles || [];
  const events = session.events || [];
  const rows = cycles.map((x: Doc) => ({
    at_ms: x.as_of_ms,
    processing_ms: x.processing_ms,
  }));
  const kinds = [...new Set(events.map((e: Doc) => e.kind))];
  return (
    <div className="grid halves">
      <Panel
        title="Processing latency"
        sub={`${rows.length} measured paper cycles · milliseconds, no human/fill latency`}
      >
        <TimePlot
          rows={rows}
          series={[{ key: "processing_ms", name: "Cycle processing ms" }]}
          label="Measured processing milliseconds by paper cycle"
        />
        <Json
          value={cycles}
          title="Exact cycle timings and publication clocks"
        />
      </Panel>
      <Panel
        title="Operational audit history"
        sub="Recorded time · explicit state transitions"
      >
        <Plot
          label="Recorded operational state transition history"
          option={{
            xAxis: { type: "time" },
            yAxis: { type: "category", data: kinds },
            series: [
              {
                type: "scatter",
                symbolSize: 8,
                data: events.map((e: Doc) => [
                  e.recorded_ms,
                  kinds.indexOf(e.kind),
                ]),
              },
            ],
          }}
        />
        <Json value={events} title="Exact operational audit records" />
      </Panel>
    </div>
  );
}
export function ReplayControls({ session }: { session: Doc }) {
  const c = useWorkspace();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const clocks = [
    ...new Set<number>(
      session.replay_clocks ||
        session.cycles.map((x: Doc) => Math.max(x.as_of_ms, x.recorded_ms)),
    ),
  ].sort((a, b) => a - b);
  const index =
    c.at === null ? clocks.length - 1 : clocks.findIndex((t) => t >= c.at!);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = clocks.find((t) => t > (c.at ?? 0));
      if (next === undefined) setPlaying(false);
      else c.setParam("at", String(next));
    }, 1000 / speed);
    return () => clearInterval(id);
  }, [playing, speed, c.at, clocks.join(",")]);
  return (
    <div className="toolbar padded">
      <Badge>Recorded cycle replay</Badge>
      <button
        onClick={() => c.setParam("at", String(clocks[Math.max(0, index - 1)]))}
        disabled={!clocks.length || index <= 0}
      >
        Previous cycle
      </button>
      <button
        onClick={() => {
          if (c.at === null) c.setParam("at", String(clocks[0]));
          setPlaying(!playing);
        }}
        disabled={!clocks.length}
      >
        {playing ? "Pause replay" : "Play replay"}
      </button>
      <button
        onClick={() =>
          c.setParam(
            "at",
            String(clocks[Math.min(clocks.length - 1, index + 1)]),
          )
        }
        disabled={!clocks.length || index >= clocks.length - 1}
      >
        Next cycle
      </button>
      <select
        aria-label="Replay speed"
        value={speed}
        onChange={(e) => setSpeed(Number(e.target.value))}
      >
        {[1, 2, 4].map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
      <button
        onClick={() => {
          setPlaying(false);
          c.setParam("at", "");
        }}
      >
        Latest recorded
      </button>
    </div>
  );
}
