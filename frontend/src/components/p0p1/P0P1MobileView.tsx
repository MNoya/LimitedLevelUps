import { useEffect, useState } from "react";
import { AppHeader } from "../AppHeader";
import { CtaPill } from "../CtaPill";
import { DiscordIcon } from "../BrandIcons";
import { SetGlyph, setGlyphCode } from "../Brand";
import { SectionLabel } from "../SectionLabel";
import { SlotCard } from "./SlotCard";
import { CardSelectionGrid } from "./CardSelectionGrid";
import { PostVotingStats } from "./PostVotingStats";
import { PickGrid } from "./CommunityGrid";
import { P0P1IntroText } from "./P0P1IntroText";
import { SlotPip, SLOT_ACCENT } from "./slotVisuals";
import { P0P1ProgressBar } from "./ProgressBar";
import { P0P1CountdownBar } from "./CountdownBar";
import { formatRemaining, formatScoringRemaining, useTick } from "./Countdown";
import { ClearAll } from "./ClearAll";
import { GoToTopButton } from "../GoToTopButton";
import { SiteFooter } from "../SiteFooter";
import { ChevronDown } from "../Icons";
import { MidwayResults } from "./MidwayResults";
import { FinalResults } from "./FinalResults";
import type { useP0P1Ballot } from "../../data/useP0P1Ballot";
import type { P0P1Phase } from "../../data/p0p1Results";
import type { FeaturedContest } from "../../data/p0p1Slots";
import { SLOTS } from "../../data/p0p1Slots";
import { groupBySlot, findExtremes, classifyYourPick, pickPctLabel } from "../../data/p0p1Stats";
import { SITE_LINKS } from "../../data/site";
import { p0p1Now } from "../../data/p0p1DevState";
import type { Card, P0P1PickStat, SlotDefinition, SlotKey } from "../../types/p0p1";
import type { SetSummary } from "../../types/leaderboard";

type Ballot = ReturnType<typeof useP0P1Ballot>;

export function P0P1MobileView({ ballot }: { ballot: Ballot }) {
  const {
    featured,
    cards,
    cardsByName,
    dataReady,
    user,
    authLoading,
    signIn,
    picksBySlot,
    pickedExcept,
    pickedSlotLabels,
    scoringFilled,
    isComplete,
    isPastDeadline,
    handleClearAll,
    clearPending,
    editingSlotKey,
    setEditingSlotKey,
    selectAndClose,
    phase,
    ratingsSnapshot,
    p0p1Sets,
  } = ballot;

  const slotCard = (slotKey: SlotKey) => {
    const slot = SLOTS.find((s) => s.key === slotKey)!;
    const cardName = picksBySlot.get(slotKey);
    return (
      <SlotCard
        key={slotKey}
        slot={slot}
        selectedCard={cardName ? cardsByName.get(cardName) : undefined}
        locked={isPastDeadline}
        active={false}
        onEdit={() => setEditingSlotKey(slotKey)}
        setCode={featured?.code}
      />
    );
  };

  const loginBarVisible = !authLoading && !user && !isPastDeadline;

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col animate-fadeIn">
      <AppHeader subtitle="P0 P1 Challenge" subtitleShort="P0 P1" />

      <main className={`flex-1 flex flex-col w-full px-4 pt-4 ${loginBarVisible ? "pb-20" : "pb-4"}`}>
        <MobileIntro featured={featured} sets={p0p1Sets} phase={phase} dateRange={ratingsSnapshot?.dateRange} />
        {dataReady ? (
          <>
            {!isPastDeadline && (
              <div className="mb-3">
                <P0P1ProgressBar filled={scoringFilled} total={SLOTS.length} isComplete={isComplete} />
              </div>
            )}
            <div className="flex-1 min-h-0 flex flex-col gap-1.5">
              {SLOTS.map((s) => (
                <div key={s.key} className="flex-1 min-h-[56px]">
                  {slotCard(s.key)}
                </div>
              ))}
            </div>
            {!isPastDeadline && (
              <ClearAll onClear={handleClearAll} clearing={clearPending} visible={scoringFilled > 0} />
            )}
          </>
        ) : (
          <>
            <div className="h-3 w-40 bg-surface2 animate-pulse mb-3" />
            <SlotsListSkeleton />
          </>
        )}
      </main>

      <MobileLoginBar show={loginBarVisible} text={!isPastDeadline ? "LOG IN TO SUBMIT PICKS" : "LOG IN TO VIEW YOUR PICKS"} signIn={signIn} />

      {!isPastDeadline && editingSlotKey && cards && (
        <MobilePickerSheet
          slotKey={editingSlotKey}
          cards={cards}
          pickedCards={pickedExcept(editingSlotKey)}
          takenBy={pickedSlotLabels}
          selectedName={picksBySlot.get(editingSlotKey)}
          onSelect={(name) => selectAndClose(editingSlotKey, name)}
          onClose={() => setEditingSlotKey(null)}
          setCode={featured?.code}
        />
      )}
    </div>
  );
}

export function P0P1MobileSelector({ ballot }: { ballot: Ballot }) {
  const {
    featured,
    cards,
    cardsByName,
    dataReady,
    resultsDataReady,
    midwayDataReady,
    user,
    authLoading,
    signIn,
    picksBySlot,
    pickedExcept,
    pickedSlotLabels,
    scoringFilled,
    isComplete,
    isPastDeadline,
    hasParticipated,
    pickStats,
    handleClearAll,
    clearPending,
    activeSlotKey,
    activeSlot,
    setEditingSlotKey,
    selectAdvance,
    phase,
    ratingsSnapshot,
    ballots,
    p0p1Sets,
  } = ballot;

  const loginBarVisible = !authLoading && !user;
  const groupedStats = hasParticipated && pickStats ? groupBySlot(pickStats) : undefined;
  const isCompleteEntrant = isPastDeadline && Boolean(user) && isComplete;
  const didNotVote = isPastDeadline && Boolean(user) && !isComplete;
  const showMidway = phase === "midway" || (phase === "finalizing" && midwayDataReady);

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col animate-fadeIn">
      <AppHeader subtitle="P0 P1 Challenge" subtitleShort="P0 P1" />

      <main className={`flex-1 flex flex-col w-full px-3 pt-3 ${loginBarVisible ? "pb-24" : "pb-4"}`}>
        <MobileIntro featured={featured} sets={p0p1Sets} phase={phase} dateRange={ratingsSnapshot?.dateRange} />
        {dataReady ? (
          <>
            {!isPastDeadline && (
              <div className="mb-1.5">
                <P0P1ProgressBar
                  filled={scoringFilled}
                  total={SLOTS.length}
                  isComplete={isComplete}
                  doneLabel="PICKS SAVED"
                  doneHint="Edit anytime before deadline"
                />
              </div>
            )}
            {!isPastDeadline && (
              <div className="sticky top-0 z-20 -mx-3 px-2 pt-3 pb-2 bg-bg/95 backdrop-blur border-b border-border">
                <div className="grid grid-cols-4 landscape:grid-cols-8 gap-1.5">
                  {SLOTS.map((slot) => {
                    const cardName = picksBySlot.get(slot.key);
                    const slotStats = groupedStats?.get(slot.key);
                    const yourStat = cardName && slotStats ? slotStats.find((s) => s.cardName === cardName) : undefined;
                    return (
                      <MobileChip
                        key={slot.key}
                        slot={slot}
                        card={cardName ? cardsByName.get(cardName) : undefined}
                        active={activeSlotKey === slot.key}
                        yourStat={yourStat}
                        slotStats={slotStats}
                        onClick={() => setEditingSlotKey(slot.key)}
                        setCode={featured?.code}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {showMidway ? (
              resultsDataReady && ratingsSnapshot && cards && pickStats ? (
                <MidwayResults
                  ratingsSnapshot={ratingsSnapshot}
                  pickStats={pickStats}
                  cards={cards}
                  cardsByName={cardsByName}
                  picksBySlot={picksBySlot}
                  user={user}
                  hasParticipated={hasParticipated}
                />
              ) : null
            ) : phase === "final" ? (
              resultsDataReady && ratingsSnapshot && cards && pickStats && ballots ? (
                <FinalResults
                  ratingsSnapshot={ratingsSnapshot}
                  pickStats={pickStats}
                  ballots={ballots}
                  cards={cards}
                  cardsByName={cardsByName}
                  picksBySlot={picksBySlot}
                  user={user}
                  hasParticipated={hasParticipated}
                />
              ) : null
            ) : phase === "postVoting" || phase === "finalizing" ? (
              pickStats && pickStats.length > 0 && (
                <>
                  {didNotVote && <MobileDidNotVoteLine />}
                  <PostVotingStats
                    pickStats={pickStats}
                    cardsByName={cardsByName}
                    picksBySlot={picksBySlot}
                    setCode={featured?.code}
                    yourPicks={
                      isCompleteEntrant ? (
                        <div>
                          <div className="flex items-baseline justify-center gap-2 mb-1.5">
                            <SectionLabel size={22} className="text-white">YOUR PICKS</SectionLabel>
                          </div>
                          <PickGrid
                            entries={SLOTS.map((slot) => {
                              const cardName = picksBySlot.get(slot.key);
                              const slotStats = groupedStats?.get(slot.key) ?? [];
                              const yourStat = cardName ? slotStats.find((s) => s.cardName === cardName) : undefined;
                              const extremes = findExtremes(slotStats);
                              const cls = yourStat ? classifyYourPick(yourStat, extremes.most, extremes.least) : undefined;
                              return {
                                slotKey: slot.key,
                                label: slot.label,
                                stats: yourStat ? [yourStat] : [],
                                slotStats,
                                badge: cls?.state === "rogue" ? cls.qualifier : undefined,
                              };
                            })}
                            cardsByName={cardsByName}
                            picksBySlot={picksBySlot}
                            setCode={featured?.code}
                          />
                        </div>
                      ) : null
                    }
                  />
                </>
              )
            ) : (
              cards && (
                <div className="pt-2">
                  <CardSelectionGrid
                    key={activeSlot.key}
                    slot={activeSlot}
                    cards={cards}
                    pickedCards={pickedExcept(activeSlot.key)}
                    takenBy={pickedSlotLabels}
                    selectedName={picksBySlot.get(activeSlot.key)}
                    onSelect={(name) => selectAdvance(activeSlot.key, name)}
                    minColW={150}
                    showLabel={false}
                    autoFocusSearch={false}
                    leftLabel={
                      <>
                        <SlotPip slotKey={activeSlot.key} size={20} setCode={featured?.code} />
                        <span className="font-display text-[18px] tracking-[0.06em] truncate">{activeSlot.label}</span>
                      </>
                    }
                    footerRight={
                      <ClearAll
                        onClear={handleClearAll}
                        clearing={clearPending}
                        visible={scoringFilled > 0}
                        className="shrink-0"
                      />
                    }
                  />
                </div>
              )
            )}
          </>
        ) : (
          <>
            <div className="h-2 w-full bg-surface2 animate-pulse mb-3 rounded-full" />
            <div className="grid grid-cols-4 landscape:grid-cols-8 gap-1.5">
              {Array.from({ length: SLOTS.length }, (_, i) => (
                <div key={i} className="aspect-[5/4] landscape:aspect-auto landscape:h-14 bg-surface2 animate-pulse border border-border2" />
              ))}
            </div>
          </>
        )}
      </main>

      <SiteFooter flush />

      <MobileLoginBar show={loginBarVisible} signIn={signIn} text={!isPastDeadline ? "LOG IN TO SUBMIT PICKS" : "LOG IN TO VIEW YOUR PICKS"} />

      <GoToTopButton
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        compact
        bottomClass={loginBarVisible ? "bottom-20" : "bottom-4"}
      />
    </div>
  );
}

function MobileChip({
  slot,
  card,
  active,
  yourStat,
  slotStats,
  onClick,
  setCode,
}: {
  slot: SlotDefinition;
  card: Card | undefined;
  active: boolean;
  yourStat?: P0P1PickStat;
  slotStats?: P0P1PickStat[];
  onClick: () => void;
  setCode?: string;
}) {
  const accent = SLOT_ACCENT[slot.key];
  let classification: ReturnType<typeof classifyYourPick> | undefined;
  if (yourStat && slotStats) {
    const { most, least } = findExtremes(slotStats);
    classification = classifyYourPick(yourStat, most, least);
  }
  const stateColor = classification?.state === "most"
    ? "text-cyan"
    : classification?.state === "rogue"
    ? "text-magenta"
    : "text-white";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={slot.label}
      className={`relative w-full aspect-[5/4] landscape:aspect-auto landscape:h-14 bg-surface2 overflow-hidden border border-t-0 transition-colors ${
        active ? "border-green" : "border-border2"
      }`}
    >
      <div
        className={`absolute top-0 left-0 right-0 z-10 transition-[height] duration-150 ${active ? "h-2" : "h-1"}`}
        style={{ background: accent }}
      />
      {card ? (
        <img src={card.imageArtCrop} alt="" className="w-full h-full object-cover" />
      ) : (
        <span className="absolute inset-0 flex items-center justify-center">
          <SlotPip slotKey={slot.key} size={20} setCode={setCode} />
        </span>
      )}
      {yourStat && classification && (
        <div className={`absolute bottom-0 left-0 right-0 text-center font-mono tabular-nums text-[10px] py-0.5 bg-bg/75 ${stateColor}`}>
          {pickPctLabel(yourStat.pickPct)}
        </div>
      )}
    </button>
  );
}

function MobileDidNotVoteLine() {
  return (
    <a
      href={SITE_LINKS.discord}
      target="_blank"
      rel="noreferrer"
      className="h-7 mb-3 rounded-full bg-surface2 border border-border flex items-center justify-between gap-2 px-5 no-underline animate-fadeIn"
    >
      <span className="font-display text-subtle text-[13px] tracking-[0.08em] leading-none whitespace-nowrap">
        YOU DIDN'T VOTE ON THIS ONE
      </span>
      <span className="flex items-center gap-1.5 text-green leading-none whitespace-nowrap">
        <DiscordIcon size={14} />
        <span className="font-body text-[12px]">Catch the next</span>
      </span>
    </a>
  );
}

function MobileLoginBar({ show, signIn, text }: { show: boolean; signIn: () => void; text: string }) {
  if (!show) {
    return null;
  }
  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-bg/95 backdrop-blur border-t border-border px-4 py-2.5 flex justify-center">
      <button type="button" onClick={signIn} className="bg-transparent border-0 cursor-pointer p-0">
        <CtaPill size="lg" icon={<DiscordIcon size={19} />}>
          {text}
        </CtaPill>
      </button>
    </div>
  );
}

function MobileIntro({
  featured,
  sets,
  phase,
  dateRange,
}: {
  featured: FeaturedContest | undefined;
  sets: SetSummary[] | undefined;
  phase: P0P1Phase;
  dateRange?: { start: string; end: string } | null;
}) {
  const [open, setOpen] = useState(true);
  const isPastDeadline = phase !== "voting";
  const setCode = featured?.code ?? "";
  const votingDeadline = featured?.votingDeadline ?? new Date();
  const scoringDate = featured?.scoringDate ?? new Date();

  return (
    <section className="bg-surface border border-border rounded-xl p-4 mb-3 flex flex-col gap-2.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? "Hide details" : "Show details"}
        className="flex w-full items-center gap-3 text-left bg-transparent border-0 p-0 cursor-pointer"
      >
        <div className="flex items-center gap-1 shrink-0">
          <SetGlyph code={setGlyphCode(sets?.find((s) => s.code === setCode) ?? { code: setCode })} size={34} />
          <span className="font-display text-text tracking-[0.04em]" style={{ fontSize: 22, lineHeight: 1 }}>
            {setCode}
          </span>
        </div>
        <span className="flex-1 min-w-0 text-center font-display text-[16px] text-text tracking-[0.1em] truncate pointer-events-none">
          PACK 0, PICK 1
        </span>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex items-center gap-2">
            <CountdownStacked deadline={votingDeadline} scoringDate={scoringDate} phase={phase} />
            <ChevronDown size={22} className={`shrink-0 text-muted transition-transform ${open ? "" : "-rotate-90"}`} />
          </div>
          {isPastDeadline && (
            <div className="w-full">
              <P0P1CountdownBar from={votingDeadline} to={scoringDate} />
            </div>
          )}
        </div>
      </button>
      {open && (
        <p className="text-subtle text-[13.5px] leading-[1.5]">
          <P0P1IntroText phase={phase} dateRange={dateRange} setName={featured?.name ?? ""} votingDeadline={votingDeadline} scoringDate={scoringDate} />
        </p>
      )}
    </section>
  );
}

function MobilePickerSheet({
  slotKey,
  cards,
  pickedCards,
  takenBy,
  selectedName,
  onSelect,
  onClose,
  setCode,
}: {
  slotKey: SlotKey;
  cards: Card[];
  pickedCards: Set<string>;
  takenBy: Map<string, string>;
  selectedName: string | undefined;
  onSelect: (name: string) => void;
  onClose: () => void;
  setCode?: string;
}) {
  const slot = SLOTS.find((s) => s.key === slotKey)!;
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-bg flex flex-col animate-fadeIn">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border shrink-0">
        <SlotPip slotKey={slotKey} size={15} setCode={setCode} />
        <span className="font-display text-[18px] tracking-[0.06em]">{slot.label}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-auto text-muted hover:text-text text-[22px] leading-none bg-transparent border-0 cursor-pointer p-1"
        >
          ×
        </button>
      </div>
      <div className="flex-1 overflow-y-auto themed-scrollbar px-4 py-3">
        <CardSelectionGrid
          slot={slot}
          cards={cards}
          pickedCards={pickedCards}
          takenBy={takenBy}
          selectedName={selectedName}
          onSelect={onSelect}
          minColW={200}
          showLabel={false}
        />
      </div>
    </div>
  );
}

const SKEL_LABEL_W = [90, 75, 85, 65, 80, 120, 100, 110, 130];
const SKEL_NAME_W = [120, 100, 110, 95, 105, 130, 115, 125, 140];

export function SlotsListSkeleton() {
  return (
    <div className="flex flex-col gap-1.5">
      {Array.from({ length: SLOTS.length }, (_, i) => (
        <div key={i} className="w-full flex items-center gap-4 px-4 py-3 bg-surface border border-border2">
          <div className="w-20 h-12 bg-surface2 animate-pulse shrink-0" />
          <div className="flex-1 flex flex-col gap-1.5">
            <div className="h-2 bg-surface2 animate-pulse" style={{ width: SKEL_LABEL_W[i % SKEL_LABEL_W.length] }} />
            <div className="h-3 bg-surface2 animate-pulse" style={{ width: SKEL_NAME_W[i % SKEL_NAME_W.length] }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function CountdownStacked({
  deadline,
  scoringDate,
  phase,
}: {
  deadline: Date;
  scoringDate?: Date;
  phase: P0P1Phase;
}) {
  useTick(30_000);
  const now = p0p1Now(scoringDate);
  const deadlineDiff = deadline.getTime() - now;

  if (phase === "voting") {
    return (
      <div className="flex flex-col items-end leading-tight whitespace-nowrap shrink-0">
        <span className="text-muted text-[11px] tracking-[0.04em]">Closes in</span>
        <span className="text-green text-[13px]">{formatRemaining(deadlineDiff)}</span>
      </div>
    );
  }

  if (phase === "final") {
    return (
      <div className="flex flex-col items-end leading-tight whitespace-nowrap shrink-0">
        <span className="text-green text-[13px]">Results are in!</span>
      </div>
    );
  }

  if (phase === "finalizing") {
    return (
      <div className="flex flex-col items-end leading-tight whitespace-nowrap shrink-0">
        <span className="text-green text-[13px]">Finalizing results</span>
      </div>
    );
  }

  if (scoringDate) {
    const scoringDiff = scoringDate.getTime() - now;
    if (scoringDiff > 0) {
      return (
        <div className="flex flex-col items-end leading-tight whitespace-nowrap shrink-0">
          <span className="text-muted text-[11px] tracking-[0.04em]">Results in</span>
          <span className="text-green text-[13px]">{formatScoringRemaining(scoringDiff)}</span>
        </div>
      );
    }
  }

  return (
    <div className="flex flex-col items-end leading-tight whitespace-nowrap shrink-0">
      <span className="text-muted text-[11px] tracking-[0.04em]">Entries</span>
      <span className="text-muted text-[13px]">have closed</span>
    </div>
  );
}
