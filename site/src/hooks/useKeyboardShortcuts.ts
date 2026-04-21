import { useEffect } from "react";
import { usePlayerStore } from "./usePlayerStore";

/**
 * Global keyboard shortcuts:
 *   Space    — toggle play/pause (when a set is loaded)
 *   Escape   — close player
 *   /        — focus the search box
 *
 * Skipped when the user is typing into an input/textarea/contentEditable,
 * so existing form interactions (search typing, artist modal if present)
 * aren't hijacked.
 *
 * Dispatches a `player:toggle` CustomEvent which <Player> listens for —
 * avoids growing the store with imperative refs.
 */
export function useKeyboardShortcuts() {
  const current = usePlayerStore((s) => s.current);
  const stop = usePlayerStore((s) => s.stop);

  useEffect(() => {
    function isTyping(target: EventTarget | null): boolean {
      const el = target as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
    }

    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const typing = isTyping(e.target);

      // "/" jumps to search even from non-form areas.
      if (e.key === "/" && !typing) {
        e.preventDefault();
        const box = document.querySelector<HTMLInputElement>(
          ".ais-SearchBox-input",
        );
        box?.focus();
        return;
      }
      if (typing) return;

      if (e.key === " ") {
        if (current) {
          e.preventDefault();
          window.dispatchEvent(new CustomEvent("player:toggle"));
        }
      } else if (e.key === "Escape") {
        if (current) {
          e.preventDefault();
          stop();
        }
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, stop]);
}
