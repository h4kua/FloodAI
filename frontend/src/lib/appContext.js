import { createContext, useContext } from "react";
import { translate } from "./translations";

export const AppContext = createContext({ lang: "id", theme: "dark" });

export function useApp() {
  return useContext(AppContext);
}

export function useT() {
  const { lang } = useContext(AppContext);
  return (key, vars) => translate(lang, key, vars);
}
