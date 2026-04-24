import { useQueueStore } from "../hooks/useQueueStore";

/**
 * Small pill next to Favorites that toggles auto-advance on set end.
 * Visible always — discoverability matters here; nobody guesses queue
 * behaviour from the absence of a toggle.
 */
export function QueueToggle() {
  const auto = useQueueStore((s) => s.autoAdvance);
  const setAuto = useQueueStore((s) => s.setAutoAdvance);

  return (
    <button
      type="button"
      className={`queue-toggle ${auto ? "queue-toggle--on" : ""}`}
      onClick={() => setAuto(!auto)}
      aria-pressed={auto}
      title={
        auto
          ? "stop auto-advance — set ends, player stops"
          : "auto-advance to the next set in the current results"
      }
    >
      <span className="queue-toggle-glyph" aria-hidden>
        {auto ? "↳" : "⇥"}
      </span>
      <span className="queue-toggle-label">
        {auto ? "auto-advance on" : "auto-advance off"}
      </span>
    </button>
  );
}
