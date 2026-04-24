import { useEffect } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "system" | "light" | "dark";

type State = {
  theme: Theme;
  setTheme: (t: Theme) => void;
};

export const useThemeStore = create<State>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (t) => set({ theme: t }),
    }),
    { name: "learchive-theme" },
  ),
);

/**
 * Reflects current theme choice onto <html data-theme="..."> so the CSS
 * variable rules can take effect. "system" removes the attribute so the
 * `@media (prefers-color-scheme: dark)` block wins again.
 */
export function useApplyTheme(): void {
  const theme = useThemeStore((s) => s.theme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
  }, [theme]);
}
