import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { t } from "../i18n";
import { readLocal, writeLocal } from "../storage";
import { Button } from "./components";

export type ScrollRow = {
  readonly id: string;
  readonly reviewed: boolean;
  readonly revision: number;
};

/** Each browser measures its own visible batch; only server-confirmed awards advance it. */
export function ScoreScroll({
  rows,
  scope,
  children,
  ranking = false,
  controls = false,
}: {
  readonly rows: readonly ScrollRow[];
  readonly scope: string;
  readonly children: ReactNode;
  readonly ranking?: boolean;
  readonly controls?: boolean;
}) {
  const pane = useRef<HTMLElement>(null);
  const visible = useRef<string[]>([]);
  const anchor = useRef<{ id: string; top: number } | null>(null);
  const previous = useRef<{ scope: string; rows: readonly ScrollRow[] }>({ scope, rows });
  const [auto, setAuto] = useState(() => readLocal("autoScoreScroll") !== "false");
  const [manual, setManual] = useState(false);
  const rowNodes = useCallback(
    () => Array.from(pane.current?.querySelectorAll<HTMLElement>("[data-scroll-id]") ?? []),
    [],
  );
  const remember = useCallback(() => {
    const box = pane.current?.getBoundingClientRect();
    if (!box) return;
    if (ranking && pane.current && pane.current.scrollTop > 0) {
      const node = rowNodes().find((item) => item.getBoundingClientRect().bottom > box.top);
      if (node)
        anchor.current = {
          id: node.dataset.scrollId || "",
          top: node.getBoundingClientRect().top - box.top,
        };
    } else anchor.current = null;
    visible.current = rowNodes()
      .filter((node) => {
        const row = node.getBoundingClientRect();
        return row.top >= box.top - 1 && row.bottom <= box.bottom + 1;
      })
      .map((node) => node.dataset.scrollId || "");
  }, [ranking, rowNodes]);
  const move = (id: string) => {
    const container = pane.current;
    const node = rowNodes().find((item) => item.dataset.scrollId === id);
    if (!container || !node) return;
    const wasInside = container.contains(document.activeElement);
    container.scrollTo({
      top:
        container.scrollTop +
        node.getBoundingClientRect().top -
        container.getBoundingClientRect().top,
      behavior: "instant",
    });
    if (wasInside && document.activeElement?.matches("button"))
      node
        .querySelector<HTMLButtonElement>("button:not(:disabled)")
        ?.focus({ preventScroll: true });
    remember();
  };
  useEffect(() => {
    const container = pane.current;
    if (!container) return;
    let frame = 0;
    let measured = "";
    const resize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const viewport = window.visualViewport;
        const height = viewport?.height ?? innerHeight;
        const bottom = height + (viewport?.offsetTop ?? 0);
        const bar = document.querySelector(".finale-action-bar")?.getBoundingClientRect();
        const reserve = bar && bar.bottom > 0 && bar.top < bottom ? bar.height + 24 : 24;
        const nodes = rowNodes();
        const first = nodes[0];
        const fifth = nodes[Math.min(4, nodes.length - 1)];
        const style = getComputedStyle(container);
        const padding =
          Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
        // Layout offsets exclude the transforms used to animate rank changes.
        // Measuring animated screen positions can collapse this pane to two pixels.
        const cap =
          ranking && first && fifth
            ? Math.max(first.offsetHeight, fifth.offsetTop + fifth.offsetHeight - first.offsetTop) +
              padding +
              (nodes.length <= 5 ? 2 : 0)
            : 620;
        const signature = `${height}:${container.clientWidth}:${cap}:${reserve}:${nodes.length}`;
        if (signature === measured) return;
        measured = signature;
        // This is a document section, not a fixed panel. Its position below the fold
        // must never squeeze it into a tiny strip that stays collapsed after scrolling.
        // Reserve room for the action bar and surrounding controls in each viewport.
        const room = Math.max(88, height - reserve - 160);
        container.style.setProperty("--score-scroll-height", `${Math.min(cap, room)}px`);
        container.dataset.overflow = String(
          ranking
            ? nodes.length > 5 || cap > room + 1
            : container.scrollHeight > container.clientHeight + 1,
        );
        remember();
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    window.addEventListener("resize", resize);
    window.visualViewport?.addEventListener("resize", resize);
    container.addEventListener("scroll", remember, { passive: true });
    resize();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", resize);
      window.visualViewport?.removeEventListener("resize", resize);
      container.removeEventListener("scroll", remember);
    };
  }, [ranking, remember, rowNodes]);
  // Preserve the row being read when score changes reorder a scrolled ranking.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reordered rows require restoring the reader’s position before paint.
  useLayoutEffect(() => {
    const saved = anchor.current;
    const container = pane.current;
    if (!ranking || !saved || !container) return;
    const node = rowNodes().find((item) => item.dataset.scrollId === saved.id);
    if (node)
      container.scrollTop +=
        node.getBoundingClientRect().top - container.getBoundingClientRect().top - saved.top;
    remember();
  }, [ranking, rows, rowNodes, remember]);
  useEffect(() => {
    const before = previous.current;
    previous.current = { scope, rows };
    if (scope !== before.scope) {
      pane.current?.scrollTo({ top: 0 });
      setManual(false);
      remember();
      return;
    }
    if (!auto || ranking || manual) {
      remember();
      return;
    }
    const last = visible.current.at(-1);
    const old = before.rows.find((row) => row.id === last);
    const current = rows.find((row) => row.id === last);
    if (old && current?.reviewed && !old.reviewed && current.revision !== old.revision) {
      if (
        pane.current?.contains(document.activeElement) &&
        document.activeElement?.matches("input, textarea, [contenteditable=true]")
      )
        return;
      const end = rows.findIndex((row) => row.id === last);
      const target =
        rows.slice(0, end).find((row) => !row.reviewed) ??
        rows.slice(end + 1).find((row) => !row.reviewed);
      if (target) move(target.id);
    }
    remember();
  });
  return (
    <section className={`score-scroll-section ${ranking ? "ranking-scroll-section" : ""}`}>
      {controls && (
        <div className="row wrap score-scroll-tools">
          <label className="folder-option">
            <input
              type="checkbox"
              checked={auto}
              onChange={(event) => {
                setAuto(event.target.checked);
                setManual(false);
                writeLocal("autoScoreScroll", String(event.target.checked));
              }}
            />
            {t("scroll.auto")}
          </label>
          {auto && manual && <Button onClick={() => setManual(false)}>{t("scroll.resume")}</Button>}
          <Button
            onClick={() => {
              const row = rows.find((item) => !item.reviewed);
              if (row) move(row.id);
              setManual(false);
            }}
            disabled={rows.every((row) => row.reviewed)}
          >
            {t("scroll.pending")}
          </Button>
        </div>
      )}
      <section
        className="score-scroll"
        aria-label={t(ranking ? "standings.title" : "finale.answers")}
        ref={pane}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll this named region.
        tabIndex={0}
        onWheel={() => {
          if (auto && !ranking && pane.current?.dataset.overflow === "true") setManual(true);
        }}
        onTouchMove={() => {
          if (auto && !ranking && pane.current?.dataset.overflow === "true") setManual(true);
        }}
        onKeyDown={(event) => {
          if (["PageDown", "PageUp", "Home", "End"].includes(event.key)) setManual(true);
        }}
      >
        {children}
      </section>
    </section>
  );
}
