import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  ColorType,
  type UTCTimestamp,
  type IChartApi,
  type Time,
  type IRange,
} from "lightweight-charts";
import * as echarts from "echarts/core";
import {
  LineChart,
  BarChart,
  ScatterChart,
  HeatmapChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  AriaComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Doc } from "./api";
import { number, fmt } from "./api";
import { Empty } from "./components";
echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  AriaComponent,
  VisualMapComponent,
  CanvasRenderer,
]);
export function Plot({
  option,
  label,
  height = 280,
}: {
  option: Doc;
  label: string;
  height?: number;
}) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "canvas" });
    c.setOption({
      backgroundColor: "transparent",
      color: ["#9e8bff", "#45d6b3", "#5ca8f6", "#e9ad67", "#e66e85"],
      textStyle: { color: "#8490a7", fontFamily: "system-ui" },
      aria: { enabled: true },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        backgroundColor: "#18202f",
        borderColor: "#35415a",
        textStyle: { color: "#e9edf5" },
      },
      grid: { left: 58, right: 20, top: 28, bottom: 45 },
      ...option,
    });
    const o = new ResizeObserver(() => c.resize());
    o.observe(el.current);
    return () => {
      o.disconnect();
      c.dispose();
    };
  }, [option]);
  return (
    <div
      ref={el}
      role="img"
      aria-label={label}
      style={{ height, width: "100%" }}
    />
  );
}
export function TimePlot({
  rows,
  series,
  label,
  height = 280,
}: {
  rows: Doc[];
  series: { key: string; name: string; color?: string }[];
  label: string;
  height?: number;
}) {
  if (!rows.length)
    return <Empty title="No samples in this evidence vintage" />;
  return (
    <Plot
      height={height}
      label={label}
      option={{
        xAxis: {
          type: "time",
          axisLine: { lineStyle: { color: "#283244" } },
          axisLabel: {
            color: "#8490a7",
            formatter: (v: number) => new Date(v).toISOString().slice(11, 16),
          },
        },
        yAxis: {
          type: "value",
          scale: true,
          splitLine: { lineStyle: { color: "#202938" } },
          axisLabel: { color: "#8490a7" },
        },
        legend: { top: 0, textStyle: { color: "#a6b0c3" }, icon: "circle" },
        dataZoom: [{ type: "inside", filterMode: "none" }],
        series: series.map((s, i) => ({
          type: "line",
          name: s.name,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 2, color: s.color },
          itemStyle: { color: s.color },
          areaStyle: i === 0 ? { opacity: 0.07 } : undefined,
          data: rows.map((r) => [r.at_ms, number(r[s.key])]),
        })),
      }}
    />
  );
}
export function Bars({
  values,
  label,
  height = 250,
}: {
  values: { name: string; value: unknown }[];
  label: string;
  height?: number;
}) {
  if (!values.length) return <Empty title="No observations available" />;
  return (
    <Plot
      label={label}
      height={height}
      option={{
        xAxis: {
          type: "category",
          data: values.map((x) => x.name),
          axisLabel: { color: "#9da7ba", overflow: "truncate", width: 110 },
        },
        yAxis: {
          type: "value",
          splitLine: { lineStyle: { color: "#202938" } },
        },
        series: [
          {
            type: "bar",
            barMaxWidth: 38,
            itemStyle: { borderRadius: [3, 3, 0, 0] },
            data: values.map((x) => number(x.value)),
          },
        ],
      }}
    />
  );
}
const syncGroups = new Map<string, Set<IChartApi>>();
export function CandleChart({
  data,
  signals = [],
  overlay = true,
  syncKey,
}: {
  data: Doc;
  signals?: Doc[];
  overlay?: boolean;
  syncKey?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewport = useRef<IRange<Time> | null>(null);
  const [hover, setHover] = useState<Doc | null>(null);
  const bars = data.candles || [];
  useEffect(() => {
    if (!host.current || !bars.length) return;
    const chart = createChart(host.current, {
      autoSize: true,
      height: 430,
      layout: {
        background: { type: ColorType.Solid, color: "#111722" },
        textColor: "#8390a6",
        fontSize: 11,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: "#1c2432" },
        horzLines: { color: "#1c2432" },
      },
      rightPriceScale: { borderColor: "#263145" },
      timeScale: {
        borderColor: "#263145",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { labelBackgroundColor: "#7561cf" },
        horzLine: { labelBackgroundColor: "#7561cf" },
      },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#43caaa",
      downColor: "#df7185",
      wickUpColor: "#43caaa",
      wickDownColor: "#df7185",
      borderVisible: false,
      priceFormat: {
        type: "price",
        precision: Math.max(
          0,
          (
            data.metadata?.spec?.constraints?.["PRICE_FILTER.tickSize"] ||
            "0.0001"
          )
            .replace(/0+$/, "")
            .split(".")[1]?.length || 0,
        ),
        minMove: Number(
          data.metadata?.spec?.constraints?.["PRICE_FILTER.tickSize"] ||
            ".0001",
        ),
      },
    });
    const records = bars.map((b: Doc) => ({
      time: (b.data.open_ms / 1000) as UTCTimestamp,
      open: Number(b.data.open),
      high: Number(b.data.high),
      low: Number(b.data.low),
      close: Number(b.data.close),
    }));
    candles.setData(records);
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volume
      .priceScale()
      .applyOptions({ scaleMargins: { top: 0.83, bottom: 0 } });
    volume.setData(
      bars.map((b: Doc) => ({
        time: (b.data.open_ms / 1000) as UTCTimestamp,
        value: Number(b.data.volume),
        color:
          Number(b.data.close) >= Number(b.data.open) ? "#275d54" : "#603745",
      })),
    );
    if (overlay) {
      for (const key of ["ema20", "ema50", "vwap_utc_session"]) {
        const unique = new Map<number, number | null>();
        for (const f of data.features || []) {
          const v = f.values?.[key];
          if (v)
            unique.set(
              f.target_open_ms,
              v.stable && v.status === "valid" ? number(v.value) : null,
            );
        }
        const points = [...unique]
          .sort((a, b) => a[0] - b[0])
          .map(([t, v]) =>
            v === null
              ? { time: (t / 1000) as UTCTimestamp }
              : { time: (t / 1000) as UTCTimestamp, value: v },
          );
        if (points.length) {
          const line = chart.addSeries(LineSeries, {
            color:
              key === "ema20"
                ? "#b8a5ff"
                : key === "ema50"
                  ? "#e9b675"
                  : "#64b8ee",
            lineWidth: 1,
            title: key,
          });
          line.setData(points);
        }
      }
    }
    const low = records[0].time,
      high = records[records.length - 1].time;
    const markers = signals
      .filter((s) => s.candidate?.symbol === data.symbol)
      .map((s) => ({
        time: Math.floor(s.candidate.target_open_ms / 1000) as UTCTimestamp,
        position: "belowBar" as const,
        shape: "arrowUp" as const,
        color: s.decision?.status === "admitted" ? "#b2a2ff" : "#c68b69",
        text: s.decision?.status === "admitted" ? "Paper admit" : "Rejected",
      }))
      .filter((m) => m.time >= low && m.time <= high)
      .sort((a, b) => a.time - b.time);
    if (signals.length === 1) {
      const signal = signals[0];
      const levels = signal.paper_outcome?.state?.levels;
      if (levels)
        for (const [name, value] of Object.entries(levels)) {
          if (
            ["stop", "target", "partial"].includes(name) &&
            number(value) !== null
          )
            candles.createPriceLine({
              price: Number(value),
              title: "Frozen " + name,
              color: name === "stop" ? "#df7185" : "#9d8ae9",
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: true,
            });
        }
    }
    createSeriesMarkers(candles, markers);
    chart.subscribeCrosshairMove((p) => {
      const v = p.seriesData.get(candles);
      setHover(v && "open" in v ? v : null);
    });
    if (viewport.current) chart.timeScale().setVisibleRange(viewport.current);
    else chart.timeScale().fitContent();
    const group = syncKey
      ? syncGroups.get(syncKey) || new Set<IChartApi>()
      : null;
    if (group && syncKey) {
      group.add(chart);
      syncGroups.set(syncKey, group);
    }
    const sync = (range: IRange<Time> | null) => {
      if (!range || !group) return;
      for (const other of group) {
        if (
          other !== chart &&
          JSON.stringify(other.timeScale().getVisibleRange()) !==
            JSON.stringify(range)
        ) {
          try {
            other.timeScale().setVisibleRange(range);
          } catch {
            /* Different recorded ranges cannot synchronize. */
          }
        }
      }
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(sync);
    return () => {
      viewport.current = chart.timeScale().getVisibleRange();
      group?.delete(chart);
      if (syncKey && group?.size === 0) syncGroups.delete(syncKey);
      chart.timeScale().unsubscribeVisibleTimeRangeChange(sync);
      chart.remove();
    };
  }, [data, signals, overlay]);
  return (
    <>
      <div className="ohlc">
        {["open", "high", "low", "close"].map((k) => (
          <span key={k}>
            {k[0].toUpperCase()}{" "}
            <b>{fmt(hover?.[k] ?? bars.at(-1)?.data[k], 4)}</b>
          </span>
        ))}
        <span className="chart-hint">Scroll to zoom · drag to pan</span>
      </div>
      {bars.length ? (
        <div
          ref={host}
          className="candle-host"
          role="img"
          aria-label={`${data.symbol} actual closed OHLCV candles`}
        />
      ) : (
        <Empty title="No complete candles in this range">
          Choose a smaller timeframe or a wider recorded range. Incomplete
          buckets stay empty.
        </Empty>
      )}
      <div className="chart-footer">
        <span>
          UTC · base-asset volume · {bars.length} closed bars ·{" "}
          {data.gaps?.length || 0} recorded gaps · no resampling
        </span>
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™ · © 2025 TradingView, Inc. ↗
        </a>
      </div>
    </>
  );
}
