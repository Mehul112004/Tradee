import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowUpRight,
  Download,
  ArrowRight,
  Play,
  ShieldCheck,
  Activity,
  SlidersHorizontal,
  LockKeyhole,
  RefreshCw,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "./context";
import { comparisonSamples } from "./analysis-view";
import {
  useResource,
  request,
  fmt,
  percent,
  short,
  query,
  number,
  download,
  type Doc,
} from "./api";
import {
  Heading,
  Panel,
  Metric,
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Table,
  Time,
  Json,
  Hash,
  SearchInput,
  Tabs,
  Money,
} from "./components";
import { TimePlot, Bars, CandleChart, Plot } from "./charts";
import {
  PortfolioDiagnostics,
  SignalDiagnostics,
  ResearchDiagnostics,
  ModelDiagnostics,
  ForwardDiagnostics,
  OperationsDiagnostics,
  ReplayControls,
  Distribution,
} from "./diagnostics";

function useSession() {
  const c = useWorkspace();
  return useResource<Doc>(
    c.workspace,
    `sessions/${encodeURIComponent(c.session)}?${query({ at_ms: c.at })}`,
    !!c.session,
  );
}
function usePortfolio() {
  const c = useWorkspace();
  return useResource<Doc>(
    c.workspace,
    `sessions/${encodeURIComponent(c.session)}/portfolio?${query({ at_ms: c.at })}`,
    !!c.session,
  );
}
function SignalTable({
  rows,
  onRow,
}: {
  rows: Doc[];
  onRow?: (d: Doc) => void;
}) {
  return (
    <Table
      rows={rows}
      onRow={onRow}
      keyOf={(s) => s.signal_id}
      columns={[
        {
          label: "Instrument",
          render: (s) => (
            <span className="instrument">
              <span
                className={
                  "coin " +
                  (s.candidate.symbol.startsWith("BTC") ? "btc" : "eth")
                }
              >
                {s.candidate.symbol.startsWith("BTC") ? "₿" : "Ξ"}
              </span>
              <b>{s.candidate.symbol}</b>
            </span>
          ),
        },
        {
          label: "Side / timeframe",
          render: (s) => (
            <>
              <Badge tone={s.candidate.side === "long" ? "good" : "bad"}>
                {s.candidate.side}
              </Badge>
              <small className="block">
                {s.trade_intent?.candidate?.timeframe || s.candidate.timeframe}
              </small>
            </>
          ),
        },
        {
          label: "Paper decision",
          render: (s) => (
            <Badge tone={s.decision?.status === "admitted" ? "purple" : "warn"}>
              {s.decision?.status || s.phase}
            </Badge>
          ),
        },
        {
          label: "Lower net R",
          render: (s) =>
            fmt(s.decision?.prediction?.uncertainty?.lower_mean_net_r, 3),
        },
        { label: "Lifecycle", render: (s) => <Badge>{s.phase}</Badge> },
        { label: "Detected", render: (s) => <Time value={s.detected_ms} /> },
        {
          label: "Telegram",
          render: (s) => <Badge>{s.delivery?.state || "No outbox"}</Badge>,
        },
      ]}
    />
  );
}

export function Overview() {
  const c = useWorkspace();
  const { data: s, error } = useSession();
  const { data: p } = usePortfolio();
  const signals = [...(s?.signals || [])].sort(
    (a, b) =>
      b.detected_ms - a.detected_ms || a.signal_id.localeCompare(b.signal_id),
  );
  const sessions = c.overview?.sessions || [];
  const m = p?.report?.metrics;
  return (
    <>
      <Heading
        eyebrow="WORKSPACE / OVERVIEW"
        title="Your research. In focus."
        sub="A clear view of market evidence, paper capital, and the decisions behind every signal."
        action={
          <Link className="button primary" to={"/markets" + location.search}>
            Open market workspace
            <ArrowUpRight size={16} />
          </Link>
        }
      />
      <ErrorBox error={error} />
      {!c.session ? (
        <Empty title="Connect your first recording">
          <p>
            This workspace has no C14 sessions yet. The Data page shows
            configured sources; Operations provides explicit jobs and setup
            instructions.
          </p>
          <Link className="button primary" to={"/operations" + location.search}>
            Set up a session
            <ArrowRight size={15} />
          </Link>
        </Empty>
      ) : (
        <>
          <div className="metrics">
            <Metric
              label="Paper equity"
              value={fmt(p?.risk?.equity_usdt)}
              sub="USDT · shared hypothetical wallet"
            />
            <Metric
              label="Net paper P&L"
              value={<Money value={m?.net_pnl_usdt} />}
              sub={
                m
                  ? `${percent(m.total_return_fraction)} total return`
                  : "No funded report"
              }
            />
            <Metric
              label="Funded positions"
              value={p?.account?.positions?.length ?? "—"}
              sub={`${p?.trades?.length ?? 0} historical admissions`}
            />
            <Metric
              label="Signal candidates"
              value={signals.length}
              sub={`${signals.filter((x: Doc) => x.decision?.status === "admitted").length} admitted · full rejection history retained`}
            />
          </div>
          <div className="grid main-split">
            <Panel
              title="Paper capital trajectory"
              sub="C13 · mark-based equity and cash, in USDT"
              action={<Badge tone="purple">Shared wallet</Badge>}
            >
              <div className="chart-stat">
                <strong>
                  {fmt(p?.risk?.equity_usdt)}
                  <small> USDT</small>
                </strong>
                <span className="positive">
                  {percent(m?.total_return_fraction)}{" "}
                  <small>over this recording</small>
                </span>
              </div>
              <TimePlot
                rows={p?.samples || []}
                series={[
                  {
                    key: "equity_usdt",
                    name: "Paper equity",
                    color: "#a58bff",
                  },
                  { key: "cash_usdt", name: "Cash", color: "#4bbaa7" },
                ]}
                label="Shared paper wallet equity and cash"
              />
              <div className="panel-foot">
                Source <Hash value={p?.report_hash} />
                <span>
                  As of <Time value={s?.cycle?.as_of_ms} />
                </span>
              </div>
            </Panel>
            <Panel
              title="Needs your attention"
              sub="Evidence and operation checks"
            >
              <div className="attention">
                <span className="status-icon amber">
                  <Activity size={17} />
                </span>
                <div>
                  <b>
                    {s?.paused
                      ? "Session is paused"
                      : "Session accepts paper ticks"}
                  </b>
                  <p>
                    {s?.paused
                      ? "Review the audit and data freshness before resuming."
                      : "Only explicit paper processing is enabled."}
                  </p>
                </div>
              </div>
              <div className="attention">
                <span className="status-icon violet">
                  <ShieldCheck size={17} />
                </span>
                <div>
                  <b>Paper evidence only</b>
                  <p>
                    Research estimates and simulated fills do not authorize live
                    trading.
                  </p>
                </div>
              </div>
              <div className="attention">
                <span className="status-icon blue">
                  <RefreshCw size={17} />
                </span>
                <div>
                  <b>Check source age</b>
                  <p>
                    Last market evidence: <Time value={s?.cycle?.as_of_ms} />.
                    Freshness is separate from service connectivity.
                  </p>
                </div>
              </div>
              <Link className="text-link" to={"/forward" + location.search}>
                Review forward evidence <ArrowRight size={14} />
              </Link>
            </Panel>
          </div>
          <Panel
            title="Signal activity"
            sub="Every candidate, including capital rejections"
            action={
              <Link className="text-link" to={"/signals" + location.search}>
                Explore signals <ArrowUpRight size={14} />
              </Link>
            }
          >
            <SignalTable rows={signals.slice(0, 6)} />
          </Panel>
        </>
      )}
      <div className="grid halves">
        <Panel
          title="Evidence stores"
          sub="Standalone stores; some engine evidence is embedded in verified runs"
        >
          <div className="source-grid">
            {c.overview?.sources?.map((x: Doc) => (
              <div className="source" key={x.component}>
                <span>{x.component.toUpperCase()}</span>
                <i
                  className={
                    "dot " +
                    (x.state === "available"
                      ? "green"
                      : x.state === "integrity_error"
                        ? "red"
                        : "")
                  }
                />
                <small>{x.state.replaceAll("_", " ")}</small>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Deployments" sub="Frozen configuration, explicit scope">
          <Table
            rows={sessions}
            columns={[
              { label: "Session", render: (x) => <b>{x.name}</b> },
              { label: "Mode", render: (x) => <Badge>{x.mode}</Badge> },
              {
                label: "State",
                render: (x) => (
                  <Badge tone={x.paused ? "warn" : "good"}>
                    {x.paused ? "Paused" : "Accepting ticks"}
                  </Badge>
                ),
              },
              {
                label: "Producer",
                render: (x) =>
                  x.producer_compatible ? "Compatible" : "Different build",
              },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}

export function Markets() {
  const c = useWorkspace();
  const { data: s } = useSession();
  const datasets = c.overview?.datasets || [];
  const [marketParams] = useSearchParams();
  const ds = marketParams.get("dataset") || "";
  const setDs = (v: string) => c.setParam("dataset", v);
  const symbol = marketParams.get("symbol") || "";
  const setSymbol = (v: string) => c.setParam("symbol", v);
  const tf = ["1m", "15m", "1h", "4h", "1d"].includes(
    marketParams.get("tf") || "",
  )
    ? marketParams.get("tf")!
    : "1m";
  const setTf = (v: string) => c.setParam("tf", v);
  const [overlay, setOverlay] = useState(true);
  const [split, setSplit] = useState(false);
  const [range, setRange] = useState({ start: "", end: "" });
  const dataset =
    datasets.find((d: Doc) => d.dataset_hash === ds) || datasets[0];
  const selected = dataset?.symbols.includes(symbol)
    ? symbol
    : dataset?.symbols[0];
  const resource = useResource<Doc>(
    c.workspace,
    `market?${query({ dataset_hash: dataset?.dataset_hash, symbol: selected, timeframe: tf, at_ms: c.at, start_ms: range.start || null, end_ms: range.end || null })}`,
    !!dataset && !!selected,
  );
  const alternate = dataset?.symbols.find((s: string) => s !== selected);
  const second = useResource<Doc>(
    c.workspace,
    `market?${query({ dataset_hash: dataset?.dataset_hash, symbol: alternate, timeframe: tf, at_ms: c.at, start_ms: range.start || null, end_ms: range.end || null })}`,
    split && !!alternate && !!dataset,
  );
  const m = resource.data;
  const quotes = m?.quotes;
  const [tab, setTab] = useState("Features");
  return (
    <>
      <Heading
        eyebrow="MARKETS / ANALYSIS"
        title="Market workspace"
        sub="Explore the recorded tape. Price, features, and execution context share the same evidence vintage."
      />
      <div className="toolbar">
        <label>
          Dataset
          <select
            aria-label="Market dataset"
            value={dataset?.dataset_hash || ""}
            onChange={(e) => {
              setDs(e.target.value);
              setRange({ start: "", end: "" });
            }}
          >
            {datasets.map((d: Doc) => (
              <option key={d.dataset_hash} value={d.dataset_hash}>
                {short(d.dataset_hash)} · {d.mode} · {d.event_count} events
              </option>
            ))}
          </select>
        </label>
        <label>
          Instrument
          <select
            aria-label="Instrument"
            value={selected || ""}
            onChange={(e) => setSymbol(e.target.value)}
          >
            {dataset?.symbols.map((x: string) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <div className="segmented" aria-label="Timeframe">
          {["1m", "15m", "1h", "4h", "1d"].map((x) => (
            <button
              key={x}
              className={tf === x ? "active" : ""}
              onClick={() => setTf(x)}
            >
              {x}
            </button>
          ))}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={overlay}
            onChange={(e) => setOverlay(e.target.checked)}
          />
          C03 overlays
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={split}
            onChange={(e) => setSplit(e.target.checked)}
          />
          Two-chart workspace
        </label>
      </div>
      <ErrorBox error={resource.error} retry={() => resource.refetch()} />
      {!dataset ? (
        <Empty title="No market datasets recorded" />
      ) : resource.isPending ? (
        <Loading />
      ) : (
        m && (
          <>
            <div className="grid market-split">
              <Panel
                title={selected + " / USDT perpetual"}
                sub="Binance USDⓈ-M · recorded evidence"
                action={<Badge>{tf} closed candles</Badge>}
              >
                <CandleChart
                  key={dataset.dataset_hash + selected + tf}
                  data={m}
                  signals={s?.signals || []}
                  overlay={overlay}
                  syncKey={dataset.dataset_hash + tf}
                />
              </Panel>
              <Panel
                title="Tape context"
                sub="Quote, mark and funding are separate observations"
              >
                <div className="tape-value">
                  <small>Last closed price</small>
                  <strong>{fmt(m.candles.at(-1)?.data.close, 4)}</strong>
                  <Badge tone="purple">Recorded</Badge>
                </div>
                {["quote", "mark", "funding", "trade"].map((k) => (
                  <div className="tape-row" key={k}>
                    <b>{k}</b>
                    {quotes?.[k] ? (
                      <>
                        <Time value={quotes[k].event_ms} />
                        <Json value={quotes[k].data} title="Observation" />
                      </>
                    ) : (
                      <small>Unavailable at cursor</small>
                    )}
                  </div>
                ))}
                <div className="notice">
                  <InfoText text="An open candle or a quote never rewrites a closed candle. Funding shown here is an observation, not a promised future charge." />
                </div>
              </Panel>
            </div>
            {split && second.data && (
              <Panel
                title={alternate + " · synchronized market pane"}
                sub="Compatible dataset and timeframe · UTC"
              >
                <CandleChart
                  key={dataset.dataset_hash + alternate + tf}
                  data={second.data}
                  signals={s?.signals || []}
                  overlay={overlay}
                  syncKey={dataset.dataset_hash + tf}
                />
              </Panel>
            )}
            <div className="grid halves">
              <Panel
                title="Quote spread & observed delay"
                sub="Top-of-book spread in bps; availability delay remains in exact evidence"
              >
                <TimePlot
                  rows={m.quote_series.map((e: Doc) => ({
                    at_ms: e.event_ms,
                    spread_bps: e.spread_bps,
                  }))}
                  series={[{ key: "spread_bps", name: "Spread bps" }]}
                  label="Recorded top of book spread in basis points"
                />
                <Json
                  value={m.quote_series}
                  title="Exact bid, ask, quantities and availability delay"
                />
              </Panel>
              <Panel
                title="Published funding observations"
                sub="Published next rates and historical settlement rates; USDT cash flows remain in trade ledgers"
              >
                <TimePlot
                  rows={m.funding_series.map((e: Doc) => ({
                    at_ms: e.event_ms,
                    published_rate:
                      e.kind === "mark" ? e.data.funding_rate : null,
                    settlement_rate:
                      e.kind === "funding" ? e.data.funding_rate : null,
                  }))}
                  series={[
                    {
                      key: "published_rate",
                      name: "Published next-rate fraction",
                    },
                    {
                      key: "settlement_rate",
                      name: "Historical settlement-rate fraction",
                    },
                  ]}
                  label="Published and historical settlement funding rate fractions, not USDT cash flows"
                />
                <Json
                  value={m.funding_series}
                  title="Funding observation, forecast horizon and source"
                />
              </Panel>
            </div>
            <Panel
              title="Evidence context"
              sub={`Availability: ${m.availability_basis} · source cutoff and chart range are explicit`}
            >
              <Tabs
                values={["Features", "Coverage & gaps", "Source"]}
                active={tab}
                onChange={setTab}
              />
              {tab === "Features" ? (
                m.features.length ? (
                  <Table
                    rows={m.features.slice(-20).reverse()}
                    columns={[
                      {
                        label: "Target bar",
                        render: (f) => <Time value={f.target_open_ms} />,
                      },
                      {
                        label: "Features",
                        render: (f) => (
                          <Json
                            value={f.values}
                            title={Object.keys(f.values).join(", ")}
                          />
                        ),
                      },
                      {
                        label: "Evaluation",
                        render: (f) => <Time value={f.evaluation_as_of_ms} />,
                      },
                    ]}
                  />
                ) : (
                  <Empty title="Indicators have not been materialized for this vintage">
                    Run a C03 feature job in Operations. The browser does not
                    approximate the indicators.
                  </Empty>
                )
              ) : tab === "Coverage & gaps" ? (
                <>
                  <div className="metrics compact">
                    <Metric
                      label="Returned bars"
                      value={m.coverage.returned_bars}
                    />
                    <Metric
                      label="Final minute keys"
                      value={m.coverage.final_minutes}
                    />
                    <Metric label="Gap intervals" value={m.gaps.length} />
                    <Metric
                      label="Provisional observations"
                      value={m.provisional.length}
                    />
                  </div>
                  <div className="range-inputs">
                    <label>
                      Range start · epoch ms
                      <input
                        value={range.start}
                        onChange={(e) =>
                          setRange({ ...range, start: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Range end · epoch ms
                      <input
                        value={range.end}
                        onChange={(e) =>
                          setRange({ ...range, end: e.target.value })
                        }
                      />
                    </label>
                    <button onClick={() => setRange({ start: "", end: "" })}>
                      Reset range
                    </button>
                  </div>
                  <Json value={m.gaps} title="Gap intervals" />
                </>
              ) : (
                <Json
                  value={{
                    dataset: m.dataset,
                    start_ms: m.start_ms,
                    end_ms: m.end_ms,
                    as_of_ms: m.as_of_ms,
                    coverage: m.coverage,
                    feature_source: m.feature_source,
                    feature_manifest: m.feature_manifest,
                  }}
                  title="Dataset and range provenance"
                />
              )}
            </Panel>
          </>
        )
      )}
    </>
  );
}
function InfoText({ text }: { text: string }) {
  return <p>{text}</p>;
}

export function Signals() {
  const c = useWorkspace();
  const { data: s, error, isPending } = useSession();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All");
  const [selected, setSelected] = useState<Doc | null>(null);
  const [count, setCount] = useState(50);
  const rows = (s?.signals || []).filter(
    (x: Doc) =>
      (status === "All" || x.decision?.status === status.toLowerCase()) &&
      JSON.stringify([
        x.candidate.symbol,
        x.candidate.hypothesis_family,
        x.signal_id,
        x.decision?.reasons,
      ])
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  rows.sort(
    (a: Doc, b: Doc) =>
      b.detected_ms - a.detected_ms || a.signal_id.localeCompare(b.signal_id),
  );
  const current = selected
    ? s?.signals.find((x: Doc) => x.signal_id === selected.signal_id)
    : null;
  return (
    <>
      <Heading
        eyebrow="DECISIONS / SIGNALS"
        title="From setup to decision."
        sub="Inspect the thesis, conditional expectancy, execution costs, and capital constraints behind each candidate."
        action={
          c.session ? (
            <a
              className="button"
              href={`/api/${c.workspace}/sessions/${c.session}/export?format=csv`}
            >
              <Download size={15} />
              Export CSV
            </a>
          ) : undefined
        }
      />
      <ErrorBox error={error} />
      {isPending && c.session ? (
        <Loading />
      ) : (
        <>
          {s && <ReplayControls session={s} />}
          <Panel
            title="Signal ledger"
            sub={`${rows.length} matching candidates · includes rejected and expired history`}
          >
            <div className="toolbar">
              <Tabs
                values={["All", "Admitted", "Rejected"]}
                active={status}
                onChange={setStatus}
              />
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder="Symbol, reason, or signal ID…"
              />
            </div>
            <SignalTable rows={rows.slice(0, count)} onRow={setSelected} />
            {rows.length > count && (
              <button onClick={() => setCount(count + 50)}>Load 50 more</button>
            )}
          </Panel>
          {current && (
            <div className="detail-panel" aria-label="Signal detail">
              <Panel
                title={`${current.candidate.symbol} · ${current.candidate.side}`}
                sub={current.candidate.hypothesis_family.replaceAll("_", " ")}
                action={
                  <button onClick={() => setSelected(null)}>Close</button>
                }
              >
                <div className="metrics">
                  <Metric
                    label="Conditional mean net R"
                    value={fmt(
                      current.decision?.prediction?.statistics?.mean_net_r,
                      3,
                    )}
                    sub="Mature simulated fills in fitted cohort"
                  />
                  <Metric
                    label="95% bootstrap interval"
                    value={`${fmt(current.decision?.prediction?.uncertainty?.lower_mean_net_r, 3)} – ${fmt(current.decision?.prediction?.uncertainty?.upper_mean_net_r, 3)}`}
                    sub="Research estimate · not a guarantee"
                  />
                  <Metric
                    label="Entry cost estimate"
                    value={fmt(
                      current.decision?.execution?.costs
                        ?.execution_plus_fee_cost_usdt,
                      4,
                    )}
                    sub="USDT · one execution leg"
                  />
                  <Metric
                    label="Paper net outcome"
                    value={fmt(current.paper_outcome?.net_usdt, 4)}
                    sub={
                      current.paper_outcome?.label_status ||
                      "No funded outcome for this candidate"
                    }
                  />
                </div>
                <div className="notice">
                  <InfoText
                    text={
                      current.decision?.reasons?.length
                        ? "Admission reasons: " +
                          current.decision.reasons.join(", ")
                        : "No rejection reason recorded. The empirical positive-net fraction is not a calibrated confidence score."
                    }
                  />
                </div>
                <SignalDiagnostics signal={current} />
                <Json
                  value={current.decision?.prediction}
                  title="Expectancy cohort and uncertainty"
                />
                <Json
                  value={current.trade_intent?.feature_snapshot}
                  title="Decision-time C03 feature snapshot"
                />
                <Json
                  value={current.decision?.execution}
                  title="Execution, spread, fees and next-funding estimate"
                />
                <Json
                  value={current.paper_outcome}
                  title="Paper path, fills and mature outcome"
                />
                <Json
                  value={current.delivery}
                  title="Telegram delivery receipt"
                />
                <Json value={current} title="Full signal provenance" />
              </Panel>
            </div>
          )}
        </>
      )}
    </>
  );
}

export function Portfolio() {
  const context = useWorkspace();
  const { data: p, error, isPending } = usePortfolio();
  const [tab, setTab] = useState("Funded trades");
  const [trade, setTrade] = useState<Doc | null>(null);
  const exposure = p?.risk?.exposure || {};
  const metrics = p?.report?.metrics;
  return (
    <>
      <Heading
        eyebrow="CAPITAL / PAPER PORTFOLIO"
        title="One wallet. Every constraint."
        sub="C13 admits candidates against shared capital. These are hypothetical paper results, including fees and settled funding."
      />
      <ErrorBox error={error} />
      {!context.session ? (
        <Empty title="No funded session selected" />
      ) : isPending ? (
        <Loading />
      ) : !p?.available ? (
        <Empty title="No funded paper cycle available" />
      ) : (
        <>
          <div className="metrics">
            <Metric
              label="Paper equity"
              value={fmt(p.risk.equity_usdt)}
              sub="USDT · marked shared wallet"
            />
            <Metric
              label="Cash balance"
              value={fmt(p.account.cash_usdt)}
              sub="USDT · after fees and settled funding"
            />
            <Metric
              label="Total return"
              value={percent(metrics.total_return_fraction)}
              sub="From initial paper capital"
            />
            <Metric
              label="Max drawdown"
              value={percent(metrics.max_drawdown_fraction)}
              sub={`${fmt(metrics.max_drawdown_usdt)} USDT · regular samples`}
            />
          </div>
          <div className="grid main-split">
            <Panel
              title="Equity & cash"
              sub="Actual C13 valuation samples; unknown marks break the line"
            >
              <TimePlot
                rows={p.samples}
                series={[
                  { key: "equity_usdt", name: "Equity", color: "#a58bff" },
                  { key: "cash_usdt", name: "Cash", color: "#46cab1" },
                  {
                    key: "unrealized_gross_usdt",
                    name: "Unrealized gross",
                    color: "#5ca8f6",
                  },
                ]}
                label="Portfolio equity cash and unrealized PnL"
              />
            </Panel>
            <Panel
              title="Current risk budget"
              sub="USDT · reservations included"
            >
              <div className="risk-list">
                {[
                  "gross_notional_usdt",
                  "stop_risk_usdt",
                  "collateral_reserved_usdt",
                  "free_collateral_usdt",
                  "worst_stress_loss_usdt",
                ].map((k) => (
                  <div key={k}>
                    <span>{k.replace("_usdt", "").replaceAll("_", " ")}</span>
                    <b>{fmt(exposure[k])}</b>
                  </div>
                ))}
              </div>
              <Badge tone={p.risk.ready ? "good" : "warn"}>
                {p.risk.ready
                  ? "Risk evidence ready"
                  : "Risk evidence incomplete"}
              </Badge>
            </Panel>
          </div>
          <div className="grid halves">
            <Panel
              title="Capital rejections"
              sub="A candidate can fail several constraints"
            >
              <Bars
                label="Portfolio rejection reasons"
                values={Object.entries(p.report.coverage.rejection_reasons).map(
                  ([name, value]) => ({
                    name: name.replaceAll("_", " "),
                    value,
                  }),
                )}
              />
            </Panel>
            <Panel
              title="Stress scenarios"
              sub="Signed paper PnL under frozen policy assumptions"
            >
              <Bars
                label="Portfolio stress scenario PnL"
                values={Object.entries(exposure.stress_pnl_usdt || {}).map(
                  ([name, value]) => ({
                    name: name.replaceAll("_", " "),
                    value,
                  }),
                )}
              />
            </Panel>
          </div>
          <PortfolioDiagnostics />
          <Panel
            title="Portfolio inventory"
            sub="Funded trade results remain separate from independent C11 hypotheses"
          >
            <Tabs
              values={["Funded trades", "Open positions", "Policy & account"]}
              active={tab}
              onChange={setTab}
            />
            {tab === "Funded trades" ? (
              <Table
                rows={p.trades}
                onRow={setTrade}
                columns={[
                  {
                    label: "Instrument",
                    render: (t) => <b>{t.outcome.state.symbol}</b>,
                  },
                  {
                    label: "Admitted",
                    render: (t) => <Time value={t.admitted_ms} />,
                  },
                  {
                    label: "Outcome",
                    render: (t) => <Badge>{t.outcome.label_status}</Badge>,
                  },
                  {
                    label: "Net USDT",
                    render: (t) => <Money value={t.outcome.net_usdt} />,
                  },
                  { label: "Fees", render: (t) => fmt(t.outcome.fees_usdt, 4) },
                  {
                    label: "Funding",
                    render: (t) => fmt(t.outcome.funding_usdt, 4),
                  },
                  { label: "Net R", render: (t) => fmt(t.outcome.net_r, 3) },
                ]}
              />
            ) : tab === "Open positions" ? (
              <Table
                rows={p.account.positions}
                columns={[
                  { label: "Symbol", render: (t) => t.symbol },
                  { label: "Position", render: (t) => <Json value={t} /> },
                ]}
                empty="No open paper positions"
              />
            ) : (
              <>
                <Json value={p.policy} title="Frozen risk policy" />
                <Json value={p.account} title="Paper account state" />
                <Json value={metrics} title="Core portfolio metrics" />
              </>
            )}
            {trade && (
              <>
                <div className="panel-head">
                  <h3>Funded trade evidence</h3>
                  <button onClick={() => setTrade(null)}>Close trade</button>
                </div>
                <Json
                  value={trade}
                  title="Fills, path, fees, funding and source run"
                />
              </>
            )}
          </Panel>
        </>
      )}
    </>
  );
}

export function Research() {
  const c = useWorkspace();
  const { data: experiments, error } = useResource<Doc[]>(
    c.workspace,
    "research",
  );
  const { data: runs } = useResource<Doc[]>(c.workspace, "runs");
  const { data: models } = useResource<Doc[]>(c.workspace, "models");
  const [tab, setTab] = useState("Experiments");
  const [experiment, setExperiment] = useState("");
  const [run, setRun] = useState("");
  const [compare, setCompare] = useState("");
  const [search, setSearch] = useState("");
  const exp = useResource<Doc>(
    c.workspace,
    `research/${experiment}`,
    !!experiment,
  );
  const detail = useResource<Doc>(c.workspace, `runs/${run}`, !!run);
  const other = useResource<Doc>(c.workspace, `runs/${compare}`, !!compare);
  const r = detail.data;
  const values = (runs || []).filter((x) => !x.locked);
  const rows = values.filter((x) =>
    JSON.stringify([x.run_hash, x.scenarios])
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  if (c.at !== null)
    return (
      <>
        <Heading
          eyebrow="RESEARCH / ARCHIVE"
          title="Choose an artifact review context"
          sub="Research reports use their pinned protocol and publication vintages. The session knowledge cursor is a different scope."
        />
        <Empty title="Research archive is outside the session replay">
          <button onClick={() => c.setParam("at", "")}>
            Leave decision cursor and open research archive
          </button>
        </Empty>
      </>
    );
  return (
    <>
      <Heading
        eyebrow="RESEARCH / VALIDATION"
        title="Evidence before conviction."
        sub="Reproducible runs, chronological validation, and cohort uncertainty. Holdout access stays explicit and audited."
      />
      <ErrorBox error={error || exp.error || detail.error || other.error} />
      <Tabs
        values={["Experiments", "Simulation runs", "Models"]}
        active={tab}
        onChange={setTab}
      />
      {tab === "Experiments" ? (
        <>
          <Panel
            title="Experiment registry"
            sub="Frozen hypotheses, fold definitions, and release decisions"
          >
            <Table
              rows={experiments || []}
              onRow={(x) => setExperiment(x.experiment_hash)}
              columns={[
                { label: "Experiment", render: (x) => <b>{x.name}</b> },
                { label: "Family", render: (x) => x.family },
                {
                  label: "Holdout",
                  render: (x) => (
                    <Badge tone={x.locked ? "warn" : "purple"}>
                      {x.locked ? "Locked" : "Opened / audited"}
                    </Badge>
                  ),
                },
                {
                  label: "Decision",
                  render: (x) => x.decision?.status || "Not exposed",
                },
                { label: "Live approval", render: () => <Badge>None</Badge> },
              ]}
            />
          </Panel>
          {exp.data && (
            <Panel
              title={exp.data.manifest.experiment.name}
              sub="Frozen experimental contract"
            >
              <ResearchDiagnostics experiment={exp.data} />
              <Json
                value={
                  exp.data.manifest.experiment.folds ||
                  exp.data.manifest.experiment
                }
                title="Chronological folds, purge, embargo and holdout contract"
              />
              {exp.data.locked ? (
                <div className="notice">
                  <LockKeyhole size={18} />
                  <p>
                    Holdout results are locked across run, chart, and artifact
                    routes. Opening requires an operator command with the exact
                    experiment hash.
                  </p>
                </div>
              ) : (
                <Json
                  value={exp.data.decision}
                  title="Research release decision"
                />
              )}
              {exp.data.artifacts.map((a: Doc) => (
                <Json key={a.key} value={a.document} title={a.key} />
              ))}
              <Json value={exp.data.events} title="Research audit trail" />
            </Panel>
          )}
        </>
      ) : tab === "Simulation runs" ? (
        <>
          <Panel
            title="Independent candidate runs"
            sub="Overlapping hypotheses do not share capital"
          >
            <div className="toolbar">
              <SearchInput value={search} onChange={setSearch} />
              <label>
                Compare with
                <select
                  aria-label="Compare run"
                  value={compare}
                  onChange={(e) => setCompare(e.target.value)}
                >
                  <option value="">No comparison</option>
                  {values.map((x) => (
                    <option key={x.run_hash} value={x.run_hash}>
                      {short(x.run_hash)} · {x.metrics.candidates} candidates
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <Table
              rows={rows}
              onRow={(x) => setRun(x.run_hash)}
              columns={[
                {
                  label: "Run",
                  render: (x) => (
                    <span className="mono">{short(x.run_hash)}</span>
                  ),
                },
                { label: "Candidates", render: (x) => x.metrics.candidates },
                {
                  label: "Mature / unresolved",
                  render: (x) =>
                    `${x.metrics.mature} / ${x.metrics.unresolved}`,
                },
                {
                  label: "Mean net R",
                  render: (x) => fmt(x.metrics.mean_net_r, 3),
                },
                {
                  label: "Net subtotal",
                  render: (x) => <Money value={x.metrics.net_usdt} />,
                },
                {
                  label: "Dataset",
                  render: (x) => <Hash value={x.dataset.dataset_hash} />,
                },
              ]}
            />
            {(runs || []).some((x) => x.locked) && (
              <p className="muted padded">
                Locked holdout runs are omitted from inspection.
              </p>
            )}
          </Panel>
          {r && (
            <>
              <Panel
                title="Run inspection"
                sub="C11 independent evaluation · PnL is not account equity"
                action={
                  <button onClick={() => download(r, "simulation-run.json")}>
                    <Download size={14} />
                    Export evidence
                  </button>
                }
              >
                <div className="metrics">
                  <Metric
                    label="Mature outcomes"
                    value={r.summary.metrics.mature}
                  />
                  <Metric
                    label="Unresolved"
                    value={r.summary.metrics.unresolved}
                  />
                  <Metric
                    label="Mean net R"
                    value={fmt(r.summary.metrics.mean_net_r, 3)}
                  />
                  <Metric
                    label="Independent net subtotal"
                    value={fmt(r.summary.metrics.net_usdt)}
                    sub="USDT · overlapping hypotheses"
                  />
                </div>
                {other.data && (
                  <div className="notice">
                    <p>
                      <b>Comparison context</b> · dataset{" "}
                      {r.manifest.dataset.dataset_hash ===
                      other.data.manifest.dataset.dataset_hash
                        ? "matches"
                        : "differs"}{" "}
                      · decision window{" "}
                      {JSON.stringify(r.manifest.decision_window_ms) ===
                      JSON.stringify(other.data.manifest.decision_window_ms)
                        ? "matches"
                        : "differs"}{" "}
                      · fee assumptions{" "}
                      {JSON.stringify(r.manifest.fees) ===
                      JSON.stringify(other.data.manifest.fees)
                        ? "match"
                        : "differ"}
                      . Compare the full pinned contracts before ranking
                      results.
                    </p>
                  </div>
                )}
                <TimePlot
                  rows={r.samples}
                  series={[
                    {
                      key: "pnl_usdt",
                      name: "Independent PnL",
                      color: "#9e8bff",
                    },
                  ]}
                  label="Independent candidate PnL, not wallet equity"
                />
                <div className="grid halves">
                  <Bars
                    label="Outcome coverage"
                    values={[
                      "candidates",
                      "filled",
                      "mature",
                      "unfilled",
                      "unresolved",
                    ].map((k) => ({ name: k, value: r.summary.metrics[k] }))}
                  />
                  <Bars
                    label="Cost attribution in USDT"
                    values={[
                      "gross_realized_usdt",
                      "fees_usdt",
                      "known_funding_subtotal_usdt",
                    ].map((k) => ({
                      name: k.replaceAll("_", " "),
                      value: r.report.attribution[k],
                    }))}
                  />
                </div>
                <Distribution data={r.distribution} />
                <Json
                  value={r.manifest}
                  title="Run contract: data, costs, strategy and producer"
                />
                <Json
                  value={r.report}
                  title="Outcome distributions, attribution and grouped evidence"
                />
                {other.data && comparisonSamples(r, other.data) && (
                  <TimePlot
                    rows={comparisonSamples(r, other.data)!}
                    series={[
                      { key: "a", name: "Selected independent PnL" },
                      { key: "b", name: "Compared independent PnL" },
                    ]}
                    label="Compatible independent run PnL comparison in USDT"
                  />
                )}
                {other.data && (
                  <Json value={other.data} title="Comparison run evidence" />
                )}
              </Panel>
            </>
          )}
        </>
      ) : (
        <Panel
          title="Expectancy models"
          sub="Conditional estimates from mature simulated fills; empirical frequency is not calibrated confidence"
        >
          {(models || []).map((m) => (
            <div className="model-block" key={m.model_hash}>
              <div className="panel-head">
                <Hash value={m.model_hash} />
                <Badge tone={m.ready ? "purple" : "warn"}>
                  {m.ready ? "Research model ready" : "Insufficient evidence"}
                </Badge>
              </div>
              <ModelDiagnostics model={m} />
              <Table
                rows={Object.entries(m.cohorts).map(([hash, x]) => ({
                  hash,
                  ...(x as Doc),
                }))}
                columns={[
                  {
                    label: "Cohort",
                    render: (x) =>
                      Object.entries(x.attributes)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · "),
                  },
                  { label: "Mature", render: (x) => x.coverage.mature },
                  {
                    label: "Mean net R",
                    render: (x) => fmt(x.statistics.mean_net_r, 3),
                  },
                  {
                    label: "Bootstrap lower / upper",
                    render: (x) =>
                      `${fmt(x.uncertainty.lower_mean_net_r, 3)} / ${fmt(x.uncertainty.upper_mean_net_r, 3)}`,
                  },
                  { label: "Status", render: (x) => <Badge>{x.status}</Badge> },
                ]}
              />
              <Json
                value={m.model}
                title="Fit protocol, sources and limitations"
              />
            </div>
          ))}
          {!models?.length && <Empty title="No models recorded" />}
        </Panel>
      )}
    </>
  );
}

export function Forward() {
  const c = useWorkspace();
  const { data: monitors, error } = useResource<Doc[]>(c.workspace, "monitors");
  const [name, setName] = useState("");
  const [vintage, setVintage] = useState("");
  const selected = monitors?.find((m) => m.name === name) || monitors?.[0];
  const detail = useResource<Doc>(
    c.workspace,
    `monitors/${selected?.name}?${query({ report_hash: vintage, at_ms: c.at })}`,
    !!selected,
  );
  const f = detail.data;
  const report = f?.report;
  return (
    <>
      <Heading
        eyebrow="VALIDATION / FORWARD REVIEW"
        title="Observe. Then evaluate."
        sub="Prospective paper evidence, fixed statistical reviews, and operational health are tracked separately."
      />
      <ErrorBox error={error || detail.error} />
      <div className="toolbar">
        <label>
          Monitor
          <select
            aria-label="Forward monitor"
            value={selected?.name || ""}
            onChange={(e) => {
              setName(e.target.value);
              setVintage("");
            }}
          >
            {monitors?.map((m) => (
              <option key={m.name}>{m.name}</option>
            ))}
          </select>
        </label>
        <label>
          Report vintage
          <select
            aria-label="Report vintage"
            value={vintage}
            onChange={(e) => setVintage(e.target.value)}
          >
            <option value="">Latest recorded</option>
            {f?.history.map((h: Doc) => (
              <option key={h.report_hash} value={h.report_hash}>
                {short(h.report_hash)} · {h.observed_ms}
              </option>
            ))}
          </select>
        </label>
      </div>
      {selected && !detail.isPending && !report && (
        <Empty title="No forward report recorded by this cursor" />
      )}
      {!selected ? (
        <Empty title="No prospective monitor registered" />
      ) : detail.isPending ? (
        <Loading />
      ) : (
        report && (
          <>
            <div className="metrics">
              <Metric
                label="Forward readiness"
                value={report.ready ? "Ready" : "Insufficient"}
                sub="A review result, never live promotion"
              />
              <Metric
                label="Rows observed"
                value={report.rows.length}
                sub="Independent and funded tracks retained"
              />
              <Metric
                label="Pause requested"
                value={report.pause_requested ? "Yes" : "No"}
                sub="Applying a pause is separately audited"
              />
              <Metric
                label="Report observed"
                value={<Time value={report.observed_ms} />}
                sub="Pinned report vintage"
              />
            </div>
            <div className="grid halves">
              {["independent", "portfolio"].map((k) => (
                <Panel
                  key={k}
                  title={
                    k === "portfolio"
                      ? "Funded paper track"
                      : "Independent hypothesis track"
                  }
                  sub={
                    k === "portfolio"
                      ? "Shared-wallet admissions"
                      : "Includes hypotheses rejected by capital policy"
                  }
                >
                  <Json
                    value={report.summary[k]}
                    title="Coverage, maturity and label summary"
                  />
                  <Bars
                    label={`${k} label statuses`}
                    values={Object.entries(
                      report.summary[k]?.statuses ||
                        report.summary[k]?.label_states ||
                        report.summary[k]?.label_statuses ||
                        {},
                    ).map(([name, value]) => ({ name, value }))}
                  />
                </Panel>
              ))}
            </div>
            <ForwardDiagnostics report={report} />
            <Panel
              title="Fixed review schedule"
              sub="Sparse or incomplete observations remain explicitly insufficient"
            >
              <Table
                rows={report.reviews}
                columns={[
                  {
                    label: "Review",
                    render: (x) =>
                      x.id ||
                      x.review_id ||
                      x.review_ms ||
                      x.at_ms ||
                      "Fixed checkpoint",
                  },
                  {
                    label: "Status",
                    render: (x) => (
                      <Badge tone={x.ready ? "purple" : "warn"}>
                        {x.status || "Insufficient"}
                      </Badge>
                    ),
                  },
                  {
                    label: "Evidence",
                    render: (x) => (
                      <Json value={x} title="Inspect review and bounds" />
                    ),
                  },
                ]}
              />
              <Json
                value={report.health}
                title="Integrity, operational and statistical health"
              />
            </Panel>
            <Panel
              title="Evidence rows & label changes"
              sub="Observation time and mature outcome knowledge are preserved"
            >
              <Table
                rows={report.rows}
                columns={[
                  {
                    label: "Row",
                    render: (x) => (
                      <Hash
                        value={x.signal_id || x.candidate_id || x.row_hash}
                      />
                    ),
                  },
                  {
                    label: "State",
                    render: (x) =>
                      x.label_status || x.status || x.phase || "Inspect source",
                  },
                  {
                    label: "Source evidence",
                    render: (x) => (
                      <Json
                        value={x}
                        title="Observation, revisions and outcome"
                      />
                    ),
                  },
                ]}
              />
              <Json
                value={report.label_changes}
                title="Label revision history"
              />
              <Json
                value={report.telemetry}
                title="Delivery and processing telemetry"
              />
            </Panel>
            <Json value={f.head} title="Monitor contract and report hashes" />
          </>
        )
      )}
    </>
  );
}

export function Data() {
  const c = useWorkspace();
  const { data: instruments, error } = useResource<Doc[]>(
    c.workspace,
    "instruments",
  );
  const datasets = c.overview?.datasets || [];
  const [key, setKey] = useState("");
  const [search, setSearch] = useState("");
  const quality = useResource<Doc>(c.workspace, `quality/${key}`, !!key);
  if (c.at !== null)
    return (
      <>
        <Heading
          eyebrow="DATA / ARCHIVE"
          title="Choose a dataset vintage"
          sub="Dataset quality uses the selected immutable dataset cutoff."
        />
        <Empty title="Data catalog is outside the session replay">
          <button onClick={() => c.setParam("at", "")}>
            Leave decision cursor and open dataset catalog
          </button>
        </Empty>
      </>
    );
  return (
    <>
      <Heading
        eyebrow="FOUNDATIONS / DATA"
        title="Know your inputs."
        sub="Instrument versions, recorded datasets, gap evidence and collector receipts. Missing data is never silently filled."
      />
      <ErrorBox error={error || quality.error} />
      <Panel
        title="Dataset catalog"
        sub="Immutable data vintages with explicit availability assumptions"
      >
        <Table
          rows={datasets}
          onRow={(d) => setKey(d.dataset_hash)}
          columns={[
            {
              label: "Dataset",
              render: (d) => (
                <span className="mono">{short(d.dataset_hash)}</span>
              ),
            },
            { label: "Universe", render: (d) => d.symbols.join(" · ") },
            { label: "Events", render: (d) => d.event_count },
            {
              label: "Availability",
              render: (d) => (
                <Badge tone={d.mode === "recorded" ? "purple" : "warn"}>
                  {d.mode}
                </Badge>
              ),
            },
            {
              label: "Source as of",
              render: (d) => <Time value={d.as_of_ms} />,
            },
          ]}
        />
      </Panel>
      {quality.data && (
        <Panel
          title="Dataset quality"
          sub="Gap, revision and provider provenance"
        >
          <Plot
            label="UTC-day minute candle coverage by instrument"
            option={{
              tooltip: { trigger: "item" },
              grid: { bottom: 65, left: 100, right: 45 },
              xAxis: {
                type: "category",
                data: [
                  ...new Set(
                    quality.data.calendar.map((x: Doc) =>
                      new Date(x.day_ms).toISOString().slice(0, 10),
                    ),
                  ),
                ],
              },
              yAxis: {
                type: "category",
                data: quality.data.quality.symbols.map((s: Doc) => s.symbol),
              },
              visualMap: {
                min: 0,
                max: 100,
                calculable: false,
                orient: "horizontal",
                bottom: 0,
                text: ["100%", "0%"],
                inRange: { color: ["#5d3444", "#49405f", "#3c9a83"] },
                textStyle: { color: "#97a6be" },
              },
              series: [
                {
                  type: "heatmap",
                  data: quality.data.calendar.map((x: Doc) => [
                    [
                      ...new Set(
                        quality.data.calendar.map((d: Doc) => d.day_ms),
                      ),
                    ].indexOf(x.day_ms),
                    quality.data.quality.symbols.findIndex(
                      (s: Doc) => s.symbol === x.symbol,
                    ),
                    x.expected ? (100 * x.finalized) / x.expected : null,
                  ]),
                },
              ],
            }}
          />
          <Json
            value={quality.data.calendar}
            title="Exact daily expected / finalized / missing minute counts"
          />
          <Json value={quality.data.quality} title="Quality report" />
          <Json
            value={quality.data.collector}
            title="Recent collector receipts"
          />
          <Json value={quality.data.dataset} title="Pinned dataset contract" />
        </Panel>
      )}
      <Panel
        title="Instrument registry"
        sub="Latest observed C01 contract rules; historical validity is not implied"
      >
        <div className="toolbar">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Find an instrument…"
          />
        </div>
        <Table
          rows={(instruments || []).filter((x) =>
            x.symbol.toLowerCase().includes(search.toLowerCase()),
          )}
          columns={[
            { label: "Instrument", render: (x) => <b>{x.symbol}</b> },
            { label: "Version", render: (x) => <Hash value={x.hash} /> },
            {
              label: "Observed",
              render: (x) => <Time value={x.first_observed_ms} />,
            },
            {
              label: "Contract rules",
              render: (x) => (
                <Json
                  value={x.version}
                  title="Tick, lot, notional and status rules"
                />
              ),
            },
          ]}
        />
      </Panel>
      <Panel
        title="Source availability"
        sub="No GET request initializes or migrates a core store"
      >
        <Table
          rows={c.overview?.sources || []}
          columns={[
            {
              label: "Component",
              render: (x) => <b>{x.component.toUpperCase()}</b>,
            },
            {
              label: "State",
              render: (x) => (
                <Badge tone={x.state === "available" ? "good" : "warn"}>
                  {x.state}
                </Badge>
              ),
            },
            { label: "Schema version", render: (x) => x.schema_version || "—" },
          ]}
        />
      </Panel>
    </>
  );
}

const templates: Record<string, Doc> = {
  refresh_registry: {},
  backfill: { symbol: "BTCUSDT", start_ms: 0, end_ms: 0, kind: "candle" },
  dataset_snapshot: {
    symbols: ["BTCUSDT", "ETHUSDT"],
    start_ms: 0,
    end_ms: 0,
    kinds: ["candle", "quote", "mark", "trade", "funding"],
    mode: "recorded",
    as_of_ms: 0,
  },
  start_runner: {
    session: "",
    monitor: "",
    reason: "",
    expected_revision: 0,
    expected_audit_head: "",
    interval_seconds: 1,
    max_cycles: 3600,
  },
  stop_runner: {
    session: "",
    reason: "",
    expected_revision: 0,
    expected_audit_head: "",
  },
  recover_runner: {
    session: "",
    reason: "",
    expected_revision: 0,
    expected_audit_head: "",
  },
  features: {
    dataset_hash: "",
    config: {
      features: ["ema20", "ema50", "atr14", "rsi14"],
      timeframes: ["15m", "1h", "4h"],
    },
  },
  simulation: {
    dataset_hash: "",
    scenarios: [],
    fees: {},
    execution: {},
    config: {},
  },
  portfolio: { sources: [], models: [], policy: {}, config: {} },
  register_experiment: { experiment: {} },
  research_run: { experiment_hash: "" },
  open_holdout: {
    experiment_hash: "",
    reason: "",
    confirmation: "OPEN <exact experiment hash>",
  },
  apply_pause: {
    session: "",
    monitor: "",
    report_hash: "",
    reason: "",
    expected_revision: 0,
    expected_audit_head: "",
  },
  reconcile_delivery: {
    session: "",
    signal_id: "",
    decision: "",
    proof: "",
    reason: "",
    expected_revision: 0,
    expected_audit_head: "",
  },
  create_session: {
    experiment_hash: "",
    portfolio_run: "",
    spec: {},
    monitor_name: "",
    monitor_policy: {},
  },
  tick: { session: "" },
  forward_observe: { monitor: "" },
  replay: { monitor: "" },
};
export function Operations() {
  const c = useWorkspace();
  const qc = useQueryClient();
  const session = useSession();
  const jobs = useResource<Doc[]>(c.workspace, "jobs");
  const runners = useResource<Doc[]>(c.workspace, "runners");
  const worker = useResource<Doc>(c.workspace, "worker");
  const [tab, setTab] = useState("Sessions & controls");
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState("features");
  const [body, setBody] = useState(JSON.stringify(templates.features, null, 2));
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [requestKey, setRequestKey] = useState(crypto.randomUUID());
  async function submit(k: string, d: Doc) {
    setBusy(true);
    setMessage("");
    try {
      const r = await request<Doc>(`${c.workspace}/commands/${k}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + c.token,
          "Idempotency-Key": requestKey,
        },
        body: JSON.stringify(d),
      });
      setMessage(
        `Operation ${short(r.id)} · ${r.state}. The separate worker executes admitted requests.`,
      );
      setRequestKey(crypto.randomUUID());
      setConfirmed(false);
      qc.invalidateQueries({ queryKey: [c.workspace] });
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const s = session.data;
  return (
    <>
      <Heading
        eyebrow="OPERATIONS / CONTROL ROOM"
        title="Deliberate operations."
        sub="Viewer access is the default. Every operator command is explicit, durable, and separate from viewing evidence."
      />
      <div className="notice">
        <ShieldCheck size={18} />
        <p>
          Paper and shadow workflows only. This dashboard has no exchange-order
          or Telegram-send endpoint. A collector and the durable job worker run
          as separately owned processes.
        </p>
      </div>
      <Tabs
        values={[
          "Sessions & controls",
          "Research & data jobs",
          "Job history",
          "Setup",
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "Sessions & controls" ? (
        <Panel
          title="Current session"
          sub="Revision and audit-head checks reject stale controls"
        >
          <ErrorBox error={session.error} />
          {s ? (
            <>
              <div className="metrics">
                <Metric label="Session" value={s.name} sub={s.mode} />
                <Metric
                  label="Status"
                  value={s.paused ? "Paused" : "Accepting paper ticks"}
                />
                <Metric label="Revision" value={s.revision} />
                <Metric
                  label="Audit head"
                  value={<Hash value={s.audit_head} />}
                />
              </div>
              <label className="field">
                Reason for the control
                <input
                  placeholder="Explain the operational reason…"
                  value={reason}
                  onChange={(e) => {
                    setReason(e.target.value);
                    setRequestKey(crypto.randomUUID());
                    setConfirmed(false);
                  }}
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I reviewed the session, current source age and intended state.
              </label>
              <div className="toolbar">
                <button
                  className="primary"
                  disabled={
                    !c.token ||
                    !confirmed ||
                    reason.trim().length < 5 ||
                    c.at !== null ||
                    busy
                  }
                  onClick={() =>
                    submit(s.paused ? "resume" : "pause", {
                      session: c.session,
                      reason,
                      expected_revision: s.revision,
                      expected_audit_head: s.audit_head,
                    })
                  }
                >
                  {s.paused
                    ? "Resume paper processing"
                    : "Pause paper processing"}
                </button>
                <button
                  disabled={
                    !c.token ||
                    !confirmed ||
                    reason.trim().length < 5 ||
                    c.at !== null ||
                    busy
                  }
                  onClick={() =>
                    submit("recover", {
                      session: c.session,
                      reason,
                      expected_revision: s.revision,
                      expected_audit_head: s.audit_head,
                    })
                  }
                >
                  Recover uncertain delivery claims
                </button>
              </div>
              <p className="muted">
                Controls require a current view and an operator token set in
                Settings. Resuming does not start a collector or tick loop.
              </p>
              <OperationsDiagnostics session={s} />
              <Json value={s.manifest} title="Frozen deployment contract" />
              <Json value={s.events} title="Session audit trail" />
            </>
          ) : (
            <Empty title="Select or create a session" />
          )}
        </Panel>
      ) : tab === "Research & data jobs" ? (
        <Panel
          title="Explicit core jobs"
          sub="Edit and review a typed core document. No artifact selection occurs automatically."
        >
          <div className="toolbar">
            <label>
              Operation
              <select
                aria-label="Operation kind"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  const template = { ...templates[e.target.value] };
                  if ("session" in template) template.session = c.session;
                  if ("expected_revision" in template) {
                    template.expected_revision = s?.revision;
                    template.expected_audit_head = s?.audit_head;
                    template.reason = reason;
                  }
                  if ("monitor" in template)
                    template.monitor = c.overview?.monitors?.[0]?.name || "";
                  if ("dataset_hash" in template)
                    template.dataset_hash =
                      s?.cycle?.dataset?.dataset_hash ||
                      c.overview?.datasets?.[0]?.dataset_hash ||
                      "";
                  setBody(JSON.stringify(template, null, 2));
                  setConfirmed(false);
                  setRequestKey(crypto.randomUUID());
                }}
              >
                {Object.keys(templates).map((k) => (
                  <option key={k} value={k}>
                    {k.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted">
            Use the frozen configuration formats from the core component
            documentation. These templates show required inputs; empty contracts
            are rejected by the worker.
          </p>
          <textarea
            aria-label="Command JSON"
            className="code-input"
            rows={15}
            value={body}
            onChange={(e) => {
              setBody(e.target.value);
              setConfirmed(false);
              setRequestKey(crypto.randomUUID());
            }}
          />
          <label className="check">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I reviewed this exact command and its workspace. Holdout opening is
            irreversible.
          </label>
          <button
            className="primary"
            disabled={!c.token || !confirmed || busy || c.at !== null}
            onClick={() => {
              try {
                submit(kind, JSON.parse(body));
              } catch {
                setMessage(
                  "Invalid JSON; correct the command before submitting",
                );
              }
            }}
          >
            <Play size={14} />
            Queue core job
          </button>
        </Panel>
      ) : tab === "Job history" ? (
        <Panel
          title="Durable job history"
          sub="Queued, running, completed, failed and interrupted states"
        >
          <Table
            rows={jobs.data || []}
            columns={[
              { label: "Operation", render: (x) => <b>{x.kind}</b> },
              {
                label: "State",
                render: (x) => (
                  <Badge
                    tone={
                      x.state === "succeeded"
                        ? "good"
                        : x.state === "failed"
                          ? "bad"
                          : "neutral"
                    }
                  >
                    {x.state}
                  </Badge>
                ),
              },
              {
                label: "Created",
                render: (x) => <Time value={x.created_ms} />,
              },
              {
                label: "Receipt",
                render: (x) => <Json value={x} title="Request and result" />,
              },
              {
                label: "Action",
                render: (x) =>
                  x.state === "queued" ? (
                    <button
                      disabled={!c.token || c.at !== null}
                      onClick={async () => {
                        try {
                          await request(`${c.workspace}/jobs/${x.id}/cancel`, {
                            method: "POST",
                            headers: { Authorization: "Bearer " + c.token },
                          });
                          jobs.refetch();
                        } catch (e) {
                          setMessage((e as Error).message);
                        }
                      }}
                    >
                      Cancel queued
                    </button>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
        </Panel>
      ) : (
        <Panel
          title="Run locally"
          sub="Both applications stay in this repository"
        >
          <ol className="setup">
            <li>
              <b>Activate the environment</b>
              <code>conda activate tradee</code>
            </li>
            <li>
              <b>Start the local API and built dashboard</b>
              <code>python -m backend.tradee_web</code>
            </li>
            <li>
              <b>Run the owned job worker in another terminal</b>
              <code>python -m backend.tradee_web.worker</code>
            </li>
            <li>
              <b>Collect or import data with the core C01/C02 CLI</b>
              <p>
                Choose the configured database paths, publish an explicit
                dataset, then queue features or research jobs. See
                docs/dashboard/DASHBOARD_RUNBOOK.md for complete commands and
                configuration.
              </p>
            </li>
          </ol>
          <div className="notice">
            <p>
              The verification workspace contains synthetic retained E2E
              artifacts. It tests engineering behavior and provides no evidence
              of a profitable live strategy.
            </p>
          </div>
        </Panel>
      )}
      <Panel
        title="Process ownership"
        sub="Job worker, paper runner and market collector are separate roles"
      >
        <div className="padded">
          <Badge tone={worker.data?.state === "connected" ? "good" : "warn"}>
            Job worker: {worker.data?.state || "checking"}
          </Badge>
          <p className="muted">
            Stopping a paper runner stops future ticks. Pausing notifications
            leaves the paper book running. Collectors remain independently owned
            core processes.
          </p>
        </div>
        <Table
          rows={runners.data || []}
          columns={[
            { label: "Session", render: (r) => r.session },
            {
              label: "State",
              render: (r) => (
                <Badge tone={r.heartbeat_stale ? "warn" : "neutral"}>
                  {r.state}
                  {r.heartbeat_stale ? " · stale heartbeat" : ""}
                </Badge>
              ),
            },
            { label: "Cycles", render: (r) => r.cycles },
            {
              label: "Heartbeat",
              render: (r) => <Time value={r.heartbeat_ms} />,
            },
            {
              label: "Ownership",
              render: (r) => (
                <Json value={r} title="Runner reservation and bounded policy" />
              ),
            },
          ]}
        />
      </Panel>
      {message && (
        <div className="notice" role="status">
          <p>{message}</p>
        </div>
      )}
    </>
  );
}

export function Settings() {
  const c = useWorkspace();
  const [value, setValue] = useState("");
  return (
    <>
      <Heading
        eyebrow="PREFERENCES / SETTINGS"
        title="Your workspace defaults."
        sub="Display settings stay in the URL. Operator authorization stays in memory and is cleared on reload."
      />
      <Panel title="Display & access" sub="Local deployment">
        <div className="settings-grid">
          <label className="field">
            Timezone
            <select
              value={c.zone}
              onChange={(e) => c.setParam("zone", e.target.value)}
            >
              {[
                "UTC",
                "Asia/Kolkata",
                Intl.DateTimeFormat().resolvedOptions().timeZone,
              ]
                .filter((v, i, a) => a.indexOf(v) === i)
                .map((z) => (
                  <option key={z}>{z}</option>
                ))}
            </select>
          </label>
          <div>
            <label className="field">
              Operator token
              <input
                type="password"
                autoComplete="off"
                value={value}
                placeholder="Paste the locally configured token"
                onChange={(e) => setValue(e.target.value)}
              />
            </label>
            <div className="toolbar">
              <button
                className="primary"
                disabled={!value}
                onClick={() => {
                  c.setToken(value);
                  setValue("");
                }}
              >
                Enable operator requests
              </button>
              <button onClick={() => c.setToken("")}>
                Clear authorization
              </button>
            </div>
            <Badge tone={c.token ? "warn" : "neutral"}>
              {c.token ? "Operator token held in memory" : "Viewer mode"}
            </Badge>
          </div>
        </div>
        <p className="muted">
          Set TRADEE_WEB_OPERATOR_TOKEN in the API process environment. The
          backend never returns it; the browser sends it only in an
          Authorization header.
        </p>
      </Panel>
      <Panel title="About this evidence" sub="Scope and interpretation">
        <p className="padded">
          Tradee analyzes Binance USDT perpetual futures for intraday and swing
          hypotheses. C11 evaluates independent candidates; C13 shares finite
          paper capital; C15 observes prospective evidence. A ready research
          artifact is never live-trading approval.
        </p>
        <Json
          value={{
            workspace: c.workspace,
            session: c.session,
            view: c.at === null ? "latest_recorded" : "decision_as_of",
            at_ms: c.at,
            connection: c.connection,
          }}
          title="Current view context"
        />
      </Panel>
    </>
  );
}
