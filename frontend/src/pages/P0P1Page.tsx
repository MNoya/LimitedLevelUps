import { useEffect, useRef, useState } from "react";
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
import { AutoSaveBadge } from "../components/p0p1/AutoSaveBadge";
import { P0P1MobileSelector } from "../components/p0p1/P0P1MobileView";
import { GoToTopButton } from "../components/GoToTopButton";
import { PostVotingStats } from "../components/p0p1/PostVotingStats";
import { MidwayResults } from "../components/p0p1/MidwayResults";
import { FinalResults } from "../components/p0p1/FinalResults";
import { P0P1DevPanel } from "../components/p0p1/P0P1DevPanel";
import { p0p1DevEnabled } from "../data/p0p1DevState";
import { isP0P1Previewer } from "../data/p0p1Previewers";
import { useAuth } from "../auth/useAuth";
import { P0P1BallotScorecard, MidwayBallotScorecard, FinalBallotScorecard, CHAMFER } from "../components/p0p1/P0P1BallotScorecard";
import { PickGrid } from "../components/p0p1/CommunityGrid";
import { useIsMobile } from "../lib/use-is-mobile";
import { useP0P1Ballot } from "../data/useP0P1Ballot";
import { SLOTS } from "../data/p0p1Slots";
import { groupBySlot, findExtremes, classifyYourPick } from "../data/p0p1Stats";
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
    setEditingSlotKey,
    activeSlotKey,
    activeSlot,
    selectAdvance,
    phase,
    ratingsSnapshot,
    ballots,
  } = ballot;

  const { user: authUser } = useAuth();
  const canPreviewPre = p0p1DevEnabled || isP0P1Previewer(authUser?.discordId);

  const isDesktop = !useIsMobile(1024);
  const heroRef = useRef<HTMLDivElement>(null);
  const [heroHeight, setHeroHeight] = useState(0);
  useEffect(() => {
    const el = heroRef.current;
    if (!el) return;
    const measure = () => setHeroHeight(el.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (!featured) return <NotFoundPage />;
  if (featured.status === "pre" && !canPreviewPre) {
    return authLoading ? <div className="bg-bg min-h-screen" /> : <NotFoundPage />;
  }

  const isCompleteEntrant = isPastDeadline && Boolean(user) && isComplete;
  const didNotVote = isPastDeadline && Boolean(user) && !isComplete;
  const groupedStats = hasParticipated && pickStats ? groupBySlot(pickStats) : undefined;

  if (!isDesktop) {
    return (
      <>
        <P0P1MobileSelector ballot={ballot} />
        <P0P1DevPanel />
      </>
    );
  }

  const loginCta = !authLoading && !user && (
    <button type="button" onClick={signIn} className="bg-transparent border-0 cursor-pointer p-0">
      <CtaPill size="lg" icon={<DiscordIcon size={19} />}>
        {!isPastDeadline ? <>LOG IN TO SUBMIT PICKS</> : <>LOG IN TO VIEW YOUR PICKS</>}
      </CtaPill>
    </button>
  );

  const showMidway = phase === "midway" || (phase === "finalizing" && midwayDataReady);
  const ballotScorecard =
    user && isPastDeadline && isComplete && pickStats && pickStats.length > 0 ? (
      phase === "final" && resultsDataReady && ratingsSnapshot && cards && ballots ? (
        <FinalBallotScorecard
          ratingsSnapshot={ratingsSnapshot}
          pickStats={pickStats}
          ballots={ballots}
          cards={cards}
          picksBySlot={picksBySlot}
          discordId={user.discordId}
        />
      ) : (phase === "midway" || phase === "finalizing") && resultsDataReady && ratingsSnapshot && cards ? (
        <MidwayBallotScorecard ratingsSnapshot={ratingsSnapshot} cards={cards} picksBySlot={picksBySlot} />
      ) : (
        <P0P1BallotScorecard pickStats={pickStats} picksBySlot={picksBySlot} />
      )
    ) : null;
  const didNotVoteCard = didNotVote ? <DidNotVoteCard /> : null;
  const heroCta =
    loginCta ||
    (user && !isPastDeadline ? <AutoSaveBadge complete={isComplete} /> : null) ||
    ballotScorecard ||
    didNotVoteCard;

  const belowIntro = isPastDeadline ? null : (
    <div className="flex items-center gap-3 w-full max-w-[420px]">
      <SectionLabel size={13}>PICKS</SectionLabel>
      <div className="flex-1">
        <P0P1ProgressBar filled={scoringFilled} total={SLOTS.length} isComplete={isComplete} />
      </div>
    </div>
  );

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col animate-fadeIn">
      <AppHeader subtitle="P0 P1 Challenge" subtitleShort="P0 P1" />
      {featured && <P0P1Hero featured={featured} innerRef={heroRef} cta={heroCta} belowIntro={belowIntro} phase={phase} dateRange={ratingsSnapshot?.dateRange} />}

      <main className="flex-1 px-10 pb-5 pt-5">
        {!isPastDeadline &&
          (dataReady ? (
            <RosterStrip
              activeSlotKey={activeSlotKey}
              picksBySlot={picksBySlot}
              cardsByName={cardsByName}
              setCode={featured?.code}
              onSelect={(key) => setEditingSlotKey(key)}
            />
          ) : (
            <RosterStripSkeleton />
          ))}

        {phase === "loading" ? (
          <ResultsSkeleton />
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
            <ResultsSkeleton />
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
            <ResultsSkeleton />
          )
        ) : phase === "postVoting" || phase === "finalizing" ? (
          pickStats && pickStats.length > 0 && (
            <PostVotingStats
              pickStats={pickStats}
              cardsByName={cardsByName}
              picksBySlot={picksBySlot}
              setCode={featured?.code}
              yourPicks={
                isCompleteEntrant ? (
                  <div>
                    <div className="relative flex items-baseline justify-center gap-2 mb-2">
                      <SectionLabel size={22} className="text-white">YOUR PICKS</SectionLabel>
                    </div>
                    <PickGrid
                      cardsByName={cardsByName}
                      picksBySlot={picksBySlot}
                      setCode={featured?.code}
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
                    />
                  </div>
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
    <div className="inline-block animate-fadeUpIn" style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1 }}>
      <div className="bg-surface2 w-[clamp(280px,22vw,340px)] px-5 py-3 flex flex-col gap-1.5" style={{ clipPath: CHAMFER }}>
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
      </div>
    </div>
  );
}

function RosterStrip({
  activeSlotKey,
  picksBySlot,
  cardsByName,
  setCode,
  onSelect,
}: {
  activeSlotKey: SlotKey;
  picksBySlot: Map<string, string>;
  cardsByName: Map<string, Card>;
  setCode?: string;
  onSelect: (key: SlotKey) => void;
}) {
  return (
    <div className="grid grid-cols-8 gap-2">
      {SLOTS.map((slot) => {
        const cardName = picksBySlot.get(slot.key);
        return (
          <RosterTile
            key={slot.key}
            slot={slot}
            card={cardName ? cardsByName.get(cardName) : undefined}
            active={activeSlotKey === slot.key}
            setCode={setCode}
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
  onClick,
}: {
  slot: SlotDefinition;
  card: Card | undefined;
  active: boolean;
  setCode?: string;
  onClick: () => void;
}) {
  const accent = SLOT_ACCENT[slot.key];
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
          <SlotPip slotKey={slot.key} size={48} setCode={setCode} />
        )}
      </div>
      <div className="px-2 pt-2 pb-1.5 shrink-0">
        <div className="text-subtle text-[12px] tracking-[0.12em] font-display truncate mb-1">
          {slot.label.toUpperCase()}
        </div>
        {card ? (
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-text text-[14px] truncate min-w-0">{card.name}</span>
            <span className="ml-auto shrink-0">
              <ManaCost cost={card.manaCost} size={13} />
            </span>
          </div>
        ) : (
          <span className="italic text-dim text-[13px]">Select a card</span>
        )}
      </div>
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

function RosterStripSkeleton() {
  return (
    <div className="grid grid-cols-8 gap-2">
      {Array.from({ length: SLOTS.length }, (_, i) => (
        <SkeletonTile key={i} />
      ))}
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col items-center gap-2">
        <div className="h-5 w-52 bg-surface2 animate-pulse" />
        <div className="h-3 w-72 bg-surface2 animate-pulse" />
      </div>
      <div className="grid grid-cols-8 gap-2">
        {Array.from({ length: SLOTS.length }, (_, i) => (
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
