import { useThemeStore } from "../hooks/useThemeStore";

/**
 * Three-state toggle: system · light · dark. Displayed in the masthead as a
 * small monochrome control — matches the archival vocabulary (no emoji icons).
 */
export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <div
      className="theme-toggle"
      role="radiogroup"
      aria-label="display theme"
    >
      {(["light", "system", "dark"] as const).map((t) => (
        <button
          key={t}
          type="button"
          className={`theme-toggle-chip ${theme === t ? "theme-toggle-chip--on" : ""}`}
          onClick={() => setTheme(t)}
          role="radio"
          aria-checked={theme === t}
          title={
            t === "system"
              ? "follow OS preference"
              : `force ${t} mode`
          }
        >
          {t === "light" ? "day" : t === "dark" ? "night" : "auto"}
        </button>
      ))}
    </div>
  );
}
