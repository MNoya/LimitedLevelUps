import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { CardModal, columnPipClass, neighborCardUrls } from "./TierGrid";
import { Tooltip } from "./Tooltip";
import { cn } from "../lib/utils";
import { columnOf, searchTierCards, tierColor, type TierCard } from "../data/tierList";

export function TierCardSearch({ cards, onClose }: { cards: TierCard[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const matches = useMemo(() => searchTierCards(cards, query), [cards, query]);
  const pickedCard = picked === null ? undefined : matches[picked]?.card;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && picked === null) {
        onClose();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, picked]);

  return createPortal(
    <div
      className="fixed inset-0 z-[190] flex items-start justify-center bg-black/70 px-4 pt-[12vh] animate-fadeIn"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Search cards"
    >
      <div
        className="flex w-full max-w-[420px] flex-col rounded-xl border border-border2 bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 pt-3.5">
          <span className="font-display text-[18px] tracking-[0.12em] text-text">SEARCH</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded text-muted transition-colors hover:text-text"
          >
            <X size={18} />
          </button>
        </div>

        <form
          className="px-4 pb-3 pt-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (matches.length > 0) {
              setPicked(0);
            }
          }}
        >
          <div className="relative flex items-center">
            <Search size={17} className="pointer-events-none absolute left-2.5 text-dim" />
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Card name"
              autoComplete="off"
              className={cn(
                "w-full rounded border border-border2 bg-bg py-2 pl-9 pr-9 text-[14px] text-text outline-none",
                "transition-colors placeholder:text-dim focus:border-green/60",
                "[&::-webkit-search-cancel-button]:hidden",
              )}
            />
            {query.length > 0 && (
              <Tooltip label="Clear Search">
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    inputRef.current?.focus();
                  }}
                  aria-label="Clear Search"
                  className="absolute right-1.5 flex h-7 w-7 cursor-pointer items-center justify-center rounded text-green transition-colors hover:bg-surface2"
                >
                  <X size={16} />
                </button>
              </Tooltip>
            )}
          </div>
        </form>

        {query.trim().length > 0 && (
          <div className="menu-scrollbar max-h-[45vh] overflow-y-auto border-t border-border px-2 py-2">
            {matches.length === 0 ? (
              <p className="px-2 py-3 text-center text-[13px] text-muted">No cards match</p>
            ) : (
              matches.map(({ card, start, end }, index) => (
                <button
                  key={card.card_id}
                  type="button"
                  onClick={() => setPicked(index)}
                  className="flex w-full cursor-pointer items-center gap-2.5 rounded px-2 py-2 text-left transition-colors hover:bg-surface2"
                >
                  <i
                    className={cn(columnPipClass(columnOf(card.color)), "shrink-0")}
                    style={{ fontSize: columnOf(card.color) === "M" ? 19 : 14 }}
                  />
                  <span className="min-w-0 flex-1 truncate text-[14px] text-text">
                    {card.name.slice(0, start)}
                    <b className="font-semibold text-green">{card.name.slice(start, end)}</b>
                    {card.name.slice(end)}
                  </span>
                  <span
                    className="shrink-0 font-display text-[15px] leading-none"
                    style={{ color: tierColor(card.tier) }}
                  >
                    {card.tier}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {picked !== null && pickedCard && (
        <CardModal
          card={pickedCard}
          onClose={() => setPicked(null)}
          onPrev={picked > 0 ? () => setPicked(picked - 1) : undefined}
          onNext={picked < matches.length - 1 ? () => setPicked(picked + 1) : undefined}
          position={`${picked + 1} / ${matches.length}`}
          neighborUrls={neighborCardUrls(matches.map((match) => match.card), picked)}
        />
      )}
    </div>,
    document.body,
  );
}
