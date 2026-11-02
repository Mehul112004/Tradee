import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  Plus,
  Pause,
  Square,
  RefreshCw,
  Bell,
  ChartCandlestick,
} from "lucide-react";
import { useWorkspace } from "./context";
import { request, fmt, date, type Doc } from "./api";
import { Badge, Panel, Table, Time, Json } from "./components";
import { CandleChart } from "./charts";

const names: Record<string, string> = {
  prior_range_breakout: "Range breakout",
  ema_pullback_continuation: "EMA pullback",
  liquidity_sweep_v1: "Liquidity sweep",
  ema200_rejection_v1: "200 EMA rejection",
  key_level_retest_v1: "Key-level retest",
};
const phaseNames: Record<string, string> = {
  preparing: "Preparing candles",
  waiting_stream: "Waiting for Binance stream",
  watching: "Watching for setups",
  warming_up: "Waiting for enough complete candles",
  paused: "Paused",
  interrupted: "Data interrupted",
  completed: "Completed",
  stopped: "Stopped",
};
const deliveryNames: Record<string, string> = {
  historical: "History only",
  disabled: "Alerts off",
  pending: "Queued",
  sending: "Sending",
  sent: "Telegram accepted",
  ambiguous: "Delivery uncertain",
  failed: "Delivery failed",
  expired: "Too old to send",
  suppressed: "Suppressed while paused",
  unqualified: "Execution checks blocked",
};

export function Analysis() {
  const c = useWorkspace();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [auth, setAuth] = useState("");
  const [form, setForm] = useState({
    name: "My analysis",
    symbols: "BTCUSDT",
    timeframe: "15m",
    mode: "live",
    history_bars: 500,
    telegram: false,
  });
  const [strategies, setStrategies] = useState(["prior_range_breakout"]);
  const hasPilot = strategies.some((s) =>
    [
      "liquidity_sweep_v1",
      "ema200_rejection_v1",
      "key_level_retest_v1",
    ].includes(s),
  );
  const [instrument, setInstrument] = useState("");
  const [focused, setFocused] = useState<Doc | null>(null);
  const catalog = useQuery<Doc>({
    queryKey: [c.workspace, "analysis"],
    queryFn: () => request(`${c.workspace}/analysis`),
    refetchInterval: 3000,
  });
  const sessions: Doc[] = catalog.data?.sessions || [];
  const selected =
    sessions.find((s) => s.id === params.get("analysis")) || sessions[0];
  const detail = useQuery<Doc>({
    queryKey: [c.workspace, "analysis", selected?.id],
    queryFn: () => request(`${c.workspace}/analysis/${selected.id}`),
    enabled: !!selected,
    refetchInterval: 1000,
  });
  const s = detail.data;
  const symbol = s?.spec.symbols.includes(instrument)
    ? instrument
    : s?.spec.symbols[0];
  const market = s?.detail[symbol];
  const historical = s?.spec.mode === "history";
  const configuredSynthetic = catalog.data?.synthetic === true;
  useEffect(() => {
    setCreating(false);
    setFocused(null);
    setInstrument("");
    setError("");
  }, [c.workspace]);
  useEffect(() => {
    setFocused(null);
  }, [selected?.id]);
  const change = (key: string, value: string | number | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${c.token}`,
  };
  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const value = await request<Doc>(`${c.workspace}/analysis`, {
        method: "POST",
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          ...form,
          symbols: form.symbols
            .toUpperCase()
            .split(/[\s,]+/)
            .filter(Boolean),
          strategies,
          telegram: form.mode === "live" && form.telegram,
        }),
      });
      c.setParam("analysis", value.id);
      setCreating(false);
      await qc.invalidateQueries({ queryKey: [c.workspace, "analysis"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function control(action: string) {
    if (!s) return;
    setBusy(true);
    setError("");
    try {
      await request(`${c.workspace}/analysis/${s.id}/control`, {
        method: "POST",
        headers,
        body: JSON.stringify({ action }),
      });
      await qc.invalidateQueries({ queryKey: [c.workspace, "analysis"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const shownMarket = market && {
    ...market,
    forming: focused ? null : market.forming,
    candles: (focused
      ? market.candles.filter((b: Doc) => b.data.open_ms <= focused.open_ms)
      : market.candles
    ).slice(-500),
    features: focused
      ? market.features.filter((f: Doc) => f.target_open_ms <= focused.open_ms)
      : market.features,
    levels: focused ? focused.levels : market.levels,
    analysis: true,
  };
  const markers = (s?.setups || [])
    .filter(
      (x: Doc) =>
        x.symbol === symbol && (!focused || x.end_ms <= focused.end_ms),
    )
    .map((x: Doc) => ({
      observation: true,
      strategy_name: x.strategy_name,
      candidate: { symbol: x.symbol, target_open_ms: x.open_ms, side: x.side },
    }));
  return (
    <div className="analysis-page">
      <div className="page-heading">
        <div>
          <h1>Analysis sessions</h1>
          <p>
            Choose a market and a strategy. Follow the chart. Get notified when
            its rules match.
          </p>
        </div>
        <button
          className="primary"
          onClick={() => {
            setCreating(true);
            setError("");
          }}
        >
          <Plus size={16} />
          New analysis session
        </button>
      </div>
      <div className="analysis-explainer">
        <ChartCandlestick size={20} />
        <p>
          <b>Your everyday workspace.</b> Watch live markets or scan historical
          candles. Research, portfolio and paper-validation tools remain in the
          sidebar.
        </p>
      </div>
      {(error || catalog.error || detail.error) && (
        <div role="alert" className="notice danger">
          <p>{error || catalog.error?.message || detail.error?.message}</p>
        </div>
      )}
      {configuredSynthetic && (
        <div className="notice">
          <p>
            This workspace contains retained synthetic research. Choose{" "}
            <b>Local recording</b> in the header to start your own analysis, or{" "}
            <Link to={`/overview?workspace=${c.workspace}`}>
              explore the example research
            </Link>
            .
          </p>
        </div>
      )}
      {!c.token && (
        <details
          className="analysis-access"
          open={creating || !sessions.length}
        >
          <summary>Enable session controls</summary>
          <p>
            Use the operator token configured for your local dashboard. It stays
            in browser memory and clears on reload.
          </p>
          {!catalog.data?.operator_enabled && (
            <p>
              Add <code>TRADEE_WEB_OPERATOR_TOKEN</code> to your repository{" "}
              <code>.env</code> and restart the backend. See{" "}
              <Link to={`/settings?workspace=${c.workspace}`}>Settings</Link>.
            </p>
          )}
          <div className="toolbar">
            <label className="field">
              Operator token
              <input
                type="password"
                autoComplete="off"
                value={auth}
                onChange={(e) => setAuth(e.target.value)}
              />
            </label>
            <button
              disabled={!auth}
              onClick={() => {
                c.setToken(auth);
                setAuth("");
              }}
            >
              Enable session controls
            </button>
          </div>
        </details>
      )}
      {(creating || !sessions.length) && (
        <Panel
          title="Start with a strategy"
          sub="The session prepares its candles automatically. No dataset IDs or research models required."
        >
          <form className="analysis-form" onSubmit={create}>
            <div className="analysis-form-grid">
              <label className="field">
                Session name
                <input
                  required
                  maxLength={80}
                  value={form.name}
                  onChange={(e) => change("name", e.target.value)}
                />
              </label>
              <label className="field">
                Instruments
                <input
                  aria-label="Instruments"
                  required
                  value={form.symbols}
                  onChange={(e) => change("symbols", e.target.value)}
                  placeholder="BTCUSDT, ETHUSDT, SOLUSDT"
                />
                <small>
                  Up to five Binance USDT perpetual symbols, separated by
                  commas.
                </small>
              </label>
              <label className="field">
                Strategy timeframe
                <select
                  value={form.timeframe}
                  disabled={hasPilot}
                  onChange={(e) => change("timeframe", e.target.value)}
                >
                  {["1m", "15m", "1h", "4h", "1d"].map((tf) => (
                    <option key={tf}>{tf}</option>
                  ))}
                </select>
                <small>
                  Strategies evaluate only completed candles at this timeframe.
                </small>
              </label>
              <label className="field">
                What would you like to do?
                <select
                  value={form.mode}
                  onChange={(e) => change("mode", e.target.value)}
                >
                  <option value="live">Watch live</option>
                  <option value="history">Scan history</option>
                </select>
                <small>
                  {form.mode === "live"
                    ? "Streams Binance WebSocket candles. Sessions run for up to 24 hours."
                    : "Find past rule matches; this is not a profit or win-rate backtest."}
                </small>
              </label>
            </div>
            <fieldset className="analysis-strategies">
              <legend>Strategies</legend>
              {Object.entries(names).map(([id, name]) => (
                <label className="analysis-strategy" key={id}>
                  <input
                    type="checkbox"
                    checked={strategies.includes(id)}
                    onChange={(e) => {
                      if (
                        e.target.checked &&
                        [
                          "liquidity_sweep_v1",
                          "ema200_rejection_v1",
                          "key_level_retest_v1",
                        ].includes(id)
                      )
                        change("timeframe", "15m");
                      setStrategies((v) =>
                        e.target.checked
                          ? [...v, id]
                          : v.filter((x) => x !== id),
                      );
                    }}
                  />
                  <span>
                    <b>{name}</b>
                    <small>
                      {id === "prior_range_breakout"
                        ? "A candle closes outside the preceding 20-candle range."
                        : id === "ema_pullback_continuation"
                          ? "Price recovers across EMA20 in the EMA20/50 trend direction."
                          : id === "liquidity_sweep_v1"
                            ? "Sweep and reclaim of a known day/swing level; trend pullbacks or proven range edges. BTC/ETH · 15m with automatic 1h context."
                            : id === "ema200_rejection_v1"
                              ? "First controlled return to EMA200 after separation in an established trend. BTC/ETH · 15m / 1h."
                              : "Accepted breakout followed by a distinct first retest in an established trend. BTC/ETH · 15m / 1h."}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
            {form.mode === "history" ? (
              <label className="field">
                Historical candles to scan
                <select
                  value={form.history_bars}
                  onChange={(e) =>
                    change("history_bars", Number(e.target.value))
                  }
                >
                  {[100, 500, 1500].map((n) => (
                    <option key={n} value={n}>
                      Last {n} closed candles
                    </option>
                  ))}
                </select>
                <small>
                  Extra earlier candles are downloaded for indicator warm-up. No
                  Telegram messages are sent.
                </small>
              </label>
            ) : (
              <label className="analysis-notify">
                <input
                  type="checkbox"
                  checked={form.telegram}
                  disabled={!catalog.data?.telegram_configured}
                  onChange={(e) => change("telegram", e.target.checked)}
                />
                <span>
                  <b>
                    <Bell size={14} /> Send setup observations to Telegram
                  </b>
                  <small>
                    {catalog.data?.telegram_configured
                      ? "Uses the bot and chat in your .env. Only new, unexpired setups after preparation are sent."
                      : "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env to enable notifications."}
                  </small>
                </span>
              </label>
            )}
            <p className="muted">
              These are exploratory rule matches. They do not place trades or
              claim a validated edge. Other timeframes are configurable
              experiments; the original engineering presets use 15m.
            </p>
            <div className="toolbar">
              <button
                type="submit"
                className="primary"
                disabled={
                  busy || !c.token || !strategies.length || configuredSynthetic
                }
              >
                <Play size={15} />
                {busy
                  ? "Creating session…"
                  : form.mode === "live"
                    ? "Start watching"
                    : "Scan historical setups"}
              </button>
              {sessions.length > 0 && (
                <button type="button" onClick={() => setCreating(false)}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </Panel>
      )}
      {sessions.length > 0 && (
        <>
          <div className="analysis-session-toolbar">
            <label className="field">
              Analysis session
              <select
                aria-label="Analysis session"
                value={selected?.id || ""}
                onChange={(e) => c.setParam("analysis", e.target.value)}
              >
                {sessions.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.spec.name} · {x.spec.timeframe} ·{" "}
                    {phaseNames[x.phase] || x.phase}
                  </option>
                ))}
              </select>
            </label>
            {s && (
              <div className="toolbar">
                <Badge tone={s.phase === "watching" ? "good" : "warn"}>
                  {phaseNames[s.phase] || s.phase}
                </Badge>
                {s.state === "running" && (
                  <button
                    disabled={!c.token || busy}
                    onClick={() => control("pause")}
                  >
                    <Pause size={14} />
                    Pause
                  </button>
                )}
                {s.state === "paused" && (
                  <button
                    disabled={!c.token || busy}
                    onClick={() => control("resume")}
                  >
                    <Play size={14} />
                    Resume
                  </button>
                )}
                {!["completed", "stopped"].includes(s.state) && (
                  <button
                    disabled={!c.token || busy}
                    onClick={() => control("stop")}
                  >
                    <Square size={14} />
                    Stop
                  </button>
                )}
                <button
                  aria-label="Refresh analysis"
                  onClick={() =>
                    qc.invalidateQueries({
                      queryKey: [c.workspace, "analysis"],
                    })
                  }
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            )}
          </div>
          {s && (
            <>
              {s.message && (
                <div className="notice" role="status">
                  <p>{s.message}</p>
                </div>
              )}
              <div className="analysis-session-summary">
                <p>
                  <b>{s.spec.symbols.join(", ")}</b> · {s.spec.timeframe} ·{" "}
                  {s.spec.strategies.map((x: string) => names[x]).join(" + ")}
                </p>
                <p>
                  {s.setup_count} saved setup observations ·{" "}
                  {historical
                    ? "Historical scan · alerts off"
                    : s.spec.telegram
                      ? "Telegram enabled"
                      : "Telegram off"}{" "}
                  · Updated <Time value={s.updated_ms} />
                </p>
              </div>
              {!market && (
                <div className="analysis-preparing" role="status">
                  <RefreshCw size={20} />
                  <h2>Preparing your market data</h2>
                  <p>
                    Checking instruments and downloading closed candles,
                    including indicator warm-up. Your chart will appear here
                    automatically.
                  </p>
                </div>
              )}
              {market && (
                <>
                  <Panel
                    title="Chart and reference levels"
                    sub="Candles close before a strategy is evaluated. Levels are references, not guaranteed support or resistance."
                    action={
                      <select
                        aria-label="Chart instrument"
                        value={symbol}
                        onChange={(e) => {
                          setInstrument(e.target.value);
                          setFocused(null);
                        }}
                      >
                        {s.spec.symbols.map((x: string) => (
                          <option key={x}>{x}</option>
                        ))}
                      </select>
                    }
                  >
                    <div className="padded">
                      {!historical && (
                        <div className="toolbar">
                          <Badge
                            tone={
                              s.state === "running" &&
                              market.stream?.state === "connected"
                                ? "good"
                                : "warn"
                            }
                          >
                            Binance WebSocket:{" "}
                            {s.state === "running"
                              ? market.stream?.state || "connecting"
                              : s.state}
                          </Badge>
                          {market.stream?.last_price && (
                            <span>
                              Last streamed price:{" "}
                              <b>{fmt(market.stream.last_price, 6)} USDT</b>
                            </span>
                          )}
                          {market.stream?.last_message_ms > 0 && (
                            <span>
                              Last market update{" "}
                              <Time value={market.stream.last_message_ms} />
                            </span>
                          )}
                        </div>
                      )}
                      {Object.entries(market.readiness).map(([id, ready]) => (
                        <Badge
                          key={id}
                          tone={ready && !market.stale ? "good" : "warn"}
                        >
                          {names[id]}:{" "}
                          {market.stale
                            ? "data behind"
                            : ready
                              ? "ready"
                              : "warming up"}
                        </Badge>
                      ))}
                      {market.pilot && (
                        <p className="padded muted">
                          Hourly context: {market.pilot.state}.{" "}
                          {market.pilot.dull
                            ? "Dull activity: new setups blocked. "
                            : ""}
                          {market.pilot.shock
                            ? "Volatility cooldown active. "
                            : ""}
                          {market.pilot.hourly_bars} complete hourly candles
                          prepared. Pilot patterns require fresh execution and
                          calendar checks before alerts. Historical scans
                          measure patterns only.
                          {market.pilot.execution_readiness && (
                            <>
                              {" "}
                              Calendar:{" "}
                              {market.pilot.execution_readiness.calendar}.
                              Clock: {market.pilot.execution_readiness.clock}.
                            </>
                          )}
                        </p>
                      )}
                      <p className="muted">
                        {market.contiguous_bars} consecutive candles available.
                        EMA pullback requires 397. Last candle closed{" "}
                        <Time value={market.last_close_ms} />.{" "}
                        {market.stale
                          ? market.message
                          : historical
                            ? "Historical closed-candle scan."
                            : "Forming candles update the chart only. Setups require a complete candle close."}
                      </p>
                      {focused && (
                        <div className="toolbar">
                          <span>
                            Levels as known at this setup:{" "}
                            {date(focused.end_ms, c.zone)}
                          </span>
                          <button onClick={() => setFocused(null)}>
                            Return to latest chart
                          </button>
                        </div>
                      )}
                    </div>
                    <CandleChart
                      key={`${s.id}-${symbol}`}
                      data={shownMarket}
                      signals={markers}
                    />
                    <div className="analysis-levels">
                      {shownMarket.levels.map((l: Doc) => (
                        <div key={l.label}>
                          <span>{l.label}</span>
                          <b>{fmt(l.price, 6)}</b>
                          <small>
                            Confirmed <Time value={l.confirmed_ms} />
                          </small>
                        </div>
                      ))}
                    </div>
                    <p className="padded muted">
                      Range levels exclude the current candle. Swing levels
                      require two completed candles on each side. Previous-day
                      levels appear only when that full UTC day is covered.
                      Chart shows the latest 500 available candles.
                    </p>
                  </Panel>
                  <Panel
                    title="Detected setups"
                    sub="Latest 200 saved observations. Select a row to inspect its explanation and the levels known at detection."
                  >
                    {s.setups.length ? (
                      <Table
                        rows={s.setups}
                        keyOf={(x) => x.id}
                        onRow={(x) => {
                          setInstrument(x.symbol);
                          setFocused(x);
                        }}
                        columns={[
                          {
                            label: "Instrument",
                            render: (x) => <b>{x.symbol}</b>,
                          },
                          { label: "Strategy", render: (x) => x.strategy_name },
                          {
                            label: "Direction",
                            render: (x) => (
                              <Badge tone={x.side === "long" ? "good" : "bad"}>
                                {x.side}
                              </Badge>
                            ),
                          },
                          {
                            label: "Candle closed",
                            render: (x) => <Time value={x.end_ms} />,
                          },
                          {
                            label: "Trigger level",
                            render: (x) => fmt(x.trigger_level, 6),
                          },
                          {
                            label: "Telegram",
                            render: (x) =>
                              deliveryNames[x.delivery] || x.delivery,
                          },
                        ]}
                      />
                    ) : (
                      <div className="empty">
                        <h3>
                          {s.state === "completed"
                            ? "No setups matched in this scan"
                            : "No setups yet"}
                        </h3>
                        <p>
                          {s.state === "completed"
                            ? "The selected rules did not match this period. That is a valid scan result."
                            : "The session is checking completed candles. A strategy can correctly stay quiet."}
                        </p>
                      </div>
                    )}
                  </Panel>
                  {focused && (
                    <Panel
                      title={`${focused.symbol} · ${focused.strategy_name}`}
                      sub={focused.explanation}
                    >
                      <p className="padded">
                        Reference close: {focused.price} USDT. Trigger:{" "}
                        {focused.trigger_level} USDT. Setup expiry:{" "}
                        <Time value={focused.expires_ms} />.{" "}
                        {deliveryNames[focused.delivery]}. This observation is
                        not an entry fill or a measured outcome.
                      </p>
                      <Json
                        value={focused}
                        title="Inspect saved setup evidence"
                      />
                    </Panel>
                  )}
                </>
              )}
              <details className="analysis-help">
                <summary>What am I looking at?</summary>
                <p>
                  A setup is a match to the chosen strategy rules at a completed
                  candle. The chart marks long and short matches. The levels
                  explain price context; they do not predict a reversal.
                  Scanning history counts matches without measuring
                  profitability, fees or fills.
                </p>
                <p>
                  To evaluate costs and trade outcomes, use{" "}
                  <Link to={`/research?workspace=${c.workspace}`}>
                    Research
                  </Link>
                  . Analysis sessions do not change research approval or create
                  portfolio positions. Pausing stops analysis; resuming never
                  sends a backlog of old setups. Restarting the backend pauses
                  sessions until you resume them.
                </p>
              </details>
            </>
          )}
        </>
      )}
    </div>
  );
}
