import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate, useParams } from "react-router-dom";
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
import { CardArt, CardImageStack, cardDataHref } from "../components/pod/cardData/CardDetailParts";
import { CardDetailRow } from "../components/pod/cardData/CardDetailRow";
import { useCursorTooltip, type CursorTooltipBinding } from "../components/CursorTooltip";
import { cardSlug } from "../data/podCardDecks";
import { winRateColor } from "../data/winRate";
import { cn } from "../lib/utils";
import { useIsMobile } from "../lib/use-is-mobile";
import { cardArtSources, cardImageSources, useBoardCardImages } from "../data/cardImages";
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
  const { board, card: cardParam } = useParams<{ board: string; card: string }>();
  const boardCode = (board ?? "PEASANT").toUpperCase();
  const label = cardDataLabel(boardCode);
  const navigate = useNavigate();
  const { search } = useLocation();

  const { data, isPending } = usePodCardStats(boardCode);
  const allRows = useMemo(() => data ?? [], [data]);
  const { data: sets } = useSets();

  const isMobile = useIsMobile();
  const [tab, setTab] = useState<CardDataTab>("cards");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [season, setSeason] = useState<string | null>(ALL_SEASONS);
  const [sortKey, setSortKey] = useState<keyof PodCard>("alsa");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [minDrafts, setMinDrafts] = useState(1);
  const [filters, setFilters] = useState<PodCardFilters>(EMPTY_POD_CARD_FILTERS);
  const [cardSearch, setCardSearch] = useState("");
  const [preview, setPreview] = useState<{ sources: string[]; anchor: PreviewAnchor } | null>(null);

  const chromeRef = useRef<HTMLDivElement>(null);
  const [chromeHeight, setChromeHeight] = useState(0);
  useLayoutEffect(() => {
    const el = chromeRef.current;
    if (!el) {
      return;
    }
    const measure = () => setChromeHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const hovering = useRef(false);
  const hoverCard = (card: PodCard, el: HTMLElement) => {
    if (isMobile || openSet.has(card.name)) {
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
  const [openNames, setOpenNames] = useState<string[]>([]);
  const clickedCard = useRef<string | null>(null);
  const toggleCard = (card: PodCard) => {
    leaveCard();
    const withoutCard = openNames.filter((name) => name !== card.name);
    const closing = openSet.has(card.name);
    const next = closing ? withoutCard : [...withoutCard, card.name];
    const urlCard = next[next.length - 1] ?? null;
    setOpenNames(next);
    clickedCard.current = urlCard;
    navigate(cardDataHref(boardCode, urlCard, search), { replace: true });
  };

  const seasons = useMemo(() => orderedSeasons(allRows, sets), [allRows, sets]);
  const cards = useMemo(() => {
    const scoped = season == null ? allRows : allRows.filter((r) => r.season === season);
    return aggregatePodCards(scoped);
  }, [allRows, season]);

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
  const [visibleKeys, setVisibleKeys] = useState<ReadonlySet<string>>(() => new Set());

  const options = useMemo(() => podCardFilterOptions(cards), [cards]);

  const rows = useMemo(() => {
    const needle = cardSearch.trim().toLowerCase();
    const kept = cards.filter(
      (c) => c.drafts >= minDrafts && cardMatchesFilters(c, filters) && (!needle || c.name.toLowerCase().includes(needle)),
    );
    return sortPodCards(kept, sortKey, sortDir);
  }, [cards, minDrafts, filters, cardSearch, sortKey, sortDir]);

  const selected = useMemo(() => {
    if (!cardParam) {
      return null;
    }
    const slug = cardParam.toLowerCase();
    for (const card of cards) {
      if (cardSlug(card.name) === slug) {
        return card;
      }
    }
    for (const card of aggregatePodCards(allRows)) {
      if (cardSlug(card.name) === slug) {
        return card;
      }
    }
    return null;
  }, [cardParam, cards, allRows]);

  const openSet = useMemo(
    () => new Set(selected ? [...openNames, selected.name] : openNames),
    [openNames, selected],
  );

  const visibleItems = useMemo(() => {
    const items: { name: string; set: string | null }[] = selected ? [{ name: selected.name, set: selected.set }] : [];
    for (const item of imageItems) {
      if (visibleKeys.has(rowImageKey(item.name, item.set))) {
        items.push(item);
      }
    }
    return items;
  }, [visibleKeys, selected, imageItems]);
  const cardImages = useBoardCardImages(imageItems, visibleItems);

  const tableBodyRef = useRef<HTMLTableSectionElement>(null);
  const mobileScrollerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const body = tableBodyRef.current;
    if (!body) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const seen: string[] = [];
        for (const entry of entries) {
          const key = (entry.target as HTMLElement).dataset.imageKey;
          if (entry.isIntersecting && key) {
            seen.push(key);
          }
        }
        setVisibleKeys((prev) => (seen.every((key) => prev.has(key)) ? prev : new Set([...prev, ...seen])));
      },
      { root: isMobile ? mobileScrollerRef.current : null, rootMargin: "400px 0px" },
    );
    for (const row of body.querySelectorAll<HTMLElement>("tr[data-image-key]")) {
      observer.observe(row);
    }
    return () => observer.disconnect();
  }, [rows, isMobile]);

  const selectedRowRef = useRef<HTMLTableRowElement>(null);
  const handledCard = useRef<string | null>(null);
  useLayoutEffect(() => {
    const name = selected?.name ?? null;
    if (name === handledCard.current) {
      return;
    }
    const fromUrl = name != null && name !== clickedCard.current;
    if (fromUrl) {
      const row = selectedRowRef.current;
      if (!row) {
        return;
      }
      pinRowBelowStickyHeader(row, isMobile ? mobileScrollerRef.current : null, chromeHeight);
      setOpenNames((prev) => (prev.includes(name) ? prev : [...prev, name]));
    }
    handledCard.current = name;
    clickedCard.current = null;
  });

  const rowTooltip = useCursorTooltip();
  const rowTooltipFor = (card: PodCard) =>
    isMobile ? undefined : rowTooltip.bind(openSet.has(card.name) ? "Close Breakdown" : "Open Card Breakdown");

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
      {rowTooltip.layer}
    </>
  );

  const detailRow = (card: PodCard, mobile: boolean) =>
    openSet.has(card.name) ? (
      <CardDetailRow
        boardCode={boardCode}
        card={card}
        imageSources={cardImageSources(card.name, card.set, cardImages)}
        artSources={cardArtSources(card.name, card.set, cardImages)}
        season={season}
        search={search}
        colSpan={POD_CARD_COLUMNS.length + (mobile ? 2 : 1)}
        mobile={mobile}
      />
    ) : null;

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

        <div ref={chromeRef} className="sticky top-0 z-30">
        <div className="relative z-10 px-4 py-3 border-b border-border bg-surface flex items-center gap-3">
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

        <div className="page-chrome bg-bg">
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
                search={cardSearch}
                setSearch={setCardSearch}
              />
            </div>
          )}
        </div>
        </div>

        <main className="flex-1">
          {tab === "archetypes" ? (
            <div className="flex flex-col gap-4 p-4">
              <ArchetypePanel setCode={boardCode} season={season} sets={sets} />
              <PodRecentTrophies setCode={boardCode} season={season} sets={sets} />
            </div>
          ) : (
            <div ref={mobileScrollerRef} className="overflow-auto" style={{ maxHeight: `calc(100dvh - ${chromeHeight}px)` }}>
              <table className="table-fixed border-collapse text-[13px]" style={{ width: MOBILE_TABLE_W }}>
                <colgroup>
                  <col style={{ width: MOBILE_ART_W }} />
                  <col style={{ width: MOBILE_NAME_W }} />
                  {POD_CARD_COLUMNS.map((col) => (
                    <col key={col.key} style={{ width: MOBILE_METRIC_W[col.key] ?? 60 }} />
                  ))}
                </colgroup>
                <thead>
                  <tr className="text-left">
                    <th
                      className="sticky left-0 top-0 z-30 bg-bg pl-2 py-2 border-b border-border"
                      aria-hidden
                    />
                    <th
                      className="sticky top-0 z-20 bg-bg border-b border-border p-0 text-left font-normal font-display tracking-[0.2em] text-[11px] text-muted"
                    >
                      <SortHeaderButton
                        label="CARD NAME"
                        active={sortKey === "name"}
                        dir={sortDir}
                        onClick={() => onSort("name")}
                        fill
                        align="left"
                        className="pr-2 py-2"
                      />
                    </th>
                    {POD_CARD_COLUMNS.map((col, i) => (
                      <th
                        key={col.key}
                        className="sticky top-0 z-20 bg-bg border-b border-border whitespace-nowrap p-0 text-right font-normal font-display tracking-[0.2em] text-[11px] text-muted"
                      >
                        <MetricHeader
                          col={col}
                          sortKey={sortKey}
                          sortDir={sortDir}
                          onSort={onSort}
                          mobile
                          isLast={i === POD_CARD_COLUMNS.length - 1}
                        />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody ref={tableBodyRef}>
                  {isPending ? (
                    <SkeletonRows sticky />
                  ) : rows.length === 0 ? (
                    <StateRow text={cards.length === 0 ? "No cube drafts on record yet" : "No cards match these filters"} />
                  ) : (
                    rows.map((card) => (
                      <Fragment key={`${card.name}|${card.set}`}>
                        <CardRow
                          card={card}
                          sources={cardArtSources(card.name, card.set, cardImages)}
                          rowRef={selected?.name === card.name ? selectedRowRef : undefined}
                          active={openSet.has(card.name)}
                          onHover={hoverCard}
                          onLeave={leaveCard}
                          onOpen={toggleCard}
                          sticky
                        />
                        {detailRow(card, true)}
                      </Fragment>
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
          search={cardSearch}
          setSearch={setCardSearch}
        />
      </div>

      <main className="relative flex-1 lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="min-w-0">
          <table className="w-full table-fixed border-collapse text-[13px]">
            <colgroup>
              <col style={{ width: "34%" }} />
              {POD_CARD_COLUMNS.map((col) => (
                <col key={col.key} />
              ))}
            </colgroup>
            <thead>
              <tr className="text-left">
                <th className="sticky top-0 z-20 bg-bg border-b border-border p-0 text-left font-normal font-display tracking-[0.2em] text-[11px] text-muted">
                  <SortHeaderButton
                    label="CARD NAME"
                    active={sortKey === "name"}
                    dir={sortDir}
                    onClick={() => onSort("name")}
                    fill
                    align="left"
                    className="pl-5 md:pl-10 pr-3 py-2"
                  />
                </th>
                {POD_CARD_COLUMNS.map((col, i) => (
                  <th
                    key={col.key}
                    className="sticky top-0 z-20 bg-bg border-b border-border whitespace-nowrap p-0 text-right font-normal font-display tracking-[0.2em] text-[11px] text-muted"
                  >
                    <MetricHeader
                      col={col}
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={onSort}
                      isLast={i === POD_CARD_COLUMNS.length - 1}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody ref={tableBodyRef}>
              {isPending ? (
                <SkeletonRows />
              ) : rows.length === 0 ? (
                <StateRow text={cards.length === 0 ? "No cube drafts on record yet" : "No cards match these filters"} />
              ) : (
                rows.map((card) => (
                  <Fragment key={`${card.name}|${card.set}`}>
                    <CardRow
                      card={card}
                      sources={cardArtSources(card.name, card.set, cardImages)}
                      rowRef={selected?.name === card.name ? selectedRowRef : undefined}
                      active={openSet.has(card.name)}
                      tooltip={rowTooltipFor(card)}
                      onHover={hoverCard}
                      onLeave={leaveCard}
                      onOpen={toggleCard}
                    />
                    {detailRow(card, false)}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>

        <aside className="flex flex-col gap-4 p-4 border-t border-border lg:border-t-0 lg:sticky lg:top-4 lg:self-start">
          <ArchetypePanel setCode={boardCode} season={season} sets={sets} />
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
  isLast = false,
}: {
  col: (typeof POD_CARD_COLUMNS)[number];
  sortKey: keyof PodCard;
  sortDir: SortDir;
  onSort: (key: keyof PodCard) => void;
  mobile?: boolean;
  isLast?: boolean;
}) {
  const hasSuffix = col.key === "playRate";
  const cellPadding = mobile
    ? cn("px-2 py-2", isLast && "pr-1")
    : cn("px-3 py-2", isLast && "pr-2 md:pr-7");
  return (
    <div className={cn("flex justify-end", cellPadding)}>
      <Tooltip label={col.title} side="top">
        <SortHeaderButton
          label={mobile && col.shortLabel ? col.shortLabel : col.label}
          active={sortKey === col.key}
          dir={sortDir}
          onClick={() => onSort(col.key)}
          fill
          grow={false}
          trailing={hasSuffix ? <span className="ml-1 w-7 shrink-0" aria-hidden /> : null}
        />
      </Tooltip>
    </div>
  );
}

function CardRow({
  card,
  sources,
  sticky = false,
  rowRef,
  active,
  tooltip,
  onHover,
  onLeave,
  onOpen,
}: {
  card: PodCard;
  sources: string[];
  sticky?: boolean;
  rowRef?: RefObject<HTMLTableRowElement>;
  active: boolean;
  tooltip?: CursorTooltipBinding;
  onHover: (card: PodCard, el: HTMLElement) => void;
  onLeave: () => void;
  onOpen: (card: PodCard) => void;
}) {
  const nameClass = cn("truncate font-display text-[18px] tracking-[0.02em]", active ? "text-green" : "text-text");
  return (
    <tr
      ref={rowRef}
      {...tooltip}
      data-image-key={rowImageKey(card.name, card.set)}
      className={cn(
        "border-b border-bg cursor-pointer",
        active ? "bg-surface2" : "bg-surface",
        sticky ? "group hover:bg-surface2" : "hover:bg-surface2",
      )}
      onClick={() => onOpen(card)}
    >
      {sticky ? (
        <>
          <td
            className={cn("sticky left-0 z-10 group-hover:bg-surface2 pl-2 pr-1 py-2", active ? "bg-surface2" : "bg-surface")}
            onMouseEnter={(e) => onHover(card, e.currentTarget)}
            onMouseLeave={onLeave}
          >
            <CardArt sources={sources} name={card.name} />
          </td>
          <td className="pr-2 py-2">
            <div className={nameClass}>{card.name}</div>
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
            <div className={cn("min-w-0", nameClass)}>{card.name}</div>
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

function rowImageKey(name: string, set: string | null): string {
  return `${set ?? ""}|${name}`;
}

function pinRowBelowStickyHeader(
  row: HTMLTableRowElement,
  scroller: HTMLElement | null,
  chromeHeight: number,
): void {
  const headHeight = row.closest("table")?.querySelector("thead")?.getBoundingClientRect().height ?? 0;
  if (!scroller) {
    window.scrollTo({ top: row.getBoundingClientRect().top + window.scrollY - headHeight });
    return;
  }
  const scrollerRect = scroller.getBoundingClientRect();
  const rowOffset = row.getBoundingClientRect().top - scrollerRect.top + scroller.scrollTop;
  scroller.scrollTo({ top: rowOffset - headHeight });
  window.scrollTo({ top: scrollerRect.top + window.scrollY - chromeHeight });
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
