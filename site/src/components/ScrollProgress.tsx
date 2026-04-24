import { useEffect, useState } from "react";

/**
 * Thin ledger-line at the very top of the viewport. Fills left→right in
 * stamp-red as the reader advances through the archive — the page metaphor,
 * honoured. Pointer-events: none so it never gets in the way.
 */
export function ScrollProgress() {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    let raf = 0;
    const update = () => {
      raf = 0;
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      setPct(max > 0 ? Math.min(100, (doc.scrollTop / max) * 100) : 0);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className="scroll-progress" aria-hidden>
      <div className="scroll-progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}
