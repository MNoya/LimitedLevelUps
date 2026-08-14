import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { DraftReviewMOCS, type ReviewSeatInfo } from "../components/pod/review/DraftReviewMOCS";
import { SectionLabel } from "../components/SectionLabel";
import { BackButton, MobilePageHeader, PrevNextNav } from "../components/PageNav";
import { useIsLandscapePhone, useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { PodTable, PodTableSkeleton } from "../components/pod/PodTable";
import { PlayerSeatPanel } from "../components/pod/PlayerSeatPanel";
import type { RoundOutcome } from "../components/pod/PlayerSeatPanel";
import { MobileSeatStack, MobileSeatStackSkeleton } from "../components/pod/MobileSeatStack";
import { DeckScreenshotModal, type DeckTab } from "../components/pod/DeckScreenshotModal";
import {
  compareStandings,
  hasStandings,
  PodStandings,
  PodStandingsSkeleton,
  StandingsBackBar,
} from "../components/pod/PodStandings";
import {
  usePodDraftArtifact,
  usePodEventBySlug,
  usePodEventMatches,
  usePodEventParticipants,
  usePodEventReplays,
  usePodEvents,
} from "../data/hooks";
import { resolveDeck } from "../data/draft-artifact";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import { useCardImageMap } from "../data/cardImages";
import { podDiscordName, podEventTitle, podSeatName } from "../data/utils";
import type {
  PodEventParticipantRow,
  PodSeat,
} from "../types/leaderboard";

const TABLE_MAX_WIDE = 720;
const TABLE_MAX_SHRUNK = 700;
const ANIMATION_MS = 500;
const CHROME_OFFSET = 200;
const RAIL_SLIDE_MS = 220;
const CHROME_OFFSET_LANDSCAPE = 84;
const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_WIDTH_LANDSCAPE = 280;

function assignSeats(rows: PodEventParticipantRow[]): PodSeat[] {
  const haveRealSeats = rows.some((r) => r.seatIndex != null);
  if (haveRealSeats) {
    return rows
      .slice()
      .filter((r) => r.seatIndex != null)
      .sort((a, b) => (a.seatIndex as number) - (b.seatIndex as number))
      .map((row) => ({
        ...row,
        seatIndex: row.seatIndex as number,
        discordName: podDiscordName(row),
      }));
  }
  const ordered = rows.slice().sort(compareStandings);
  return ordered.map((row, i) => ({
    ...row,
    seatIndex: i,
    discordName: podDiscordName(row),
  }));
}

function findSeatByName(seats: PodSeat[], name: string): PodSeat | undefined {
  const lower = name.toLowerCase();
  return (
    seats.find((p) => p.discordName === name) ??
    seats.find((p) => p.displayName === name) ??
    seats.find((p) => p.discordName.toLowerCase() === lower) ??
    seats.find((p) => p.displayName.toLowerCase() === lower)
  );
}

export function PodPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const preselectName = searchParams.get("player");
  const isMobile = useIsMobile();
  const isLandscapePhone = useIsLandscapePhone();
  const [selectedSeat, setSelectedSeat] = useState<number | null>(null);
  const [highlightedSeat, setHighlightedSeat] = useState<number | null>(null);
  const [highlightedRound, setHighlightedRound] = useState<number | null>(null);
  const [highlightedOutcome, setHighlightedOutcome] = useState<RoundOutcome | null>(null);
  const [animateLayout, setAnimateLayout] = useState(false);
  const [deckTarget, setDeckTarget] = useState<PodSeat | null>(null);
  const [deckInitialTab, setDeckInitialTab] = useState<DeckTab>("screenshot");

  const openDeck = (seat: PodSeat, tab: DeckTab = "screenshot") => {
    if (!decklistAccess.canViewSeat(seat.avatarUrl)) return;
    setDeckInitialTab(tab);
    setDeckTarget(seat);
  };

  const handleRoundHover = (seat: number | null, round: number | null, outcome: RoundOutcome | null) => {
    setHighlightedSeat(seat);
    setHighlightedRound(round);
    setHighlightedOutcome(outcome);
  };

  const handleSelectSeat = (seat: number | null) => {
    if (seat == null && isMobile && !standingsAvailable) return;
    const openingFromStandings = seat != null && selectedSeat == null;
    setSelectedSeat(seat);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (seat == null) {
          next.delete("player");
        } else {
          const participant = seats.find((p) => p.seatIndex === seat);
          if (participant) next.set("player", participant.discordName);
          else next.delete("player");
        }
        return next;
      },
      { replace: !openingFromStandings },
    );
  };

  const { data: event, isLoading: eventLoading } = usePodEventBySlug(slug);
  const eventId = event?.eventId;
  const { data: participantRows, isLoading: participantsLoading } = usePodEventParticipants(eventId);
  const { data: draftArtifact } = usePodDraftArtifact(eventId);
  // Warm the card-image map for the whole draft so the review's first pick paints instantly on entry.
  const warmImageItems = useMemo(
    () => (draftArtifact ? draftArtifact.cards.map((c) => ({ name: c.n, set: c.s ?? draftArtifact.set })) : []),
    [draftArtifact],
  );
  const warmedImages = useCardImageMap(warmImageItems);
  const deckTargetMainboard = useMemo(
    () => (draftArtifact && deckTarget ? resolveDeck(draftArtifact, deckTarget.seatIndex) : null),
    [draftArtifact, deckTarget],
  );
  const cycleDeck = (direction: number) => {
    if (!deckTarget || seats.length === 0) return;
    const index = seats.findIndex((s) => s.seatIndex === deckTarget.seatIndex);
    if (index === -1) return;
    for (let step = 1; step <= seats.length; step++) {
      const next = seats[(((index + direction * step) % seats.length) + seats.length) % seats.length];
      if (decklistAccess.canViewSeat(next.avatarUrl)) {
        setDeckTarget(next);
        return;
      }
    }
  };
  const { data: matches, isLoading: matchesLoading } = usePodEventMatches(eventId);
  const { data: replays, isLoading: replaysLoading } = usePodEventReplays(eventId);
  const { data: setEvents } = usePodEvents(event?.setCode);
  const decklistAccess = usePodDecklistAccess(event);

  const { prevSlug, nextSlug } = useMemo(() => {
    if (!setEvents || !event) return { prevSlug: null, nextSlug: null };
    const nowMs = Date.now();
    const started = setEvents.filter(
      (e) => e.championDisplayName || new Date(e.eventTime).getTime() <= nowMs,
    );
    const idx = started.findIndex((e) => e.eventId === event.eventId);
    if (idx < 0) return { prevSlug: null, nextSlug: null };
    return {
      prevSlug: idx > 0 ? started[idx - 1].slug : null,
      nextSlug: idx < started.length - 1 ? started[idx + 1].slug : null,
    };
  }, [setEvents, event]);
  const prevTo = prevSlug ? `/pods/${prevSlug}` : null;
  const nextTo = nextSlug ? `/pods/${nextSlug}` : null;

  const chromeOffset = isLandscapePhone ? CHROME_OFFSET_LANDSCAPE : CHROME_OFFSET;
  const panelMinWidth = isLandscapePhone ? PANEL_MIN_WIDTH_LANDSCAPE : PANEL_MIN_WIDTH;
  const mainClass = `flex-1 flex flex-col px-3 min-h-0 ${isLandscapePhone ? "pb-2" : "md:px-6 pb-5"}`;
  const tableColumnPad = isLandscapePhone ? "py-1 pr-2" : "py-3 md:py-4 pr-5 md:pr-7";
  const contentRowPad = isLandscapePhone ? "py-1" : "py-2";
  const pageHeader = isLandscapePhone ? (
    <MobilePageHeader
      backTo="/pods"
      prevTo={prevTo}
      nextTo={nextTo}
      prevAriaLabel="Previous pod"
      nextAriaLabel="Next pod"
    />
  ) : (
    <AppHeader subtitle="POD DRAFT BREAKDOWN" />
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (deckTarget) return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      const t = e.target;
      if (t instanceof HTMLElement) {
        if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return;
      }
      if (e.key === "ArrowLeft" && prevTo) {
        e.preventDefault();
        navigate(prevTo);
      } else if (e.key === "ArrowRight" && nextTo) {
        e.preventDefault();
        navigate(nextTo);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prevTo, nextTo, navigate, deckTarget]);

  const seats = useMemo<PodSeat[]>(() => {
    if (!participantRows) return [];
    return assignSeats(participantRows).map((s) => ({
      ...s,
      deckColors: decklistAccess.canViewSeat(s.avatarUrl) ? s.deckColors : null,
      ...(draftArtifact ? { hasDeckList: resolveDeck(draftArtifact, s.seatIndex) !== null } : {}),
    }));
  }, [participantRows, draftArtifact, decklistAccess]);

  const participantsBySeatName = useMemo(() => {
    const m = new Map<string, PodSeat>();
    for (const s of seats) m.set(podSeatName(s), s);
    return m;
  }, [seats]);

  const selectedParticipant =
    selectedSeat == null ? null : seats.find((p) => p.seatIndex === selectedSeat) ?? null;

  const standingsAvailable = hasStandings(seats);

  const [displayParticipant, setDisplayParticipant] = useState<PodSeat | null>(selectedParticipant);

  useEffect(() => {
    if (selectedParticipant) {
      setDisplayParticipant(selectedParticipant);
      return;
    }
    const t = setTimeout(() => setDisplayParticipant(null), ANIMATION_MS);
    return () => clearTimeout(t);
  }, [selectedParticipant]);

  useEffect(() => {
    if (!event || animateLayout) return;
    const id = window.requestAnimationFrame(() => setAnimateLayout(true));
    return () => window.cancelAnimationFrame(id);
  }, [event, animateLayout]);

  const [preselectChecked, setPreselectChecked] = useState(false);

  useEffect(() => {
    setPreselectChecked(false);
    setSelectedSeat(null);
  }, [slug]);

  useEffect(() => {
    if (preselectChecked) return;
    if (!participantRows) return;
    if (seats.length === 0) {
      setPreselectChecked(true);
      return;
    }
    let target: PodSeat | undefined;
    if (preselectName) {
      target = findSeatByName(seats, preselectName);
    } else if (isMobile && !standingsAvailable) {
      target = seats.find((p) => p.placement === 1) ?? seats[0];
    }
    if (target) setSelectedSeat(target.seatIndex);
    setPreselectChecked(true);
  }, [seats, preselectName, isMobile, preselectChecked, participantRows]);

  // Browser Back and Forward move ?player=, so the open seat follows the URL and not only the click
  useEffect(() => {
    if (!preselectChecked || !standingsAvailable) return;
    if (preselectName == null) {
      setSelectedSeat(null);
      return;
    }
    const target = findSeatByName(seats, preselectName);
    if (target) setSelectedSeat(target.seatIndex);
  }, [preselectName, preselectChecked, standingsAvailable, seats]);

  const preselectPending = (!!preselectName || isMobile) && !preselectChecked;
  const railOpensOnLoad = event ? event.kind !== "mock" : true;

  if (eventLoading || (event && participantsLoading) || (event && preselectPending)) {
    if (isMobile) {
      return (
        <div className="bg-bg text-text min-h-screen flex flex-col">
          <MobilePageHeader
            backTo="/pods"
            prevTo={null}
            nextTo={null}
            prevAriaLabel="Previous pod"
            nextAriaLabel="Next pod"
          />
          <MobileSeatStackSkeleton
            variant={preselectName ? "player" : "standings"}
            finalized={event?.isFinalized ?? true}
            teamDraft={event?.isTeamDraft ?? false}
          />
        </div>
      );
    }
    return (
      <div className="bg-bg text-text h-screen flex flex-col overflow-hidden">
        {pageHeader}
        <main className={mainClass}>
          {!isLandscapePhone && (
            <div className="pt-5 pb-2 flex items-center justify-between gap-4 shrink-0">
              <BackButton to="/pods" label="BACK TO POD DRAFTS" inline />
            </div>
          )}
          {railOpensOnLoad ? (
            <div className={`flex-1 flex items-stretch min-h-0 ${contentRowPad}`}>
              <div className={`flex items-center min-w-0 shrink-0 justify-end ${tableColumnPad}`} style={{ width: "55%" }}>
                <PodTableSkeleton
                  maxWidth={`min(${TABLE_MAX_SHRUNK}px, calc(100vh - ${chromeOffset}px))`}
                />
              </div>
              <div className="min-w-0 shrink-0 self-start max-h-full" style={{ width: "45%" }}>
                <PodPanelSkeleton
                  minWidth={panelMinWidth}
                  variant={preselectName ? "player" : "standings"}
                  finalized={event?.isFinalized ?? true}
                />
              </div>
            </div>
          ) : (
            <div className={`flex-1 flex items-center justify-center min-h-0 ${contentRowPad}`}>
              <PodTableSkeleton
                maxWidth={`min(${TABLE_MAX_WIDE}px, calc(100vh - ${chromeOffset}px))`}
              />
            </div>
          )}
        </main>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="bg-bg text-text min-h-screen">
        <AppHeader subtitle="POD DRAFTS" />
        <main className="px-6 md:px-10 py-16 max-w-[720px]">
          <SectionLabel className="mb-3">Not found</SectionLabel>
          <h1 className="font-display text-text" style={{ fontSize: 36, letterSpacing: "0.04em" }}>
            No pod matched <span className="text-muted">"{slug}"</span>.
          </h1>
          <p className="text-muted mt-4">
            <Link to="/pods" className="text-green hover:underline">
              Back to pod drafts
            </Link>
          </p>
        </main>
      </div>
    );
  }

  const eventLabel = podEventTitle(event).toUpperCase();
  const medallionLabel = podEventTitle(event, { teamAsSuffix: false }).toUpperCase();
  const deckLogHref =
    draftArtifact && deckTarget && decklistAccess.canViewSeat(deckTarget.avatarUrl)
      ? `/pods/${event.slug}/${deckTarget.playerSlug ?? deckTarget.seatIndex}`
      : null;
  const open = selectedParticipant !== null || standingsAvailable;
  const detailOpen = selectedParticipant !== null;
  const tableMaxPx = open ? TABLE_MAX_SHRUNK : TABLE_MAX_WIDE;
  const loadedMatches = matches ?? [];
  const loadedReplays = replays ?? [];
  const auxLoading = matchesLoading || replaysLoading;
  const standingsActions = {
    eventSlug: event.slug,
    hasDraftLog: !!draftArtifact,
    canViewSeat: decklistAccess.canViewSeat,
    onShowDeck: (seat: PodSeat) => openDeck(seat),
  };

  if (isMobile) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <MobilePageHeader
          backTo="/pods"
          prevTo={prevTo}
          nextTo={nextTo}
          prevAriaLabel="Previous pod"
          nextAriaLabel="Next pod"
        />
        <MobileSeatStack
          participants={seats}
          participantsBySeatName={participantsBySeatName}
          matches={loadedMatches}
          replays={loadedReplays}
          selectedSeat={selectedSeat}
          onSelect={handleSelectSeat}
          onShowDeck={openDeck}
          canViewSeat={decklistAccess.canViewSeat}
          podFinalized={event.isFinalized}
          eventLabel={eventLabel}
          setCode={event.setCode}
          eventSlug={event.slug}
          hasDraftLog={!!draftArtifact}
          formatLabel={event.formatLabel}
          isMock={event.kind === "mock"}
          standingsAvailable={standingsAvailable}
          teamDraft={event.isTeamDraft ?? false}
          standingsActions={standingsActions}
        />
        {deckTarget && (
          <DeckScreenshotModal
            participant={{
              eventId: deckTarget.eventId,
              displayName: deckTarget.discordName,
              participantDisplayName: deckTarget.displayName,
              deckColors: deckTarget.deckColors,
              deckScreenshotUrl: deckTarget.deckScreenshotUrl,
              deckScreenshotCaption: deckTarget.deckScreenshotCaption,
              mainboard: deckTargetMainboard,
              record: deckTarget.record,
            }}
            initialTab={deckInitialTab}
            draftLogHref={deckLogHref}
            cardImages={warmedImages}
            onClose={() => setDeckTarget(null)}
            onPrev={() => cycleDeck(-1)}
            onNext={() => cycleDeck(1)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="bg-bg text-text h-screen flex flex-col overflow-hidden">
      {pageHeader}

      <main className={mainClass}>
        {!isLandscapePhone && (
          <div className="pt-5 pb-2 flex items-center justify-between gap-4 shrink-0">
            <BackButton to="/pods" label="BACK TO POD DRAFTS" inline />
            <PrevNextNav
              prevTo={prevTo}
              nextTo={nextTo}
              prevAriaLabel="Previous pod"
              nextAriaLabel="Next pod"
            />
          </div>
        )}

        <div className={`flex-1 flex items-stretch min-h-0 ${contentRowPad}`}>
          <div
            className={`flex items-center min-w-0 shrink-0 ${tableColumnPad} ${open ? "justify-end" : "justify-center"}`}
            style={{
              width: open ? "55%" : "100%",
              transition: animateLayout ? `width ${ANIMATION_MS}ms ease-out` : "none",
            }}
          >
            <PodTable
              participants={seats}
              selectedSeat={selectedSeat}
              highlightedSeat={highlightedSeat}
              highlightedRound={highlightedRound}
              highlightedOutcome={highlightedOutcome}
              onSelect={handleSelectSeat}
              onShowDeck={openDeck}
              canViewDeck={decklistAccess.canViewSeat}
              eventLabel={medallionLabel}
              teamDraft={event.isTeamDraft ?? false}
              eventSlug={event.slug}
              hasDraftLog={!!draftArtifact}
              setCode={event.setCode}
              formatLabel={event.formatLabel}
              date={event.eventDate}
              maxWidth={`min(${tableMaxPx}px, calc(100vh - ${chromeOffset}px))`}
            />
          </div>
          <div
            className="min-w-0 shrink-0 self-start max-h-full flex flex-col min-h-0"
            style={{
              width: open ? "45%" : "0%",
              opacity: open ? 1 : 0,
              transition: animateLayout
                ? `width ${ANIMATION_MS}ms ease-out, opacity ${ANIMATION_MS - 80}ms ease-out`
                : "none",
            }}
          >
            <div className="pod-panel-shell bg-surface border border-border flex flex-col min-h-0 flex-1 overflow-hidden">
              <div className="relative flex flex-col min-h-0 flex-1" style={{ minWidth: panelMinWidth }}>
                {standingsAvailable && (
                  <RailLayer shown={!detailOpen} hiddenShift="-translate-x-4" className="overflow-y-auto themed-scrollbar">
                    <PodStandings
                      seats={seats}
                      teamDraft={event.isTeamDraft ?? false}
                      finalized={event.isFinalized}
                      selectedSeat={selectedSeat}
                      onSelect={handleSelectSeat}
                      onHover={(seat) => handleRoundHover(seat, null, null)}
                      actions={standingsActions}
                    />
                  </RailLayer>
                )}
                <RailLayer shown={detailOpen || !standingsAvailable} hiddenShift="translate-x-6">
                  {standingsAvailable && <StandingsBackBar onClick={() => handleSelectSeat(null)} />}
                  {displayParticipant && (
                    <PlayerSeatPanel
                      key={displayParticipant.displayName}
                      participant={displayParticipant}
                      participantsBySeatName={participantsBySeatName}
                      matches={loadedMatches}
                      replays={loadedReplays}
                      setCode={event.setCode}
                      eventSlug={event.slug}
                      hasDraftLog={!!draftArtifact}
                      canViewSeat={decklistAccess.canViewSeat}
                      podFinalized={event.isFinalized}
                      onRoundHover={handleRoundHover}
                      onShowDeck={openDeck}
                      isMock={event.kind === "mock"}
                    />
                  )}
                  {displayParticipant && auxLoading && (
                    <div className="px-5 py-2 text-muted text-[12px] font-body">
                      Loading matches & replays…
                    </div>
                  )}
                </RailLayer>
              </div>
            </div>
          </div>
        </div>
      </main>
      {deckTarget && (
        <DeckScreenshotModal
          participant={{
            eventId: deckTarget.eventId,
            displayName: deckTarget.discordName,
            participantDisplayName: deckTarget.displayName,
            deckColors: deckTarget.deckColors,
            deckScreenshotUrl: deckTarget.deckScreenshotUrl,
            deckScreenshotCaption: deckTarget.deckScreenshotCaption,
            mainboard: deckTargetMainboard,
            record: deckTarget.record,
          }}
          initialTab={deckInitialTab}
          draftLogHref={deckLogHref}
          onClose={() => setDeckTarget(null)}
          onPrev={() => cycleDeck(-1)}
          onNext={() => cycleDeck(1)}
        />
      )}
    </div>
  );
}

export function PodDraftLogRoute() {
  const { slug, who, pack, pick } = useParams<{ slug: string; who?: string; pack?: string; pick?: string }>();
  const navigate = useNavigate();
  const { data: event, isLoading: eventLoading } = usePodEventBySlug(slug);
  const eventId = event?.eventId;
  const { data: participantRows, isLoading: participantsLoading } = usePodEventParticipants(eventId);
  const { data: artifact, isLoading: artifactLoading } = usePodDraftArtifact(eventId);
  const decklistAccess = usePodDecklistAccess(event);

  const seats = useMemo(
    () => (participantRows ? assignSeats(participantRows) : []),
    [participantRows],
  );

  if (eventLoading || (event && (participantsLoading || artifactLoading))) {
    return <div className="fixed inset-0 z-50 bg-bg" />;
  }
  if (!event || !artifact) {
    return <Navigate to={`/pods/${slug ?? ""}`} replace />;
  }

  if (!who) {
    return <Navigate to={`/pods/${slug}`} replace />;
  }

  const resolved = resolveLogSeat(seats, who);
  const initialSeat = resolved != null && resolved < artifact.seats.length ? resolved : 0;
  const initialPack = pack ? Number(pack) - 1 : 0;
  const initialPick = pick ? Number(pick) - 1 : 0;
  const seatInfo: ReviewSeatInfo[] = seats.map((s) => ({
    seatIndex: s.seatIndex,
    displayName: s.discordName,
    participantDisplayName: s.displayName,
    avatarUrl: s.avatarUrl,
    deckColors: s.deckColors,
    deckScreenshotUrl: s.deckScreenshotUrl,
    deckScreenshotCaption: s.deckScreenshotCaption,
    record: s.record,
  }));

  const current = resolved != null ? seats.find((s) => s.seatIndex === resolved) : null;
  const backHref = `/pods/${slug}${current ? `?player=${encodeURIComponent(current.discordName)}` : ""}`;

  // While the pod is closed a player gets their own draft in scroll-only mode; only organizers and
  // finished pods open the whole-table review.
  const soloOwnSeat = !decklistAccess.canViewAll;
  if (soloOwnSeat && !(current && decklistAccess.canViewSeat(current.avatarUrl))) {
    return <Navigate to={`/pods/${slug}`} replace />;
  }

  return (
    <DraftReviewMOCS
      artifact={artifact}
      meta={{ setCode: event.setCode, name: event.name }}
      initialSeat={initialSeat}
      initialPack={initialPack}
      initialPick={initialPick}
      onClose={() => navigate(backHref)}
      backHref={backHref}
      onNavigate={(seatIndex, p, pk) => {
        const target = seats.find((s) => s.seatIndex === seatIndex);
        if (target) {
          navigate(`/pods/${slug}/${seatIdentifier(target)}/${p + 1}/${pk + 1}`, { replace: true });
        }
      }}
      eventId={event.eventId}
      seatInfo={seatInfo}
      soloSeat={soloOwnSeat ? initialSeat : undefined}
    />
  );
}

function seatIdentifier(seat: PodSeat): string {
  return seat.playerSlug ?? String(seat.seatIndex);
}

function resolveLogSeat(seats: PodSeat[], who: string): number | null {
  const bySlug = seats.find((s) => s.playerSlug === who);
  if (bySlug) {
    return bySlug.seatIndex;
  }
  const n = Number(who);
  if (Number.isInteger(n) && seats.some((s) => s.seatIndex === n)) {
    return n;
  }
  return null;
}

function RailLayer({
  shown,
  hiddenShift,
  className,
  children,
}: {
  shown: boolean;
  hiddenShift: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      aria-hidden={!shown}
      className={cn(
        "flex flex-col ease-out motion-reduce:transition-none transition-[transform,opacity]",
        shown
          ? "relative flex-1 min-h-0 translate-x-0 opacity-100"
          : `absolute inset-0 ${hiddenShift} opacity-0 pointer-events-none`,
        className,
      )}
      style={{ transitionDuration: `${RAIL_SLIDE_MS}ms` }}
    >
      {children}
    </div>
  );
}

function PodPanelSkeleton({
  minWidth = PANEL_MIN_WIDTH,
  variant = "player",
  finalized = true,
}: {
  minWidth?: number;
  variant?: "player" | "standings";
  finalized?: boolean;
}) {
  if (variant === "standings") {
    return (
      <div className="pod-panel-shell bg-surface border border-border max-h-full overflow-hidden">
        <div style={{ minWidth }}>
          <PodStandingsSkeleton finalized={finalized} />
        </div>
      </div>
    );
  }
  return (
    <div className="pod-panel-shell bg-surface border border-border max-h-full overflow-hidden">
      <div style={{ minWidth }}>
        <div className="flex items-center gap-4 px-4 md:px-5 xl:px-8 py-5 border-b border-border">
          <div className="w-[54px] h-[54px] bg-surface2 animate-pulse shrink-0" />
          <div className="min-w-0 flex-1 flex flex-col gap-2">
            <div className="h-7 w-2/3 bg-surface2 animate-pulse" />
            <div className="h-4 w-1/3 bg-surface2 animate-pulse" />
          </div>
          <div className="flex flex-col gap-2 shrink-0">
            <div className="h-[44px] w-[200px] bg-surface2 animate-pulse" />
            <div className="h-[44px] w-[200px] bg-surface2 animate-pulse" />
          </div>
        </div>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="border-b border-border last:border-b-0 px-4 md:px-5 xl:px-8 py-3 flex items-center gap-3">
            <div className="h-[52px] w-[72px] bg-surface2 animate-pulse" />
            <div className="h-5 w-8 bg-surface2 animate-pulse" />
            <div className="h-5 flex-1 bg-surface2 animate-pulse" />
            <div className="h-[34px] w-[120px] bg-surface2 animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

