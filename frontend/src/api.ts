import { useQuery } from "@tanstack/react-query";
export type Doc = Record<string, any>;
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T = any>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch("/api/" + path, init);
  const d = await r.json();
  if (!r.ok)
    throw new ApiError(
      r.status,
      d.error?.message || d.detail || `Request failed (${r.status})`,
    );
  if (!("data" in d) || !d.meta) throw new Error("Invalid service response");
  return d.data as T;
}
export function useResource<T = any>(
  workspace: string,
  path: string,
  enabled = true,
) {
  return useQuery<T, Error>({
    queryKey: [workspace, path],
    queryFn: () => request<T>(`${workspace}/${path}`),
    enabled,
    staleTime: 10000,
    refetchInterval: 30000,
    retry: 1,
  });
}
export const number = (x: unknown): number | null =>
  (typeof x !== "string" && typeof x !== "number") ||
  (typeof x === "string" && x.trim() === "") ||
  !Number.isFinite(Number(x))
    ? null
    : Number(x);
export function fmt(x: unknown, digits = 2) {
  const n = number(x);
  return n === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(n);
}
export function percent(x: unknown) {
  const n = number(x);
  return n === null ? "—" : fmt(n * 100) + "%";
}
export function short(x: string | undefined) {
  return x ? x.slice(0, 8) + "…" + x.slice(-4) : "—";
}
export function date(x: unknown, zone = "UTC") {
  const n = number(x);
  return n === null
    ? "—"
    : new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hourCycle: "h23",
        timeZone: zone,
      }).format(n);
}
export function query(values: Doc) {
  return new URLSearchParams(
    Object.entries(values)
      .filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
}
export function download(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
