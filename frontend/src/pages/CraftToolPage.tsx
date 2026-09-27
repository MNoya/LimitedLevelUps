import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { PageShell } from "../components/PageShell";
import { SetGlyphDropdown } from "../components/SetGlyphDropdown";
import { CopyTextButton } from "../components/CopyTextButton";
import { RaritySetGlyph } from "../components/Brand";
import { WildcardIcon } from "../components/WildcardIcon";
import { ChevronRight, Copy } from "lucide-react";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { useSets } from "../data/hooks";
import { isCubeCode } from "../data/utils";
import { ACTIVE_SET_CODE } from "../data/constants";
import { P0P1_CONTESTS } from "../data/p0p1Slots";
import {
  isCraftSetCode,
  craftListLabel,
  craftListText,
  craftListTitle,
  craftListWildcards,
  useCraftLists,
  type CraftList,
} from "../data/craftLists";
import type { SetSummary } from "../types/leaderboard";

export function CraftToolPage() {
  const mtgaIcon = `${import.meta.env.BASE_URL}platforms/mtga.png`;
  const steps = [
    {
      label: "Copy a list",
      shortLabel: "Copy",
      icon: <Copy size={16} strokeWidth={2.25} className="shrink-0 text-text" />,
    },
    {
      label: "Import in Arena",
      shortLabel: "Import",
      icon: <img src={mtgaIcon} alt="" className="h-4 w-auto shrink-0" />,
    },
    { label: "Craft All", shortLabel: "Craft All", icon: <WildcardIcon rarity="rare" size={16} /> },
  ];
  const { data: sets } = useSets();
  const { setCode } = useParams();
  const isMobile = useIsMobile();
  const craftSets = useMemo(() => cardSets(sets), [sets]);
  const current = setCode?.toUpperCase() ?? craftSets[0]?.code ?? ACTIVE_SET_CODE;
  const setMeta = craftSets.find((s) => s.code === current);
  const { data: lists, isPending, isError } = useCraftLists(current);

  return (
    <PageShell subtitle="TOOLS">
      <div className="w-full px-2 md:px-[15px] pt-2 md:pt-3 pb-10 [--craft-chrome:340px]">
        <div
          className={cn(
            "flex flex-col gap-2.5",
            "lg:grid lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-center lg:gap-x-6",
          )}
        >
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 min-w-0">
            <div className="flex flex-col min-w-0 shrink-0">
              <div className="font-display tracking-[0.12em] flex items-center leading-none min-w-0">
                <SetGlyphDropdown
                  sets={craftSets}
                  activeCode={current}
                  glyphCode={current}
                  label={setMeta?.name?.toUpperCase() ?? current}
                  isMobile={isMobile}
                  loading={!sets}
                  hrefFor={(code) => `/tools/craft/${code}`}
                />
              </div>
              <h1 className="mt-1 pl-[2px] font-mono text-[11px] tracking-[0.16em] text-muted">
                BULK CRAFTING DECK LISTS
              </h1>
            </div>
            {lists && lists.length > 0 && (
              <div
                className={cn(
                  "md:hidden ml-auto basis-1/3 shrink-0 grid grid-cols-2 justify-items-center gap-y-1.5",
                  "rounded-xl border border-border bg-surface py-2",
                )}
              >
                <RarityTotals lists={lists} />
              </div>
            )}
          </div>
          <ol className="flex w-full rounded-xl border border-border bg-surface md:w-fit lg:justify-self-center">
            {steps.map((step, index) => (
              <li
                key={step.label}
                className={cn(
                  "flex flex-1 items-center justify-center gap-2 px-2.5 py-2.5 md:flex-none md:gap-2.5 md:px-5",
                  "border-border [&:not(:first-child)]:border-l",
                )}
              >
                <span className="font-display text-green text-[18px] md:text-[20px] leading-none">{index + 1}</span>
                <span
                  className={cn(
                    "font-display text-text tracking-[0.06em] leading-none uppercase",
                    "text-[15px] md:text-[17px]",
                  )}
                >
                  <span className="md:hidden">{step.shortLabel}</span>
                  <span className="hidden md:inline">{step.label}</span>
                </span>
                {step.icon}
              </li>
            ))}
          </ol>
          <div className="hidden min-[1250px]:flex flex-col items-end gap-1.5 text-right text-[13px] leading-tight">
            <span className="text-subtle">More wildcards than you know what to do with?</span>
            <span className="text-muted">Lists split to fit the 250-card deck limit</span>
            {lists && lists.length > 0 && (
              <div className="flex items-center gap-x-5 rounded-xl border border-border bg-surface px-3 py-[3px]">
                <RarityTotals lists={lists} />
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 md:mt-3">
          {!isCraftSetCode(current) ? (
            <CraftNotice text={`No set with the code ${current}`} />
          ) : isPending ? (
            <CraftListsSkeleton />
          ) : isError ? (
            <CraftNotice text="Scryfall is unavailable right now. Try again later" />
          ) : lists.length === 0 ? (
            <CraftNotice text={`Scryfall has no MTG Arena cards for ${current} yet`} />
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 items-start">
                {rarityColumns(lists).map((column) => (
                  <div key={column[0].rarity} className="flex flex-col gap-3 min-w-0">
                    {column.map((list) => (
                      <CraftListRow key={craftListLabel(list)} list={list} startExpanded={list === lists.at(-1)} />
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}

function CraftListRow({ list, startExpanded }: { list: CraftList; startExpanded: boolean }) {
  const label = craftListLabel(list);
  const text = craftListText(list);
  const isMobile = useIsMobile();
  const [expanded, setExpanded] = useState(startExpanded);
  const showText = !isMobile || expanded;
  const title = (
    <>
      <RaritySetGlyph code={list.setCode} rarity={list.rarity} size={26} />
      <span className="font-display tracking-[0.12em] text-[17px] leading-none truncate">
        {craftListTitle(list).toUpperCase()}
      </span>
    </>
  );
  return (
    <div className="flex flex-col border border-border bg-surface min-w-0">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 px-4 py-2.5">
        {isMobile ? (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            className="flex items-center gap-2 min-w-0 text-left cursor-pointer"
          >
            {title}
            <ChevronRight
              size={16}
              strokeWidth={2.5}
              className={cn("shrink-0 text-muted transition-transform", expanded && "rotate-90")}
            />
          </button>
        ) : (
          <div className="flex items-center gap-2 min-w-0">{title}</div>
        )}
        <span className="flex items-center gap-1 text-subtle text-[13px] leading-none">
          <WildcardIcon rarity={list.rarity} size={16} />
          {craftListWildcards(list)}
        </span>
        <CopyTextButton
          text={() => text}
          label="COPY"
          ariaLabel={`Copy ${label} to clipboard`}
          className="justify-self-end"
        />
      </div>
      {showText && (
        <div className="bg-bg border-t border-border px-4 py-2.5">
          <pre
            className={cn(
              "font-mono text-[12px] leading-[1.6] text-subtle whitespace-pre select-all overflow-auto",
              "[scrollbar-width:thin] max-h-[240px] xl:max-h-[max(8rem,calc((100vh-var(--craft-chrome))/2))]",
          )}
        >
          {text}
        </pre>
      </div>
      )}
    </div>
  );
}

function RarityTotals({ lists }: { lists: CraftList[] }) {
  return (
    <>
      {rarityColumns(lists).map((column) => {
        let wildcards = 0;
        for (const list of column) {
          wildcards += craftListWildcards(list);
        }
        return (
          <span key={column[0].rarity} className="flex items-center gap-1 tracking-normal text-subtle text-[13px]">
            <WildcardIcon rarity={column[0].rarity} size={16} />
            {wildcards}
          </span>
        );
      })}
    </>
  );
}

function rarityColumns(lists: CraftList[]): CraftList[][] {
  const columns = new Map<string, CraftList[]>();
  for (const list of lists) {
    const column = columns.get(list.rarity) ?? [];
    column.push(list);
    columns.set(list.rarity, column);
  }
  return [...columns.values()];
}

function CraftNotice({ text }: { text: string }) {
  return <p className="py-16 text-center text-muted text-[14px]">{text}</p>;
}

function CraftListsSkeleton() {
  const partsPerColumn = [2, 2, 1, 1];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 items-start" aria-label="Loading lists">
      {partsPerColumn.map((parts, column) => (
        <div key={column} className="flex flex-col gap-3 min-w-0">
          {Array.from({ length: parts }, (_, part) => (
            <CraftListRowSkeleton key={part} />
          ))}
        </div>
      ))}
    </div>
  );
}

function CraftListRowSkeleton() {
  const lineWidths = [
    "w-1/4", "w-1/2", "w-0", "w-1/4", "w-3/4", "w-2/3", "w-4/5", "w-1/2", "w-3/5", "w-2/3", "w-1/2", "w-3/4",
  ];
  return (
    <div className="flex flex-col border border-border bg-surface">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="h-[26px] w-[26px] shrink-0 rounded-full bg-surface2 animate-pulse" />
          <span className="h-3.5 w-24 bg-surface2 animate-pulse" />
        </div>
        <span className="h-3 w-12 bg-surface2 animate-pulse" />
        <span className="justify-self-end h-7 w-[72px] rounded-full bg-surface2 animate-pulse" />
      </div>
      <div className="bg-bg border-t border-border px-4 py-2.5">
        <div
          className={cn(
            "flex flex-col gap-[7.2px] overflow-hidden",
            "h-[240px] xl:h-[max(8rem,calc((100vh-var(--craft-chrome))/2))]",
          )}
        >
          {lineWidths.map((width, index) => (
            <span key={index} className={cn("h-3 shrink-0 bg-surface2 animate-pulse", width)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function cardSets(sets: SetSummary[] | undefined): SetSummary[] {
  const nonCardSets = new Set(["CHAOS"]);
  const released = (sets ?? []).filter((s) => !isCubeCode(s.code) && !nonCardSets.has(s.code));
  const releasedCodes = new Set(released.map((s) => s.code));
  const previewed: SetSummary[] = [];
  for (const [code, contest] of Object.entries(P0P1_CONTESTS)) {
    if (releasedCodes.has(code) || Date.parse(contest.previewsOpen) > Date.now()) {
      continue;
    }
    previewed.push({ code, name: contest.name, startDate: contest.release.slice(0, 10), endDate: "", isActive: false });
  }
  return [...previewed, ...released].sort((a, b) => b.startDate.localeCompare(a.startDate));
}
