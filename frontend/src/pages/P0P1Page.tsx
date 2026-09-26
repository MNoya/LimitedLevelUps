import { useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { Crossfade } from "../components/Crossfade";
import { CtaPill } from "../components/CtaPill";
import { DiscordIcon } from "../components/BrandIcons";
import { SectionLabel } from "../components/SectionLabel";
import { ManaCost } from "../components/ManaPips";
import { CardSelectionGrid } from "../components/p0p1/CardSelectionGrid";
import { SlotPip, SLOT_ACCENT } from "../components/p0p1/slotVisuals";
import { P0P1ProgressBar } from "../components/p0p1/ProgressBar";
import { ClearAll } from "../components/p0p1/ClearAll";
import { P0P1Hero } from "../components/p0p1/P0P1Hero";
import { NextContestOpens } from "../components/p0p1/NextContestOpens";
import { AutoSaveBadge } from "../components/p0p1/AutoSaveBadge";
import { P0P1MobileSelector } from "../components/p0p1/P0P1MobileView";
import { GoToTopButton } from "../components/GoToTopButton";
import { PostVotingStats } from "../components/p0p1/PostVotingStats";
import { MidwayResults } from "../components/p0p1/MidwayResults";
import { FinalResults } from "../components/p0p1/FinalResults";
import { P0P1DevPanel } from "../components/p0p1/P0P1DevPanel";
import { p0p1DevEnabled, p0p1Now } from "../data/p0p1DevState";
import { isP0P1Previewer } from "../data/p0p1Previewers";
import { useAuth } from "../auth/useAuth";
import { yourBallotScorecard, BallotScorecardSkeleton, ScorecardFrame } from "../components/p0p1/P0P1BallotScorecard";
import { YourPicks } from "../components/p0p1/YourPicks";
import { ExpandToggle } from "../components/p0p1/ExpandToggle";
import { useIsMobile } from "../lib/use-is-mobile";
import { useP0P1Ballot } from "../data/useP0P1Ballot";
import { slotsForSet, isWideBallot, resolveAllContestChips, resolveFeaturedContest } from "../data/p0p1Slots";
import type { Card, SlotDefinition, SlotKey } from "../types/p0p1";
import { SITE_LINKS } from "../data/site";
import { NotFoundPage } from "./NotFoundPage";

export function P0P1Page() {
  const { setCode: routeSetCode } = useParams<{ setCode?: string }>();
  const ballot = useP0P1Ballot(routeSetCode);
  const {
    featured,
    cards,
    cardsByName,
    dataReady,
    resultsDataReady,
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
    ballotPending,
    handleClearAll,
    clearPending,
    setEditingSlotKey,
    activeSlotKey,
    activeSlot,
    selectAdvance,
    phase,
    ratingsSnapshot,
    ballots,
    contestSlots,
  } = ballot;

  const { user: authUser } = useAuth();
  const canPreviewPre = p0p1DevEnabled || isP0P1Previewer(authUser?.discordId);

  const currentContest = resolveFeaturedContest(p0p1Now(featured?.scoringDate));
  const isCurrentContest = !currentContest || !featured || currentContest.code === featured.code;
  const allContests = resolveAllContestChips(p0p1Now(featured?.scoringDate));
  const visibleContests = canPreviewPre
    ? allContests
    : allContests.filter((c) => c.status !== "pre");
  const contestHref = (code: string) =>
    currentContest && code === currentContest.code ? "/p0p1" : `/p0p1/${code.toLowerCase()}`;

  const isDesktop = !useIsMobile(1024);
  const heroRef = useRef<HTMLDivElement>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const [heroHeight, setHeroHeight] = useState(0);
  const [gridsExpanded, setGridsExpanded] = useState(false);
  const [rosterStuck, setRosterStuck] = useState(false);
  useEffect(() => {
    const el = heroRef.current;
    if (!el) return;
    const measure = () => setHeroHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setRosterStuck(entry.intersectionRatio < 1),
      { threshold: [1], rootMargin: `-${Math.round(heroHeight) + 1}px 0px 0px 0px` },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [heroHeight]);

  useEffect(() => {
    if (!cards) return;
    const preloaded = cards.map((c) => {
      const img = new Image();
      img.src = c.imageArtCrop;
      return img;
    });
    return () => preloaded.forEach((img) => { img.src = ""; });
  }, [cards]);

  if (!featured) return <NotFoundPage />;
  if (featured.status === "pre" && !featured.comingSoon && !canPreviewPre) {
    return authLoading ? <div className="bg-bg min-h-screen" /> : <NotFoundPage />;
  }

  const isCompleteEntrant = isPastDeadline && Boolean(user) && isComplete;
  const didNotVote = isPastDeadline && Boolean(user) && !isComplete;

  if (!isDesktop) {
    return (
      <>
        <P0P1MobileSelector
          ballot={ballot}
          contests={visibleContests}
          contestHref={contestHref}
          isCurrent={isCurrentContest}
        />
        <P0P1DevPanel />
      </>
    );
  }

  if (phase === "comingSoon") {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
        <AppHeader subtitle="P0 P1 Challenge" subtitleShort="P0 P1" />
        <P0P1Hero
          featured={featured}
          contests={visibleContests}
          contestHref={contestHref}
          innerRef={heroRef}
          cta={null}
          belowIntro={
            <NextContestOpens
              next={{ code: featured.code, name: featured.name, previewsOpen: featured.previewsOpen }}
              showSet={false}
            />
          }
          phase={phase}
          isCurrent={isCurrentContest}
        />
        <main className="flex-1 flex items-center justify-center px-10 py-24">
          <span className="font-display tracking-[0.12em] text-muted" style={{ fontSize: 48 }}>COMING SOON</span>
        </main>
      </div>
    );
  }

  const loginCta = !authLoading && !user && (
    <button type="button" onClick={signIn} className="bg-transparent border-0 cursor-pointer p-0">
      <CtaPill size="lg" icon={<DiscordIcon size={19} />}>
        {!isPastDeadline ? <>LOG IN TO SUBMIT PICKS</> : <>LOG IN TO VIEW YOUR PICKS</>}
      </CtaPill>
    </button>
  );

  const showMidway = phase === "midway";
  const ballotScorecard = yourBallotScorecard(ballot);
  const didNotVoteCard = didNotVote ? <DidNotVoteCard /> : null;
  const heroCta = ballotPending ? (
    <BallotScorecardSkeleton setCode={featured?.code ?? ""} />
  ) : (
    loginCta ||
    (user && !isPastDeadline ? <AutoSaveBadge complete={isComplete} /> : null) ||
    ballotScorecard ||
    didNotVoteCard
  );

  const collapsible = isWideBallot(contestSlots.length);
  const compactGrids = collapsible && !gridsExpanded;
  const gridsToggle = (topClass: string) => (
    <ExpandToggle
      expanded={gridsExpanded}
      onToggle={() => setGridsExpanded((v) => !v)}
      className={`absolute left-1/2 ${topClass} -translate-x-1/2 z-10`}
    />
  );
  let belowIntro: ReactNode = null;
  if (!isPastDeadline) {
    belowIntro = (
      <div className="relative flex items-center gap-3 w-full max-w-[420px]">
        <SectionLabel size={13}>PICKS</SectionLabel>
        <div className="flex-1">
          <P0P1ProgressBar filled={scoringFilled} total={contestSlots.length} isComplete={isComplete} />
        </div>
        {collapsible && gridsToggle("top-full")}
      </div>
    );
  } else if (phase === "postVoting" && collapsible) {
    belowIntro = <div className="relative w-full">{gridsToggle("top-2")}</div>;
  }

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="P0 P1 Challenge" subtitleShort="P0 P1" />
      {featured && (
        <P0P1Hero
          featured={featured}
          contests={visibleContests}
          contestHref={contestHref}
          innerRef={heroRef}
          cta={heroCta}
          belowIntro={belowIntro}
          phase={phase}
          dateRange={ratingsSnapshot?.dateRange}
          isCurrent={isCurrentContest}
        />
      )}

      <main className="flex-1 px-5 pt-5">
        {!isPastDeadline &&
          (dataReady ? (
            <div
              ref={stripRef}
              className={`-mx-5 px-5 mb-3 bg-bg/95 border-b border-border ${
                gridsExpanded ? "relative pb-5" : `sticky z-20 ${rosterStuck ? "pb-2" : "pb-5"} backdrop-blur`
              }`}
              style={gridsExpanded ? undefined : { top: heroHeight }}
            >
              <RosterStrip
                expanded={gridsExpanded}
                activeSlotKey={activeSlotKey}
                picksBySlot={picksBySlot}
                cardsByName={cardsByName}
                setCode={featured?.code}
                onSelect={(key) => setEditingSlotKey(key)}
              />
            </div>
          ) : (
            <RosterStripSkeleton setCode={featured?.code} />
          ))}

        {phase === "loading" ? (
          <ResultsSkeleton setCode={featured?.code} />
        ) : showMidway ? (
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
          ) : (
            <ResultsSkeleton setCode={featured?.code} />
          )
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
              stickyTop={heroHeight}
            />
          ) : (
            <ResultsSkeleton setCode={featured?.code} />
          )
        ) : phase === "postVoting" ? (
          pickStats && pickStats.length > 0 && (
            <PostVotingStats
              pickStats={pickStats}
              cardsByName={cardsByName}
              picksBySlot={picksBySlot}
              setCode={featured?.code}
              compact={compactGrids}
              yourPicks={
                isCompleteEntrant ? (
                  <YourPicks
                    contestSlots={contestSlots}
                    pickStats={pickStats}
                    cardsByName={cardsByName}
                    picksBySlot={picksBySlot}
                    setCode={featured?.code}
                    compact={compactGrids}
                  />
                ) : null
              }
            />
          )
        ) : (
          <div className="mt-4">
            {dataReady && cards ? (
              <Crossfade transitionKey={activeSlot.key}>
                <CardSelectionGrid
                  key={activeSlot.key}
                  animateMount={false}
                  slot={activeSlot}
                  cards={cards}
                  pickedCards={pickedExcept(activeSlot.key)}
                  takenBy={pickedSlotLabels}
                  selectedName={picksBySlot.get(activeSlot.key)}
                  onSelect={(name) => selectAdvance(activeSlot.key, name)}
                  minColW={200}
                  setCode={featured?.code}
                  footerRight={
                    <ClearAll
                      onClear={handleClearAll}
                      clearing={clearPending}
                      visible={scoringFilled > 0}
                      className="shrink-0"
                    />
                  }
                />
              </Crossfade>
            ) : (
              <CardGridSkeleton />
            )}
          </div>
        )}
      </main>

      <GoToTopButton onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} />
      <P0P1DevPanel />
    </div>
  );
}

function DidNotVoteCard() {
  return (
    <ScorecardFrame compact={false} animate>
      <span className="font-display text-text leading-none tracking-[0.04em]" style={{ fontSize: 22 }}>
        YOU DIDN'T VOTE ON THIS ONE
      </span>
      <p className="font-body text-subtle text-[12px] leading-snug">
        <a
          href={SITE_LINKS.discord}
          target="_blank"
          rel="noreferrer"
          className="text-green hover:text-green-2 underline underline-offset-2"
        >
          Check the Dischord
        </a>{" "}
        to catch the next challenge
      </p>
    </ScorecardFrame>
  );
}

function RosterStrip({
  activeSlotKey,
  picksBySlot,
  cardsByName,
  setCode,
  expanded,
  onSelect,
}: {
  activeSlotKey: SlotKey;
  picksBySlot: Map<string, string>;
  cardsByName: Map<string, Card>;
  setCode?: string;
  expanded: boolean;
  onSelect: (key: SlotKey) => void;
}) {
  const slots = slotsForSet(setCode ?? "");
  const wide = isWideBallot(slots.length);
  const compact = wide && !expanded;
  const cols = !wide ? "grid-cols-8" : expanded ? "grid-cols-6" : "grid-cols-12";
  return (
    <div className={`grid ${cols} gap-2`}>
      {slots.map((slot) => {
        const cardName = picksBySlot.get(slot.key);
        return (
          <RosterTile
            key={slot.key}
            slot={slot}
            card={cardName ? cardsByName.get(cardName) : undefined}
            active={activeSlotKey === slot.key}
            setCode={setCode}
            compact={compact}
            onClick={() => onSelect(slot.key)}
          />
        );
      })}
    </div>
  );
}

function RosterTile({
  slot,
  card,
  active,
  setCode,
  compact = false,
  onClick,
}: {
  slot: SlotDefinition;
  card: Card | undefined;
  active: boolean;
  setCode?: string;
  compact?: boolean;
  onClick: () => void;
}) {
  const accent = SLOT_ACCENT[slot.key];
  const tileLabel = slot.label.toUpperCase();
  const pipCount = card ? (card.manaCost.match(/\{/g) ?? []).length : 0;
  const manaSize = pipCount >= 5 ? 8 : pipCount === 4 ? 9 : pipCount === 3 ? 10 : 11;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex flex-col aspect-square border border-t-0 overflow-hidden text-left min-w-0 transition-all duration-150 cursor-pointer hover:z-10 hover:scale-[1.04] ${
        active ? "border-green/60 bg-green/5 z-10 scale-[1.04]" : "border-border2 bg-surface hover:border-border"
      }`}
    >
      <div
        className={`w-full shrink-0 transition-[height] duration-150 ${active ? "h-2" : "h-[4px] group-hover:h-2"}`}
        style={{ background: accent }}
      />
      <div className="relative flex-1 min-h-0 bg-surface2 flex items-center justify-center overflow-hidden">
        {card ? (
          <img src={card.imageArtCrop} alt={card.name} className="w-full h-full object-cover" />
        ) : (
          <>
            <SlotPip slotKey={slot.key} size={compact ? 34 : 48} setCode={setCode} />
            {compact && (
              <span className="absolute inset-x-0 bottom-1.5 px-1 text-muted text-[14px] tracking-[0.08em] font-display text-center leading-tight">
                {tileLabel}
              </span>
            )}
          </>
        )}
      </div>
      {!compact && (
        <div className="px-2 pt-2 pb-1.5 shrink-0">
          <div className="text-subtle text-[13px] tracking-[0.1em] font-display truncate min-w-0 mb-1">
            {tileLabel}
          </div>
          {card ? (
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-text text-[14px] truncate min-w-0">{card.name}</span>
              <span className="ml-auto shrink-0">
                <ManaCost cost={card.manaCost} size={manaSize} />
              </span>
            </div>
          ) : (
            <span className="italic text-dim text-[13px]">Select a card</span>
          )}
        </div>
      )}
    </button>
  );
}

function SkeletonTile() {
  return (
    <div className="flex flex-col aspect-square border-t-0 bg-surface border border-border2">
      <div className="h-1 w-full bg-surface2" />
      <div className="flex-1 min-h-0 bg-surface2 animate-pulse" />
      <div className="px-2.5 py-1.5 shrink-0 flex flex-col gap-1">
        <div className="h-2 w-12 bg-surface2 animate-pulse" />
        <div className="h-2.5 w-16 bg-surface2 animate-pulse" />
      </div>
    </div>
  );
}

function RosterStripSkeleton({ setCode = "" }: { setCode?: string }) {
  const slots = slotsForSet(setCode);
  return (
    <div className={`grid ${isWideBallot(slots.length) ? "grid-cols-6" : "grid-cols-8"} gap-2`}>
      {Array.from({ length: slots.length }, (_, i) => (
        <SkeletonTile key={i} />
      ))}
    </div>
  );
}

function ResultsSkeleton({ setCode = "" }: { setCode?: string }) {
  const slots = slotsForSet(setCode);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col items-center gap-2">
        <div className="h-5 w-52 bg-surface2 animate-pulse" />
        <div className="h-3 w-72 bg-surface2 animate-pulse" />
      </div>
      <div className={`grid ${isWideBallot(slots.length) ? "grid-cols-6" : "grid-cols-8"} gap-2`}>
        {Array.from({ length: slots.length }, (_, i) => (
          <SkeletonTile key={i} />
        ))}
      </div>
    </div>
  );
}

function CardGridSkeleton() {
  return (
    <div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 mb-3">
        <div />
        <div className="h-6 w-56 bg-surface2 animate-pulse" />
        <div className="ml-auto h-7 w-60 bg-surface2 animate-pulse" />
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3.5">
        {Array.from({ length: 10 }, (_, i) => (
          <div key={i} className="bg-surface2 animate-pulse rounded-[3%]" style={{ aspectRatio: "488 / 680" }} />
        ))}
      </div>
    </div>
  );
}
