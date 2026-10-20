import { createContext, useContext } from "react";
import type { Doc } from "./api";
export interface Context {
  workspace: string;
  session: string;
  zone: string;
  at: number | null;
  token: string;
  overview: Doc | undefined;
  setParam: (key: string, value: string) => void;
  setToken: (s: string) => void;
  connection: string;
}
export const Workspace = createContext<Context>(null!);
export const useWorkspace = () => useContext(Workspace);
