import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { Tooltip } from "../Tooltip";
import { ManaCost } from "../ManaPips";
import { PreviewShell, previewAnchorFor, type PreviewAnchor } from "../TierGrid";
import { useFallbackImage } from "../pod/review/ReviewCard";
import { cardImageSources, useCardImageMap } from "../../data/cardImages";
import { fetchSetRaresAndMythics, type ColorSection } from "../../data/scryfallSet";
import { useDraftRates } from "../../data/trackerDrafts";
import {
  fetchCollection,
  fetchSetEconomy,
  saveCollectionCount,
  saveSetEconomy,
  EMPTY_ECONOMY,
  type CollectionCount,
} from "../../data/trackerApi";
import {
  draftsToRareComplete,
  masteryTrackFor,
  packsToRareComplete,
  projectCompletion,
  remainingMasteryPacks,
} from "../../data/collectionProjection";
const SUBLABEL_CLS = "font-display text-[13px] tracking-[0.08em] text-muted";

const COLOR_HEX: Record<string, string> = {
  W: "#f5efd6", U: "#4aa8ff", B: "#a98eff", R: "#ff5e5e", G: "#2ee85c", M: "#ffc63a", C: "#8a93a5",
};

const RARITY_STYLE = {
  rare: { color: "#A58E4A", gradient: "linear-gradient(90deg, #876a3b 0%, #dfbd6b 50%, #876a3b 100%)" },
  mythic: { color: "#BF4427", gradient: "linear-gradient(90deg, #9E3620 0%, #D2603C 50%, #9E3620 100%)" },
};

type RarityStyle = (typeof RARITY_STYLE)["rare"];

function frontFace(name: string): string {
  return name.split(" // ")[0].trim();
}

function collectionLookup(counts: CollectionCount[] | undefined): (name: string) => number {
  const owned = new Map<string, number>();
  for (const c of counts ?? []) {
    owned.set(c.cardName, c.owned);
    owned.set(frontFace(c.cardName), c.owned);
  }
  return (name) => owned.get(name) ?? owned.get(frontFace(name)) ?? 0;
}

/** owned counts copies so a playset is `cards * 4`, held counts cards with at least one copy */
function tallySections(sections: ColorSection[], lookup: (name: string) => number) {
  const cards = sections.flatMap((s) => s.cards);
  const owned = cards.reduce((n, c) => n + lookup(c), 0);
  const held = cards.reduce((n, c) => n + (lookup(c) > 0 ? 1 : 0), 0);
  return {
    cards: cards.length,
    owned,
    held,
    pct: cards.length ? Math.round((owned / (cards.length * 4)) * 100) : 0,
    heldPct: cards.length ? Math.round((held / cards.length) * 100) : 0,
  };
}

export function Collection({
  slug, setCode, accountId, narrow = false,
}: { slug: string | undefined; setCode: string; accountId: number | null; narrow?: boolean }) {
  const qc = useQueryClient();
  const isMobile = useIsMobile();

  const { data: lists, isLoading, error } = useQuery({
    queryKey: ["scryfall-set", setCode],
    queryFn: () => fetchSetRaresAndMythics(setCode),
    staleTime: Infinity,
  });
  const { data: counts } = useQuery({
    queryKey: ["tracker-collection", setCode],
    queryFn: () => fetchCollection(setCode),
  });

  const lookup = useMemo(() => collectionLookup(counts), [counts]);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["tracker-collection", setCode] });

  const allCards = useMemo(
    () => [...(lists?.rares ?? []), ...(lists?.mythics ?? [])]
      .flatMap((section) => section.cards)
      .map((name) => ({ name, set: setCode })),
    [lists, setCode],
  );
  const cardImages = useCardImageMap(allCards);
  const { data: economy } = useQuery({
    queryKey: ["tracker-economy", setCode],
    queryFn: () => fetchSetEconomy(setCode),
  });
  const saveEconomy = async (patch: Parameters<typeof saveSetEconomy>[1]) => {
    await saveSetEconomy(setCode, patch);
    qc.invalidateQueries({ queryKey: ["tracker-economy", setCode] });
  };
  const [preview, setPreview] = useState<{ sources: string[]; anchor: PreviewAnchor } | null>(null);
  const draftRates = useDraftRates(slug, setCode, accountId);
  const [copiesMode, setCopiesMode] = useState<"playset" | "singles">("playset");
  const [shownRarity, setShownRarity] = useState<"rare" | "mythic">("rare");

  if (isLoading) return <div className="px-5 md:px-10 py-8 text-muted text-[14px]">Loading {setCode} cards from Scryfall</div>;
  if (error || !lists) return <div className="px-5 md:px-10 py-8 text-red text-[14px]">Scryfall has no rares or mythics for {setCode}</div>;

  const rare = tallySections(lists.rares, lookup);
  const myth = tallySections(lists.mythics, lookup);
  const eco = economy ?? EMPTY_ECONOMY;
  const masteryTrack = masteryTrackFor(setCode);
  const projection = projectCompletion(eco, { owned: rare.owned, cards: rare.cards },
                                       { owned: myth.owned, cards: myth.cards }, masteryTrack);
  // Side by side the way the spreadsheet tab held them, stacked on a phone
  const columnsCls = isMobile ? "grid-cols-1" : narrow ? "grid-cols-2" : "grid-cols-2 xl:grid-cols-4";
  const sectionsCls = isMobile || narrow ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-2";
  const passPacksLeft = remainingMasteryPacks(eco.masteryLevel, masteryTrack);
  const playsets = copiesMode === "playset";
  const toggleCopiesMode = () => setCopiesMode(playsets ? "singles" : "playset");
  const columns = [
    {
      key: "rare" as const, label: "RARES", sections: lists.rares, rarity: RARITY_STYLE.rare,
      owned: playsets ? rare.owned : rare.held,
      total: playsets ? rare.cards * 4 : rare.cards,
      pct: playsets ? rare.pct : rare.heldPct,
      projected: playsets ? projection.rarePct : null,
      missing: rare.cards - rare.held,
      extraLine: `${draftsToRareComplete(eco, rare, draftRates, masteryTrack)} drafts to complete`,
    },
    {
      key: "mythic" as const, label: "MYTHICS", sections: lists.mythics, rarity: RARITY_STYLE.mythic,
      owned: playsets ? myth.owned : myth.held,
      total: playsets ? myth.cards * 4 : myth.cards,
      pct: playsets ? myth.pct : myth.heldPct,
      projected: playsets ? projection.mythicPct : null,
      missing: myth.cards - myth.held,
      extraLine: null,
    },
  ];

  return (
    <div className="p-4">
      <div className="border border-border bg-surface mb-4">
        <div className="grid gap-[1px] bg-border auto-rows-fr"
             style={{ gridTemplateColumns: "2fr 1fr 2fr 1fr" }}>
          <EconomyCell label="PACKS OWNED" value={eco.packsOwned} tooltip="Unopened Packs you own"
                       onCommit={(n) => saveEconomy({ packsOwned: n })} />
          <EconomyCell label="GOLDEN PACKS" value={eco.goldenPacks} tooltip="Golden Packs you own, about 4.4 Rares each"
                       onCommit={(n) => saveEconomy({ goldenPacks: n })} />
          <EconomyCell label="PASS LVL" value={eco.masteryLevel}
                       tooltip="Your Mastery Pass level"
                       onCommit={(n) => saveEconomy({ masteryLevel: n })} />
          <EconomyCell label="RANKED PACKS" value={eco.rankedSeasonPacks}
                       tooltip="Packs from Ranked Season Rewards"
                       onCommit={(n) => saveEconomy({ rankedSeasonPacks: n })} />
          <DerivedCell label="PASS PACKS" value={passPacksLeft}
                       tooltip="Pass Packs left on the track" />
          <DerivedCell label="FUTURE PACKS" value={passPacksLeft + eco.rankedSeasonPacks}
                       tooltip="Pass Packs plus Ranked Packs" />
          <DerivedCell label="TO OPEN" value={eco.packsOwned + passPacksLeft + eco.rankedSeasonPacks}
                       tooltip="Packs you own plus every Future Pack" />
          <DerivedCell label="PACKS NEEDED" value={packsToRareComplete(eco, rare, masteryTrack)}
                       tooltip="Extra Packs you need for a full Rare Playset" />
        </div>
      </div>

      {/* One list at a time on a phone, so reaching the mythics costs a tap and not 60 rows of scroll */}
      {isMobile && (
        <div className="grid grid-cols-2 gap-2 mb-3">
          {columns.map((col) => (
            <div
              key={col.key}
              className={cn("border",
                col.key === shownRarity ? "border-border2 bg-surface2" : "border-border bg-surface")}
            >
              <CompletionBar
                label={col.label} owned={col.owned} total={col.total} pct={col.pct} projected={col.projected}
                rarity={col.rarity} missing={col.missing} extraLine={col.extraLine}
                onToggleMode={() => (col.key === shownRarity ? toggleCopiesMode() : setShownRarity(col.key))}
              />
            </div>
          ))}
        </div>
      )}

      <div className={cn("grid gap-4 items-start", columnsCls)}>
        {columns
          .filter((col) => !isMobile || col.key === shownRarity)
          .map(({ key, label, sections, rarity, owned, total, pct, projected, missing, extraLine }) => (
          <div key={key} className={cn(!narrow && !isMobile && "xl:col-span-2")}>
            {!isMobile && (
              <div className="border border-border bg-surface mb-3">
                <CompletionBar label={label} owned={owned} total={total} pct={pct} projected={projected}
                               rarity={rarity} missing={missing} extraLine={extraLine}
                               onToggleMode={toggleCopiesMode} />
              </div>
            )}
            <div className={cn("grid gap-4", sectionsCls)}>
              {sections.map((section) => {
                const sectionOwned = playsets
                  ? section.cards.reduce((n, c) => n + lookup(c), 0)
                  : section.cards.reduce((n, c) => n + (lookup(c) > 0 ? 1 : 0), 0);
                return (
                  <section key={`${key}-${section.color}`} className="border border-border">
                    <header
                      className="flex items-baseline gap-2 px-2.5 py-1.5"
                      style={{ background: COLOR_HEX[section.color] ?? COLOR_HEX.C }}
                    >
                      <span className="font-display text-[15px] tracking-[0.16em] text-bg">{section.label}</span>
                      <span className="font-display tabular-nums ml-auto text-[15px] text-bg/75">
                        {sectionOwned}/{section.cards.length * (playsets ? 4 : 1)}
                      </span>
                    </header>
                    <div className="flex flex-col gap-[1px] bg-border">
                      {section.cards.map((card) => (
                        <CardRow
                          key={card}
                          card={card}
                          owned={lookup(card)}
                          cost={isMobile ? lists.costs[card] : undefined}
                          touch={isMobile}
                          onSet={async (n) => { await saveCollectionCount(setCode, card, n); invalidate(); }}
                          onHover={isMobile ? undefined : (el) =>
                            setPreview({ sources: cardImageSources(card, setCode, cardImages),
                                         anchor: previewAnchorFor(el) })}
                          onLeave={() => setPreview(null)}
                        />
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {preview && <CardPreview {...preview} />}
    </div>
  );
}

function CardPreview({ sources, anchor }: { sources: string[]; anchor: PreviewAnchor }) {
  const { src, onError } = useFallbackImage(sources);
  if (!src) return null;
  return (
    <PreviewShell anchor={anchor}>
      <img src={src} alt="" onError={onError} className="w-full rounded-[10px]" />
    </PreviewShell>
  );
}


// The faint bar behind the solid one is the spreadsheet's "after packs + future" projection, and the
// owned count doubles as the playset/singles switch
function CompletionBar({
  label, owned, total, pct, projected, rarity, missing, extraLine, onToggleMode,
}: {
  label: string; owned: number; total: number; pct: number; projected: number | null; rarity: RarityStyle;
  missing: number;
  /** appended to the tooltip where the section has one, as rares do with their drafts estimate */
  extraLine: string | null;
  onToggleMode: () => void;
}) {
  const tip = [`${missing} singles missing`, extraLine].filter(Boolean).join(" - ");
  // Radix closes an uncontrolled tooltip on pointer down, and this trigger is also the mode switch
  const [hovered, setHovered] = useState(false);

  return (
    <Tooltip label={tip} open={hovered}>
      <button
        onClick={onToggleMode}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        className="group block w-full text-left px-2.5 py-1"
      >
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[14px] tracking-[0.16em]" style={{ color: rarity.color }}>
            {label}
          </span>
          <span
            className="font-display tabular-nums text-[16px] text-text ml-auto"
            style={hovered ? { color: rarity.color } : undefined}
          >
            {owned}/{total}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="relative h-[6px] flex-1 min-w-0 bg-bg overflow-hidden">
            {projected != null && (
              <i className="absolute inset-y-0 left-0 opacity-30"
                 style={{ width: `${Math.min(projected, 100)}%`, background: rarity.gradient }} />
            )}
            <i className="absolute inset-y-0 left-0"
               style={{ width: `${Math.min(pct, 100)}%`, background: rarity.gradient }} />
          </span>
          <span className="font-display tabular-nums text-[15px] shrink-0" style={{ color: rarity.color }}>
            {pct}%
          </span>
          {projected != null && (
            <span className="font-display tabular-nums text-[15px] shrink-0"
                  style={{ color: rarity.color, opacity: 0.7 }}>
              {projected}%
            </span>
          )}
        </div>
      </button>
    </Tooltip>
  );
}

/** Label and value are separate cells, so the whole block reads as one grid of equal boxes */
function CellLabel({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <Tooltip label={tooltip}>
      <div className="bg-surface px-2.5 py-1.5 flex items-center">
        <span className={cn("whitespace-nowrap", SUBLABEL_CLS)}>{label}</span>
      </div>
    </Tooltip>
  );
}

function EconomyCell({
  label, value, tooltip, onCommit,
}: { label: string; value: number; tooltip: string; onCommit: (n: number) => void }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => { setDraft(String(value)); }, [value]);
  return (
    <>
      <CellLabel label={label} tooltip={tooltip} />
      <Tooltip label={tooltip}>
        <label className="bg-bg flex items-center cursor-text hover:bg-surface2">
          <input
            value={draft}
            inputMode="numeric"
            aria-label={label}
            onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))}
            onFocus={(e) => e.currentTarget.select()}
            onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
            onBlur={() => { const n = Number(draft || 0); if (n !== value) onCommit(n); }}
            size={2}
            className="w-full min-w-0 px-2.5 py-1.5 bg-transparent text-center font-display tabular-nums
                       text-[17px] text-text outline-none"
          />
        </label>
      </Tooltip>
    </>
  );
}

/** Computed from the economy inputs, so it carries no input affordance */
function DerivedCell({ label, value, tooltip }: { label: string; value: number; tooltip: string }) {
  return (
    <>
      <CellLabel label={label} tooltip={tooltip} />
      <Tooltip label={tooltip}>
        <div className="bg-surface px-2.5 py-1.5 flex items-center justify-center">
          <span className="font-display tabular-nums text-[17px] text-subtle">{value}</span>
        </div>
      </Tooltip>
    </>
  );
}

function CardRow({
  card, owned, cost, touch = false, onSet, onHover, onLeave,
}: {
  card: string; owned: number;
  /** Scryfall mana cost, shown only where the row has room for it */
  cost?: string;
  /** a tap is the only gesture on a phone, so the count wraps 4 → 0 and the target grows */
  touch?: boolean;
  onSet: (n: number) => Promise<void>;
  onHover?: (el: HTMLElement) => void; onLeave: () => void;
}) {
  const nameRef = useShrinkToFit(frontFace(card), NAME_MAX_PX, NAME_MIN_PX);
  const nextCount = () => {
    if (owned < 4) return owned + 1;
    return touch ? 0 : null;
  };

  return (
    <div
      onMouseEnter={onHover && ((e) => onHover(e.currentTarget))}
      onMouseLeave={onLeave}
      className="bg-surface flex items-stretch"
    >
      <span
        ref={nameRef}
        className={cn("flex-1 min-w-0 self-center truncate pl-3 pr-2 font-spectral",
          touch ? "py-2" : "py-[3px]",
          owned === 0 ? "text-muted" : "text-text")}
      >
        {frontFace(card)}
      </span>
      {cost && (
        <span className="self-center shrink-0 pr-2">
          <ManaCost cost={cost} size={12} />
        </span>
      )}
      <button
        aria-label={touch
          ? `${frontFace(card)}, ${owned} owned. Tap to add, tap again past four to clear`
          : `${frontFace(card)}, ${owned} owned. Click to add, right click to remove`}
        onClick={() => { const n = nextCount(); if (n != null) void onSet(n); }}
        onContextMenu={(e) => { e.preventDefault(); if (owned > 0) void onSet(owned - 1); }}
        className={cn(
          "font-display tabular-nums text-[16px] shrink-0 text-center select-none",
          touch ? "w-11" : "w-9",
          "border-0 border-l border-border outline-none hover:bg-surface2",
          owned === 4 ? "bg-green/15 text-green" : "bg-bg text-text",
        )}
      >
        {owned}
      </button>
    </div>
  );
}

const NAME_MAX_PX = 15;
const NAME_MIN_PX = 10;

/** Steps a one-line label down until it fits its cell, so a long card name never ends in an ellipsis */
function useShrinkToFit(text: string, maxPx: number, minPx: number) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const measuredAt = useRef(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    measuredAt.current = 0;
    const fit = () => {
      const width = el.clientWidth;
      if (!width || width === measuredAt.current) {
        return;
      }
      measuredAt.current = width;
      el.style.fontSize = `${maxPx}px`;
      if (el.scrollWidth <= width) {
        return;
      }
      let size = Math.max(minPx, Math.floor((maxPx * width) / el.scrollWidth));
      el.style.fontSize = `${size}px`;
      while (size > minPx && el.scrollWidth > width) {
        size -= 1;
        el.style.fontSize = `${size}px`;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    const refitAfterFonts = () => { measuredAt.current = 0; fit(); };
    document.fonts?.ready.then(refitAfterFonts);
    return () => observer.disconnect();
  }, [text, maxPx, minPx]);

  return ref;
}
