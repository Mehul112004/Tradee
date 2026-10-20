import React, { Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  LayoutDashboard,
  ChartCandlestick,
  Radio,
  Wallet,
  FlaskConical,
  ScanLine,
  Database,
  Settings2,
  Command,
  ChevronRight,
  Menu,
  RefreshCw,
  SlidersHorizontal,
  ShieldCheck,
} from "lucide-react";
import { request, useResource, type Doc } from "./api";
import { Workspace } from "./context";
import { Badge, ErrorBox, Loading } from "./components";
import "./style.css";
const pages = () => import("./pages");
const Overview = React.lazy(() =>
  pages().then((x) => ({ default: x.Overview })),
);
const Markets = React.lazy(() => pages().then((x) => ({ default: x.Markets })));
const Signals = React.lazy(() => pages().then((x) => ({ default: x.Signals })));
const Portfolio = React.lazy(() =>
  pages().then((x) => ({ default: x.Portfolio })),
);
const Research = React.lazy(() =>
  pages().then((x) => ({ default: x.Research })),
);
const Forward = React.lazy(() => pages().then((x) => ({ default: x.Forward })));
const Data = React.lazy(() => pages().then((x) => ({ default: x.Data })));
const Operations = React.lazy(() =>
  pages().then((x) => ({ default: x.Operations })),
);
const Settings = React.lazy(() =>
  pages().then((x) => ({ default: x.Settings })),
);
const client = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});
const navigation = [
  ["/", "Overview", LayoutDashboard],
  ["/markets", "Markets", ChartCandlestick],
  ["/signals", "Signals", Radio],
  ["/portfolio", "Portfolio", Wallet],
  ["/research", "Research", FlaskConical],
  ["/forward", "Forward review", ScanLine],
  ["/data", "Data quality", Database],
  ["/operations", "Operations", Command],
] as const;
class Boundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <div className="fatal">
        <h1>This view could not render</h1>
        <p>Reload or inspect the backend error before continuing.</p>
        <button onClick={() => window.location.reload()}>
          Reload dashboard
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
function App() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const [token, setToken] = useState("");
  const [connection, setConnection] = useState("connecting");
  const [mobile, setMobile] = useState(false);
  const [cursorOpen, setCursorOpen] = useState(false);
  const [cursor, setCursor] = useState("");
  const boot = useQuery<Doc>({
    queryKey: ["bootstrap"],
    queryFn: () => request("bootstrap"),
    staleTime: Infinity,
  });
  const workspace =
    params.get("workspace") || boot.data?.default_workspace || "local";
  const overview = useResource<Doc>(workspace, "overview", !!boot.data);
  const selected = params.get("session");
  const session = overview.data?.sessions?.some((s: Doc) => s.name === selected)
    ? selected!
    : overview.data?.sessions?.[0]?.name || "";
  const zone = params.get("zone") || "UTC";
  const atRaw = params.get("at");
  const at = atRaw && /^\d+$/.test(atRaw) ? Number(atRaw) : null;
  const setParam = (key: string, value: string) => {
    setParams((p) => {
      const q = new URLSearchParams(p);
      value ? q.set(key, value) : q.delete(key);
      if (key === "workspace") {
        q.delete("session");
        q.delete("at");
        q.delete("dataset");
        q.delete("symbol");
        q.delete("tf");
      }
      return q;
    });
  };
  useEffect(() => {
    setMobile(false);
  }, [location.pathname]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobile(false);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, []);
  useEffect(() => {
    if (!boot.data) return;
    setConnection("connecting");
    let timer: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    const stream = new EventSource(`/api/${workspace}/events`);
    stream.onopen = () => {
      if (alive) setConnection("connected");
    };
    stream.onerror = () => {
      if (alive) setConnection("reconnecting");
    };
    const invalidate = () => {
      if (!timer)
        timer = setTimeout(() => {
          client.invalidateQueries({ queryKey: [workspace] });
          timer = undefined;
        }, 700);
    };
    stream.addEventListener("resource_changed", invalidate);
    stream.addEventListener("job_completed", invalidate);
    stream.addEventListener("runner_changed", invalidate);
    stream.addEventListener("resync", invalidate);
    return () => {
      alive = false;
      stream.close();
      clearTimeout(timer);
    };
  }, [workspace, boot.data]);
  if (boot.isPending) return <Loading />;
  if (boot.error)
    return (
      <div className="fatal">
        <ErrorBox error={boot.error} retry={() => boot.refetch()} />
      </div>
    );
  const label = boot.data?.workspaces.find((p: Doc) => p.id === workspace);
  const sessionInfo = overview.data?.sessions?.find(
    (s: Doc) => s.name === session,
  );
  return (
    <Workspace.Provider
      value={{
        workspace,
        session,
        zone,
        at,
        token,
        overview: overview.data,
        setParam,
        setToken,
        connection,
      }}
    >
      <div className="app">
        <a className="skip" href="#main">
          Skip to main content
        </a>
        <aside className={"sidebar " + (mobile ? "open" : "")}>
          <button
            className="sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMobile(false)}
          >
            ×
          </button>
          <NavLink className="brand" to={"/" + location.search}>
            <span className="brand-mark">
              <span />
              <span />
              <span />
            </span>
            <b>
              tradee<span>.</span>
            </b>
            <Badge>LAB</Badge>
          </NavLink>
          <div className="workspace-label">RESEARCH WORKSPACE</div>
          <nav aria-label="Main navigation">
            {navigation.map(([path, name, Icon]) => (
              <NavLink
                key={path}
                end={path === "/"}
                to={path + location.search}
              >
                <Icon size={18} />
                <span>{name}</span>
                {path === "/signals" && sessionInfo && <small>↗</small>}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="environment">
              <span className="env-icon">
                <ShieldCheck size={18} />
              </span>
              <div>
                <b>Evidence first</b>
                <small>Research & paper trading</small>
              </div>
            </div>
            <NavLink to={"/settings" + location.search}>
              <Settings2 size={17} />
              Settings
            </NavLink>
            <div className="build-label">
              <span className="dot green" />
              Local workspace<span>v1.0</span>
            </div>
          </div>
        </aside>
        <div className="workspace-main">
          <header className="topbar">
            <button
              className="menu-button"
              aria-label="Toggle navigation"
              onClick={() => setMobile(!mobile)}
            >
              <Menu size={19} />
            </button>
            <div className="breadcrumb">
              Workspace
              <ChevronRight size={13} />
              <b>
                {navigation.find((x) => x[0] === location.pathname)?.[1] ||
                  "Settings"}
              </b>
            </div>
            <div className="top-controls">
              <label className="sr-only" htmlFor="workspace">
                Workspace
              </label>
              <select
                id="workspace"
                value={workspace}
                onChange={(e) => setParam("workspace", e.target.value)}
              >
                {boot.data?.workspaces.map((p: Doc) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
              <div className="connection">
                <i
                  className={
                    "dot " + (connection === "connected" ? "green" : "amber")
                  }
                />
                <span>
                  {connection === "connected"
                    ? "Service connected"
                    : connection}
                </span>
              </div>
              <button
                className="icon-button"
                aria-label="Refresh all evidence"
                onClick={() =>
                  client.invalidateQueries({ queryKey: [workspace] })
                }
              >
                <RefreshCw size={16} />
              </button>
              <span className="avatar">T</span>
            </div>
          </header>
          <div className="contextbar">
            <div>
              <Badge tone={label?.synthetic ? "warn" : "purple"}>
                {label?.synthetic
                  ? "SYNTHETIC VERIFICATION"
                  : "RECORDED WORKSPACE"}
              </Badge>
              <span className="context-divider" />
              <label>
                Session{" "}
                <select
                  aria-label="Session"
                  value={session}
                  onChange={(e) => setParam("session", e.target.value)}
                >
                  {!session && <option value="">No session</option>}
                  {overview.data?.sessions?.map((s: Doc) => (
                    <option key={s.name}>{s.name}</option>
                  ))}
                </select>
              </label>
              {sessionInfo && <Badge>{sessionInfo.mode}</Badge>}
            </div>
            <div>
              <button
                className={
                  at !== null ? "view-button historical" : "view-button"
                }
                onClick={() => setCursorOpen(!cursorOpen)}
              >
                <SlidersHorizontal size={13} />
                {at === null ? "Latest recorded" : "Decision as of " + at}
              </button>
              <span className="timezone">{zone}</span>
            </div>
          </div>
          {cursorOpen && (
            <div className="cursor-bar">
              <label>
                Knowledge cursor · epoch milliseconds
                <input
                  aria-label="Knowledge cursor"
                  inputMode="numeric"
                  value={cursor}
                  onChange={(e) => setCursor(e.target.value)}
                  placeholder="Includes recording time, not just event time"
                />
              </label>
              <button
                disabled={!/^\d+$/.test(cursor)}
                onClick={() => setParam("at", cursor)}
              >
                Apply cursor
              </button>
              <button
                onClick={() => {
                  setParam("at", "");
                  setCursorOpen(false);
                }}
              >
                Return to latest recorded
              </button>
            </div>
          )}
          {label?.synthetic && (
            <div className="synthetic-strip">
              <span>ENGINEERING VERIFICATION</span>Synthetic prices and paper
              results. This workspace does not demonstrate market profitability.
            </div>
          )}
          {at !== null && (
            <div className="notice historical">
              <p>
                Decision-as-of view · only source cycles and audit events
                recorded by this cursor are visible. Operator controls are
                disabled.
              </p>
            </div>
          )}
          <main id="main">
            <ErrorBox error={overview.error} retry={() => overview.refetch()} />
            <Boundary key={workspace + location.pathname}>
              <Suspense fallback={<Loading />}>
                <Routes>
                  <Route path="/" element={<Overview />} />
                  <Route path="/markets" element={<Markets />} />
                  <Route path="/signals" element={<Signals />} />
                  <Route path="/portfolio" element={<Portfolio />} />
                  <Route path="/research" element={<Research />} />
                  <Route path="/forward" element={<Forward />} />
                  <Route path="/data" element={<Data />} />
                  <Route path="/operations" element={<Operations />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route
                    path="*"
                    element={
                      <div className="empty">
                        <h1>Page not found</h1>
                        <NavLink to={"/" + location.search}>
                          Return to overview
                        </NavLink>
                      </div>
                    }
                  />
                </Routes>
              </Suspense>
            </Boundary>
          </main>
          <footer className="footer">
            <span>
              TRADEE RESEARCH LAB <i> / </i> Binance USDⓈ-M perpetual futures
            </span>
            <span>Paper evidence · No live trading approval</span>
          </footer>
        </div>
      </div>
    </Workspace.Provider>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
