import { useEffect } from "react";

type Props = {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  activeCount: number;
};

/**
 * Mobile-only filters drawer chrome. Renders a FAB trigger pill and, when
 * open, a tinted backdrop + close handle. The <aside className="filters">
 * itself is styled into a bottom-sheet via .filters--drawer-open (set on
 * .layout from App). Keeps desktop untouched — the pill and backdrop are
 * hidden above the mobile breakpoint.
 */
export function MobileFilters({ open, onToggle, onClose, activeCount }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    // Prevent underlying scroll while the sheet is open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  return (
    <>
      <button
        type="button"
        className={`filters-fab ${open ? "filters-fab--on" : ""}`}
        onClick={onToggle}
        aria-expanded={open}
        aria-controls="site-filters"
      >
        <span className="filters-fab-glyph" aria-hidden>
          ☰
        </span>
        <span className="filters-fab-label">filters</span>
        {activeCount > 0 && (
          <span className="filters-fab-count" aria-label={`${activeCount} active`}>
            {activeCount}
          </span>
        )}
      </button>
      {open && (
        <div
          className="filters-backdrop"
          role="presentation"
          onClick={onClose}
        />
      )}
    </>
  );
}
