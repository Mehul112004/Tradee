import { useState, type ReactNode } from "react";
import {
  ChevronDown,
  Download,
  RefreshCw,
  Search,
  ArrowUpRight,
  Info,
  Check,
  Copy,
} from "lucide-react";
import { date, download, fmt, short, type Doc } from "./api";
import { useWorkspace } from "./context";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Panel({
  title,
  sub,
  action,
  children,
  className = "",
}: {
  title: string;
  sub?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Heading({
  eyebrow,
  title,
  sub,
  action,
}: {
  eyebrow: string;
  title: string;
  sub: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {action}
    </div>
  );
}
export function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        <Info size={13} />
      </div>
      <strong className={tone}>{value}</strong>
      <small>{sub || "—"}</small>
    </div>
  );
}
export function Empty({
  title = "No evidence yet",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Search size={23} />
      </div>
      <h3>{title}</h3>
      <div className="empty-copy">
        {children ||
          "Select a recorded workspace or create the required artifacts using Tradee’s core workflow."}
      </div>
    </div>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="notice danger" role="alert">
      <Info size={17} />
      <div>
        <strong>Evidence unavailable</strong>
        <p>{error.message}</p>
      </div>
      {retry && (
        <button onClick={retry}>
          <RefreshCw size={14} />
          Retry
        </button>
      )}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span />
      Reading verified evidence…
    </div>
  );
}
export function Json({
  value,
  title = "Inspect source evidence",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <details className="evidence">
      <summary>
        {title}
        <ChevronDown size={15} />
      </summary>
      <div className="evidence-tools">
        <button onClick={() => download(value, "tradee-evidence.json")}>
          <Download size={13} />
          JSON
        </button>
      </div>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function Hash({ value }: { value?: string }) {
  const [copied, set] = useState(false);
  return (
    <button
      className="hash"
      title={value}
      disabled={!value}
      onClick={() => {
        navigator.clipboard.writeText(value!);
        set(true);
        setTimeout(() => set(false), 1500);
      }}
    >
      {short(value)}
      {copied ? <Check size={11} /> : <Copy size={11} />}
    </button>
  );
}
export function Time({ value }: { value: unknown }) {
  const { zone } = useWorkspace();
  return <time>{date(value, zone)}</time>;
}
export function Table({
  columns,
  rows,
  keyOf,
  onRow,
  empty = "No matching records",
}: {
  columns: { label: string; render: (row: Doc) => ReactNode }[];
  rows: Doc[];
  keyOf?: (row: Doc) => string;
  onRow?: (row: Doc) => void;
  empty?: string;
}) {
  const [offset, setOffset] = useState(0);
  const current = Math.min(
    offset,
    Math.max(0, Math.ceil(rows.length / 50) - 1),
  );
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.label}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(current * 50, current * 50 + 50).map((r, i) => (
            <tr key={keyOf?.(r) || i} className={onRow ? "clickable" : ""}>
              {columns.map((c, j) => (
                <td key={c.label}>
                  {j === 0 && onRow ? (
                    <button className="row-open" onClick={() => onRow(r)}>
                      {c.render(r)}
                      <ArrowUpRight size={12} />
                    </button>
                  ) : (
                    c.render(r)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 50 && (
        <div className="table-pager">
          <button
            disabled={current === 0}
            onClick={() => setOffset(current - 1)}
          >
            Previous
          </button>
          <span>
            {current * 50 + 1}–{Math.min(rows.length, current * 50 + 50)} of{" "}
            {rows.length}
          </span>
          <button
            disabled={(current + 1) * 50 >= rows.length}
            onClick={() => setOffset(current + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  ) : (
    <Empty title={empty} />
  );
}
export function SearchInput({
  value,
  onChange,
  placeholder = "Search records…",
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="search">
      <Search size={15} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Money({ value }: { value: unknown }) {
  return (
    <span
      className={
        Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : ""
      }
    >
      {fmt(value)} <small>USDT</small>
    </span>
  );
}
export function Tabs({
  values,
  active,
  onChange,
}: {
  values: string[];
  active: string;
  onChange: (s: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {values.map((v) => (
        <button
          key={v}
          role="tab"
          aria-selected={v === active}
          className={v === active ? "active" : ""}
          onClick={() => onChange(v)}
        >
          {v}
        </button>
      ))}
    </div>
  );
}
