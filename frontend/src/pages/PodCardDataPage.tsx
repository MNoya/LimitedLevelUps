import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams } from "react-router-dom";
import { SlidersHorizontal } from "lucide-react";

import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { PodCardFilterBar } from "../components/PodCardFilterBar";
import { ArchetypePanel } from "../components/ArchetypePanel";
import { PodRecentTrophies } from "../components/PodRecentTrophies";
import { SortHeaderButton } from "../components/SortHeader";
import { PreviewShell, previewAnchorFor, type PreviewAnchor } from "../components/TierGrid";
import { Tooltip } from "../components/Tooltip";
import { BoardWindowSelector, type BoardWindowOption } from "../components/BoardWindowSelector";
import { TabButton } from "../components/TabButton";
import { CalendarRange } from "../components/Icons";
import { AVATAR_CLIP, SetGlyph } from "../components/Brand";
import { winRateColor } from "../data/winRate";
import { cn } from "../lib/utils";
import { useIsMobile } from "../lib/use-is-mobile";
import { cardArtSources, cardImageSources, useCardImageMap } from "../data/cardImages";
import { usePodCardStats, useSets } from "../data/hooks";
import type { SetSummary } from "../types/leaderboard";
import {
  POD_CARD_COLUMNS,
  EMPTY_POD_CARD_FILTERS,
  activePodCardFilterCount,
  aggregatePodCards,
  cardMatchesFilters,
  podCardFilterOptions,
  cardDataLabel,
  sortPodCards,
  type PodCard,
  type PodCardStatRow,
  type PodCardFilters,
  type SortDir,
} from "../data/podCards";

type CardDataTab = "cards" | "archetypes";

const ALL_SEASONS = null;

const NUM_CLASS = "font-num font-medium text-[15px] text-text";

const MUTED_COLUMNS = new Set<keyof PodCard>(["seen", "picked"]);

const MOBILE_METRIC_W: Partial<Record<keyof PodCard, number>> = {
  seen: 54,
  picked: 56,
  alsa: 50,
  ata: 50,
  gamesPlayed: 54,
  playRate: 86,
  winRate: 58,
};
const MOBILE_ART_W = 44;
const MOBILE_NAME_W = 184;
const MOBILE_TABLE_W =
  MOBILE_ART_W + MOBILE_NAME_W + Object.values(MOBILE_METRIC_W).reduce((sum, w) => sum + (w ?? 60), 0);

function orderedSeasons(rows: PodCardStatRow[], sets: SetSummary[] | undefined): string[] {
  const present = [...new Set(rows.map((r) => r.season))].filter((s) => s !== "CUBE" && s !== "UNKNOWN");
  const rank = new Map((sets ?? []).map((s, i) => [s.code, i]));
  present.sort((a, b) => (rank.get(a) ?? 999) - (rank.get(b) ?? 999) || a.localeCompare(b));
  return present;
}

export function PodCardDataPage() {
  const { board } = useParams<{ board: string }>();
  const boardCode = (board ?? "PEASANT").toUpperCase();
  const label = cardDataLabel(boardCode);

  const { data, isPending } = usePodCardStats(boardCode);
  const allRows = useMemo(() => data ?? [], [data]);
  const { data: sets } = useSets();

  const isMobile = useIsMobile();
  const [tab, setTab] = useState<CardDataTab>("cards");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [season, setSeason] = useState<string | null>(ALL_SEASONS);
  const [sortKey, setSortKey] = useState<keyof PodCard>("seen");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [minDrafts, setMinDrafts] = useState(1);
  const [filters, setFilters] = useState<PodCardFilters>(EMPTY_POD_CARD_FILTERS);
  const [search, setSearch] = useState("");
  const [preview, setPreview] = useState<{ sources: string[]; anchor: PreviewAnchor } | null>(null);
  const [modal, setModal] = useState<string[] | null>(null);

  const hovering = useRef(false);
  const hoverCard = (card: PodCard, el: HTMLElement) => {
    if (isMobile) {
      return;
    }
    hovering.current = true;
    const sources = cardImageSources(card.name, card.set, cardImages);
    if (sources.length === 0) {
      return;
    }
    const img = new Image();
    img.onload = () => {
      if (hovering.current) {
        setPreview({ sources, anchor: previewAnchorFor(el) });
      }
    };
    img.src = sources[0];
    if (img.complete) {
      img.onload(new Event("load"));
    }
  };
  const leaveCard = () => {
    hovering.current = false;
    setPreview(null);
  };
  const openCard = (card: PodCard) => {
    const sources = cardImageSources(card.name, card.set, cardImages);
    if (sources.length > 0) {
      setModal(sources);
    }
  };
  const overlays = (
    <>
      {preview
        ? createPortal(
            <PreviewShell anchor={preview.anchor}>
              <CardImageStack sources={preview.sources} />
            </PreviewShell>,
            document.body,
          )
        : null}
      {modal
        ? createPortal(
            <div
              className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-6"
              onClick={() => setModal(null)}
            >
              <div className="w-[min(360px,80vw)]">
                <CardImageStack sources={modal} />
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );

  const seasons = useMemo(() => orderedSeasons(allRows, sets), [allRows, sets]);
  const cards = useMemo(() => {
    const scoped = season == null ? allRows : allRows.filter((r) => r.season === season);
    return aggregatePodCards(scoped);
  }, [allRows, season]);

  // Resolve art for the whole board once (stable across season filters) so the shared image cache isn't re-queried
  const imageItems = useMemo(() => {
    const seen = new Set<string>();
    const items: { name: string; set: string | null }[] = [];
    for (const row of allRows) {
      const key = `${row.card_set ?? ""}|${row.card_name}`;
      if (!seen.has(key)) {
        seen.add(key);
        items.push({ name: row.card_name, set: row.card_set });
      }
    }
    return items;
  }, [allRows]);
  const cardImages = useCardImageMap(imageItems);

  const options = useMemo(() => podCardFilterOptions(cards), [cards]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const kept = cards.filter(
      (c) => c.drafts >= minDrafts && cardMatchesFilters(c, filters) && (!needle || c.name.toLowerCase().includes(needle)),
    );
    return sortPodCards(kept, sortKey, sortDir);
  }, [cards, minDrafts, filters, search, sortKey, sortDir]);

  const onSort = (key: keyof PodCard) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (isMobile) {
    const filterCount = activePodCardFilterCount(filters);
    const seasonAll = "ALL";
    const seasonOptions: BoardWindowOption[] = [
      { value: seasonAll, label: "ALL SEASONS", icon: <CalendarRange size={20} className="text-white shrink-0" /> },
      ...seasons.map((code) => ({ value: code, label: `${code} SEASON`, glyph: code })),
    ];
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
        <AppHeader subtitle={label.toUpperCase()} />

        <div className="relative z-30 px-4 py-3 border-b border-border bg-surface flex items-center gap-3">
          <SetGlyph code="CUBE" size={40} className="text-text shrink-0" />
          <span className="min-w-0 truncate font-display tracking-[0.04em]" style={{ fontSize: 24, lineHeight: 0.9 }}>
            {label.toUpperCase()}
          </span>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {tab === "cards" && (
              <button
                type="button"
                onClick={() => setFiltersOpen((o) => !o)}
                aria-expanded={filtersOpen}
                aria-label="Filters"
                className={cn(
                  "relative flex h-9 w-9 shrink-0 items-center justify-center border transition-colors",
                  filtersOpen || filterCount > 0 ? "border-green text-green" : "border-border2 text-muted",
                )}
              >
                <SlidersHorizontal size={16} />
                {filterCount > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-green px-1 text-[10px] font-bold text-bg">
                    {filterCount}
                  </span>
                )}
              </button>
            )}
            <div className="w-[150px]">
              <BoardWindowSelector
                value={season ?? seasonAll}
                options={seasonOptions}
                onSelect={(v) => setSeason(v === seasonAll ? ALL_SEASONS : v)}
                variant="mobile"
              />
            </div>
          </div>
        </div>

        <div className="page-chrome sticky top-0 z-20 bg-bg">
          <div className="flex items-stretch border-b border-border">
            <TabButton active={tab === "cards"} onClick={() => setTab("cards")}>
              CARD DATA
            </TabButton>
            <TabButton active={tab === "archetypes"} onClick={() => setTab("archetypes")}>
              DECK COLORS
            </TabButton>
          </div>
          {tab === "cards" && filtersOpen && (
            <div className="border-b border-border px-4 py-3">
              <PodCardFilterBar
                options={options}
                filters={filters}
                setFilters={setFilters}
                minDrafts={minDrafts}
                setMinDrafts={setMinDrafts}
                search={search}
                setSearch={setSearch}
              />
            </div>
          )}
        </div>

        <main className="flex-1">
          {tab === "archetypes" ? (
            <div className="flex flex-col gap-4 p-4">
              <ArchetypePanel setCode={boardCode} season={season} />
              <PodRecentTrophies setCode={boardCode} season={season} sets={sets} />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table-fixed border-collapse text-[13px]" style={{ width: MOBILE_TABLE_W }}>
                <colgroup>
                  <col style={{ width: MOBILE_ART_W }} />
                  <col style={{ width: MOBILE_NAME_W }} />
                  {POD_CARD_COLUMNS.map((col) => (
                    <col key={col.key} style={{ width: MOBILE_METRIC_W[col.key] ?? 60 }} />
                  ))}
                </colgroup>
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="sticky left-0 z-10 bg-bg pl-2 py-2" aria-hidden />
                    <th className="pr-2 py-2 text-left font-normal font-display tracking-[0.2em] text-[11px] text-muted">
                      <SortHeaderButton
                        label="CARD NAME"
                        active={sortKey === "name"}
                        dir={sortDir}
                        onClick={() => onSort("name")}
                        inline
                      />
                    </th>
                    {POD_CARD_COLUMNS.map((col, i) => (
                      <th
                        key={col.key}
                        className={cn(
                          "whitespace-nowrap px-2 py-2 text-right font-normal font-display tracking-[0.2em] text-[11px] text-muted",
                          i === POD_CARD_COLUMNS.length - 1 && "pr-3",
                        )}
                      >
                        <MetricHeader col={col} sortKey={sortKey} sortDir={sortDir} onSort={onSort} mobile />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isPending ? (
                    <SkeletonRows sticky />
                  ) : rows.length === 0 ? (
                    <StateRow text={cards.length === 0 ? "No cube drafts on record yet" : "No cards match these filters"} />
                  ) : (
                    rows.map((card) => (
                      <CardRow
                        key={`${card.name}|${card.set}`}
                        card={card}
                        sources={cardArtSources(card.name, card.set, cardImages)}
                        onHover={hoverCard}
                        onLeave={leaveCard}
                        onOpen={openCard}
                        sticky
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </main>

        <Footer className="mt-auto px-5 py-4 shrink-0" />
        {overlays}
      </div>
    );
  }

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle={label.toUpperCase()} />

      <div className="relative px-5 md:px-10 py-5 border-b border-border bg-surface flex items-center gap-5 md:gap-6">
        <SetGlyph code="CUBE" size={84} className="text-text" />
        <div className="flex items-baseline gap-3.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {label.toUpperCase()}
          </span>
          <span className="font-display text-[22px] text-muted tracking-[0.06em]">CARD DATA</span>
        </div>
        <div className="flex-1" />
        {seasons.length > 0 && (
          <div className="hidden md:flex flex-wrap items-center justify-end gap-1.5">
            <SeasonChip code="CUBE" label="ALL" active={season == null} onClick={() => setSeason(ALL_SEASONS)} />
            {seasons.map((code) => (
              <SeasonChip
                key={code}
                code={code}
                label={code}
                active={season === code}
                onClick={() => setSeason(code)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="px-5 md:px-10 py-3 border-b border-border">
        <PodCardFilterBar
          options={options}
          filters={filters}
          setFilters={setFilters}
          minDrafts={minDrafts}
          setMinDrafts={setMinDrafts}
          search={search}
          setSearch={setSearch}
        />
      </div>

      <main className="relative flex-1 lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full table-fixed border-collapse text-[13px]">
            <colgroup>
              <col style={{ width: "34%" }} />
              {POD_CARD_COLUMNS.map((col) => (
                <col key={col.key} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pl-5 md:pl-10 pr-3 py-2 text-left font-normal font-display tracking-[0.2em] text-[11px] text-muted">
                  <SortHeaderButton
                    label="CARD NAME"
                    active={sortKey === "name"}
                    dir={sortDir}
                    onClick={() => onSort("name")}
                    inline
                  />
                </th>
                {POD_CARD_COLUMNS.map((col, i) => (
                  <th
                    key={col.key}
                    className={cn(
                      "whitespace-nowrap px-3 py-2 text-right font-normal font-display tracking-[0.2em] text-[11px] text-muted",
                      i === POD_CARD_COLUMNS.length - 1 && "pr-5 md:pr-10",
                    )}
                  >
                    <MetricHeader col={col} sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isPending ? (
                <SkeletonRows />
              ) : rows.length === 0 ? (
                <StateRow text={cards.length === 0 ? "No cube drafts on record yet" : "No cards match these filters"} />
              ) : (
                rows.map((card) => (
                  <CardRow
                    key={`${card.name}|${card.set}`}
                    card={card}
                    sources={cardArtSources(card.name, card.set, cardImages)}
                    onHover={hoverCard}
                    onLeave={leaveCard}
                    onOpen={openCard}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        <aside className="flex flex-col gap-4 p-4 border-t border-border lg:border-t-0">
          <ArchetypePanel setCode={boardCode} season={season} />
          <PodRecentTrophies setCode={boardCode} season={season} sets={sets} />
        </aside>
        <div className="hidden lg:block pointer-events-none absolute inset-y-0 right-[340px] w-px bg-border" />
      </main>

      <Footer className="mt-auto px-5 py-4 md:pt-5 md:pb-3 shrink-0" />
      {overlays}
    </div>
  );
}

const CHIP_CHAMFER = "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)";

function SeasonChip({
  code,
  label,
  active,
  onClick,
}: {
  code?: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group block cursor-pointer"
      style={{ clipPath: CHIP_CHAMFER, background: active ? "#2ee85c" : "#3b4458", padding: 1, minHeight: 42 }}
    >
      <span
        className={cn(
          "flex h-full items-center justify-center gap-[7px] px-[17px] font-display",
          active ? "bg-green text-bg" : "bg-surface text-text group-hover:bg-surface2",
        )}
        style={{ clipPath: CHIP_CHAMFER, minHeight: 40 }}
      >
        {code ? <SetGlyph code={code} size={22} className={active ? "text-bg" : "text-text"} /> : null}
        <span className="text-[20px] tracking-[0.06em] leading-none">{label}</span>
      </span>
    </button>
  );
}

function MetricHeader({
  col,
  sortKey,
  sortDir,
  onSort,
  mobile = false,
}: {
  col: (typeof POD_CARD_COLUMNS)[number];
  sortKey: keyof PodCard;
  sortDir: SortDir;
  onSort: (key: keyof PodCard) => void;
  mobile?: boolean;
}) {
  const hasSuffix = col.key === "playRate";
  return (
    <Tooltip label={col.title} side="top">
      <span className="inline-flex items-baseline align-middle">
        <SortHeaderButton
          label={mobile && col.shortLabel ? col.shortLabel : col.label}
          active={sortKey === col.key}
          dir={sortDir}
          onClick={() => onSort(col.key)}
          inline
        />
        {hasSuffix ? <span className="ml-1 w-7 shrink-0" aria-hidden /> : null}
      </span>
    </Tooltip>
  );
}

function CardRow({
  card,
  sources,
  sticky = false,
  onHover,
  onLeave,
  onOpen,
}: {
  card: PodCard;
  sources: string[];
  sticky?: boolean;
  onHover: (card: PodCard, el: HTMLElement) => void;
  onLeave: () => void;
  onOpen: (card: PodCard) => void;
}) {
  return (
    <tr
      className={cn("bg-surface border-b border-bg cursor-pointer", sticky ? "group hover:bg-surface2" : "hover:bg-surface2")}
      onClick={() => onOpen(card)}
    >
      {sticky ? (
        <>
          <td
            className="sticky left-0 z-10 bg-surface group-hover:bg-surface2 pl-2 pr-1 py-2"
            onMouseEnter={(e) => onHover(card, e.currentTarget)}
            onMouseLeave={onLeave}
          >
            <CardArt sources={sources} name={card.name} />
          </td>
          <td className="pr-2 py-2">
            <div className="truncate font-display text-[18px] tracking-[0.02em] text-text">{card.name}</div>
          </td>
        </>
      ) : (
        <td
          className="pl-5 md:pl-10 pr-3 py-2"
          onMouseEnter={(e) => onHover(card, e.currentTarget)}
          onMouseLeave={onLeave}
        >
          <div className="flex items-center gap-2.5">
            <CardArt sources={sources} name={card.name} />
            <div className="min-w-0 truncate font-display text-[18px] tracking-[0.02em] text-text">{card.name}</div>
          </div>
        </td>
      )}
      {POD_CARD_COLUMNS.map((col, i) => {
        const last = i === POD_CARD_COLUMNS.length - 1;
        const text = col.format(card);
        const empty = text === "—";
        return (
          <td
            key={col.key}
            className={cn(
              "whitespace-nowrap px-2 md:px-3 py-2 text-right",
              NUM_CLASS,
              last && "pr-3 md:pr-10",
              (empty || MUTED_COLUMNS.has(col.key)) && "text-muted",
            )}
            style={col.key === "winRate" && !empty ? { color: winRateColor(card.winRate) } : undefined}
          >
            {col.key === "playRate" && card.playRate != null ? (
              <span className="flex items-baseline justify-end">
                <span>{text}</span>
                <span className="ml-1 w-7 shrink-0 text-left font-num text-[11px] text-subtle">({card.maindecked})</span>
              </span>
            ) : (
              text
            )}
          </td>
        );
      })}
    </tr>
  );
}

function CardArt({ sources, name }: { sources: string[]; name: string }) {
  const [index, setIndex] = useState(0);
  const src = sources[index] ?? null;
  if (!src) {
    return <div className="h-9 w-12 shrink-0 bg-surface2" style={{ clipPath: AVATAR_CLIP }} aria-hidden />;
  }
  return (
    <img
      src={src}
      alt={name}
      loading="lazy"
      decoding="async"
      onError={() => setIndex((i) => i + 1)}
      className="h-9 w-12 shrink-0 object-cover object-center"
      style={{ clipPath: AVATAR_CLIP }}
    />
  );
}

function CardImageStack({ sources }: { sources: string[] }) {
  const [index, setIndex] = useState(0);
  const src = sources[index] ?? null;
  if (!src) {
    return <div className="w-full rounded-[10px] bg-surface2" style={{ aspectRatio: "488 / 680" }} aria-hidden />;
  }
  return (
    <img
      src={src}
      alt=""
      decoding="async"
      onError={() => setIndex((i) => i + 1)}
      className="w-full rounded-[10px]"
      style={{ aspectRatio: "488 / 680" }}
    />
  );
}

function StateRow({ text }: { text: string }) {
  return (
    <tr>
      <td colSpan={POD_CARD_COLUMNS.length + 2} className="px-5 md:px-10 py-10 text-center text-[13px] text-muted">
        {text}
      </td>
    </tr>
  );
}

function SkeletonRows({ sticky = false }: { sticky?: boolean }) {
  const bar = "h-3.5 bg-surface2 animate-pulse";
  return (
    <>
      {Array.from({ length: 12 }).map((_, i) => (
        <tr key={i} className="bg-surface border-b border-bg">
          {sticky ? (
            <>
              <td className="sticky left-0 z-10 bg-surface pl-2 pr-1 py-2">
                <div className="h-9 w-12 bg-surface2 animate-pulse" style={{ clipPath: AVATAR_CLIP }} />
              </td>
              <td className="pr-2 py-2">
                <div className={bar} style={{ width: `${55 + ((i * 7) % 35)}%` }} />
              </td>
            </>
          ) : (
            <td className="pl-5 md:pl-10 pr-3 py-2">
              <div className="flex items-center gap-2.5">
                <div className="h-9 w-12 shrink-0 bg-surface2 animate-pulse" style={{ clipPath: AVATAR_CLIP }} />
                <div className={bar} style={{ width: `${45 + ((i * 7) % 35)}%` }} />
              </div>
            </td>
          )}
          {POD_CARD_COLUMNS.map((col, j) => {
            const last = j === POD_CARD_COLUMNS.length - 1;
            return (
              <td key={col.key} className={cn("px-2 md:px-3 py-2", last && "pr-3 md:pr-10")}>
                <div className={cn(bar, "ml-auto w-8")} />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
