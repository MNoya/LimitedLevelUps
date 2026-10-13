import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { useNow } from "../../lib/countdown";
import { Check, Eye, EyeOff, Lock, Plus, Repeat } from "lucide-react";
import { Tooltip } from "../Tooltip";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { usePersistentBool } from "../../lib/use-persistent-bool";
import { DiscordIcon } from "../BrandIcons";
import { ChevronDown } from "../Icons";
import { SectionLabel } from "../SectionLabel";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import {
  CountryFlag,
  PlayerPortrait,
  QUALIFICATION_ORDER,
  QualificationChips,
  SLOTS,
  SearchBox,
  fullName,
  playerSlug,
  cardName,
  FitText,
  PicksCountdown,
  PicksLockDate,
  qualificationLabel,
  qualificationOf,
  shortLastName,
  slotFor,
  useFieldFilters,
  useLineupPicker,
  type FieldPlayer,
  type Lineup,
  type Qualification,
  type Slot,
  type SlotKey,
} from "./fantasyField";
import { PickButton, PlayerProfile, PlayerProfileSheet } from "./PlayerProfilePanel";
import {
  EventCrest,
  EventSwitcher,
  EventTitle,
  ProfileHint,
  FieldTile,
  HoverCard,
  useHoverTarget,
  useLongPress,
} from "./FantasyParts";
import { TabLink } from "../TabButton";
import { useAuth } from "../../auth/useAuth";
import { LeaderboardSkeleton, MembersLeaderboard } from "./MembersLeaderboard";
import { ReplayStandings, StandingsSkeleton, type TeamSlot } from "./ReplayStandings";
import { ProPlaySkeleton } from "./ProPlaySkeleton";
import { replayProfileEvent, standingsAfter, standingsRound } from "./fantasyReplay";
import { usePersistedLineup } from "./usePersistedLineup";
import {
  FantasyEventContext,
  fantasyEventByCode,
  fantasyEventPath,
  useFantasyEvent,
  type FantasyEventEntry,
  type FantasyEventHeader,
} from "./fantasyEvents";
import { devPresetState, picksAtPreviewPhase, readsDemoData, useFantasyDevPreset } from "./fantasyDevState";
import { Top8Bracket, Top8BracketList } from "./Top8Bracket";
import { eventContext, membersFromRows, standings, type Member, type StandingsDay } from "./fantasyMembers";
import { type BracketPicks } from "./fantasyTop8";
import { dayOneRecord, isOut, recordThrough, type EventPhase } from "./fantasyScoring";
import { LiveEventContext, buildLiveEvent, liveBracketResults, useLiveEvent, type LiveEvent } from "./fantasyLive";
import { usePersistedBracket } from "./usePersistedBracket";
import {
  useFantasyDemo,
  useFantasyEventState,
  useFantasyField,
  useFantasyMembers,
  useFantasyResults,
} from "../../data/hooks";
import type {
  FantasyBracketPickRow,
  FantasyEventState,
  FantasyLineupRow,
  FantasyMemberRow,
} from "../../types/fantasy";


type Picker = ReturnType<typeof useLineupPicker>;
type Filters = ReturnType<typeof useFieldFilters>;

type SheetView = "field" | "standings" | "top8" | "leaderboard";

export function TeamSheet({ loginCta, onSignIn }: { loginCta: ReactNode; onSignIn: () => void }) {
  const header = useFantasyEvent();
  const entry = fantasyEventByCode(header.code);
  const [spoilerFree, setSpoilerFree] = usePersistentBool("fantasySpoilerFree", true);
  const now = useNow(15_000);
  const minute = Math.floor(now / 60_000);
  const devPreset = useFantasyDevPreset(entry);
  const { data: storedState } = useFantasyEventState(header.code);
  const baseState = useMemo(() => storedState ?? (entry ? stateFromRegistry(entry) : undefined), [storedState, entry]);
  const demoActive = baseState ? readsDemoData(devPreset, baseState) : false;
  const { data: demo } = useFantasyDemo(demoActive);
  const state = useMemo(
    () => (baseState && entry ? devPresetState(devPreset, baseState, entry, minute * 60_000) : baseState),
    [baseState, entry, devPreset, minute],
  );
  const { data: storedField } = useFantasyField(header.code);
  const { data: storedResults } = useFantasyResults(header.code, storedState?.completedThroughRound);
  const field = demoActive ? demo?.field : storedField;
  const results = demoActive ? demo?.results : storedResults;
  const locked = state ? now >= new Date(state.picksLockAt).getTime() : false;
  const bracketLocked = state ? now >= new Date(state.bracketLockAt).getTime() : false;
  const membersVersion = state && locked && !demoActive ? `${state.completedThroughRound}:${bracketLocked}` : undefined;
  const { data: storedMembers } = useFantasyMembers(header.code, membersVersion);
  const memberData = useMemo(
    () => {
      if (!demoActive || !demo) {
        return storedMembers;
      }
      return { members: demo.members, lineups: demo.lineups, brackets: demo.brackets };
    },
    [demoActive, demo, storedMembers],
  );
  const throughRound = state ? (spoilerFree ? state.revealedThroughRound : state.completedThroughRound) : 0;
  const liveEvent = useMemo(
    () => {
      if (!entry || !state) {
        return null;
      }
      const demoData = demoActive ? (demo ?? null) : null;
      const readOnly = devPreset !== "live";
      return buildLiveEvent(entry, state, field ?? [], results ?? [], throughRound, new Date(now), demoData, readOnly);
    },
    [entry, state, field, results, throughRound, minute, demoActive, demo, devPreset],
  );
  const members = useMemo(
    () =>
      liveEvent?.readOnly && memberData
        ? { ...memberData, lineups: picksAtPreviewPhase(memberData.lineups, liveEvent.phase) }
        : memberData,
    [liveEvent?.readOnly, liveEvent?.phase, memberData],
  );
  const liveHeader = useMemo(
    () =>
      state
        ? {
            ...header,
            picksLockAt: new Date(state.picksLockAt),
            bracketLockAt: new Date(state.bracketLockAt),
          }
        : header,
    [header, state],
  );
  if (!liveEvent) {
    return <ProPlaySkeleton layout="sheet" />;
  }
  return (
    <FantasyEventContext.Provider value={liveHeader}>
      <LiveEventContext.Provider value={liveEvent}>
        <TeamSheetView
          key={devPreset}
          fieldLoading={!field || devPreset === "skeleton"}
          loginCta={loginCta}
          onSignIn={onSignIn}
          liveEvent={liveEvent}
          members={members}
          spoilerFree={spoilerFree}
          onToggleSpoilerFree={() => setSpoilerFree((value) => !value)}
        />
      </LiveEventContext.Provider>
    </FantasyEventContext.Provider>
  );
}

function TeamSheetView({
  fieldLoading,
  loginCta,
  onSignIn,
  liveEvent,
  members,
  spoilerFree,
  onToggleSpoilerFree,
}: {
  fieldLoading: boolean;
  loginCta: ReactNode;
  onSignIn: () => void;
  liveEvent: LiveEvent;
  members: { members: FantasyMemberRow[]; lineups: FantasyLineupRow[]; brackets: FantasyBracketPickRow[] } | undefined;
  spoilerFree: boolean;
  onToggleSpoilerFree: () => void;
}) {
  const fantasyEvent = useFantasyEvent();
  const { cardAreaRef, cardWidth, cardAreaMinHeight } = useFittedCardWidth();
  const picker = useLineupPicker();
  const now = useNow(15_000);
  const picksOpen = now < fantasyEvent.picksLockAt.getTime();
  const phase = liveEvent.phase;
  const roundsPlayed = liveEvent.roundsPlayed;
  const live = phase !== "picking";
  const replacing = phase === "cut" && liveEvent.replacementsOpen;
  const lineupWritable = ((!live && picksOpen) || replacing) && !liveEvent.readOnly;
  const { dayOneLineup, restoring } = usePersistedLineup(picker, liveEvent, !loginCta, lineupWritable, fieldLoading);
  const teamLoading = restoring || (live && !members);
  const filters = useFieldFilters(liveEvent.players);
  const isMobile = useIsMobile(1024);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const sheetSlug = searchParams.get("player");
  const sheetPlayer = sheetSlug ? (liveEvent.bySlug.get(sheetSlug) ?? null) : null;
  const { hoverTarget, onHover: handleHover, onLeave: handleLeave } = useHoverTarget(isMobile);
  const activeSlot = picker.activeSlot ? slotFor(picker.activeSlot) : null;
  const { view: viewSlug } = useParams();
  const defaultView = defaultViewFor(phase);
  const view = sheetViewFromSlug(viewSlug) ?? defaultView;
  const viewPath = (option: SheetView) => {
    const basePath = fantasyEventPath(liveEvent.event);
    return option === defaultView ? basePath : `${basePath}/${SHEET_VIEW_SLUG[option]}`;
  };
  const seeded = liveEvent.seeded;
  const results = liveBracketResults(liveEvent);
  const topEightOpen = phase === "top8" || phase === "final";
  const bracketOpen = liveEvent.bracketWindowOpen && now < fantasyEvent.bracketLockAt.getTime() && !results;
  const [bracketPicks, setBracketPicks] = usePersistedBracket(
    liveEvent,
    !loginCta,
    bracketOpen && !liveEvent.readOnly,
    fieldLoading,
  );

  const replacingSlot = picker.activeSlot && picker.lineup[picker.activeSlot] ? picker.activeSlot : null;

  useEffect(() => {
    if (!replacingSlot) {
      return;
    }
    const cancelOnOutsidePress = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target?.closest("[data-fantasy-pick-target]")) {
        picker.setActiveSlot(null);
      }
    };
    document.addEventListener("pointerdown", cancelOnOutsidePress);
    return () => document.removeEventListener("pointerdown", cancelOnOutsidePress);
  }, [replacingSlot]);

  const slotIsReplaceable = (key: SlotKey) => {
    const player = picker.lineup[key];
    const original = dayOneLineup?.[key];
    return replacing && Boolean(player && original && isOut(liveEvent, original));
  };

  const allMembers = useMemo(
    () => (members ? membersFromRows(liveEvent, members.members, members.lineups, members.brackets) : []),
    [liveEvent, members],
  );
  const savedSelf = allMembers.find((member) => member.isSelf);
  const selfMember: Member | null =
    savedSelf && dayOneLineup
      ? { ...savedSelf, dayOneLineup, lineup: picker.lineup, bracket: bracketPicks }
      : null;
  const others = allMembers.filter((member) => !member.isSelf);
  const memberRows = live ? standings(selfMember ? [selfMember, ...others] : others, eventContext(liveEvent)) : [];
  const memberCount = allMembers.length;
  const selfRow = memberRows.find((row) => row.member.isSelf);
  const standingsDays: StandingsDay[] = topEightOpen ? ["overall", "day1", "day2", "top8"] : ["overall", "day1", "day2"];

  const cardPoints = (key: SlotKey) => (live ? selfRow?.slots.find((slot) => slot.slot === key)?.total : undefined);

  const replacedPick = (key: SlotKey) => {
    const original = dayOneLineup?.[key];
    const current = picker.lineup[key];
    if (!live || !original || !current || fullName(original) === fullName(current)) {
      return undefined;
    }
    return original;
  };

  const replacedSlotByName = new Map<string, SlotKey>();
  for (const slot of SLOTS) {
    const replaced = replacedPick(slot.key);
    if (replaced) {
      replacedSlotByName.set(fullName(replaced), slot.key);
    }
  }

  const cardRecord = (key: SlotKey) => {
    const player = picker.lineup[key];
    return live && player ? recordThrough(liveEvent, player) : undefined;
  };

  const cardOut = (key: SlotKey) => {
    const player = picker.lineup[key];
    return live && Boolean(player && isOut(liveEvent, player));
  };

  const selectCard = (key: SlotKey) => {
    if (!live && picksOpen) {
      picker.setActiveSlot(key);
      return;
    }
    if (live && slotIsReplaceable(key)) {
      picker.setActiveSlot(picker.activeSlot === key ? null : key);
      return;
    }
    const player = picker.lineup[key];
    if (player) {
      openProfile(player);
    }
  };

  const score = selfRow?.total ?? 0;
  const liveStatus = (short: boolean) =>
    live ? (
      <LiveStatus
        phase={phase}
        roundsPlayed={roundsPlayed}
        score={score}
        rank={selfRow?.rank ?? null}
        loading={teamLoading}
        memberCount={memberCount}
        short={short}
        spoilerControl={<SpoilerEye on={spoilerFree} onToggle={onToggleSpoilerFree} />}
      />
    ) : null;


  const isPicked = (player: FieldPlayer) => picker.pickedSlotByName.has(fullName(player));

  const teamSlotOf = (player: FieldPlayer): TeamSlot | null => {
    const name = fullName(player);
    const picked = picker.pickedSlotByName.get(name);
    if (picked) {
      return { slot: picked, dayOne: false };
    }
    const replaced = replacedSlotByName.get(name);
    return replaced ? { slot: replaced, dayOne: true } : null;
  };

  const handleTileClick = (player: FieldPlayer) => {
    handleLeave();
    if (!live && picksOpen) {
      picker.toggle(player);
      return;
    }
    const targetSlot = live ? replacementTargetSlot() : null;
    if (targetSlot && !isPicked(player) && !isOut(liveEvent, player)) {
      picker.assign(player, targetSlot);
      return;
    }
    openProfile(player);
  };

  const replacementTargetSlot = () => {
    if (picker.activeSlot && slotIsReplaceable(picker.activeSlot)) {
      return picker.activeSlot;
    }
    for (const slot of SLOTS) {
      if (slotIsReplaceable(slot.key) && cardOut(slot.key)) {
        return slot.key;
      }
    }
    return null;
  };

  const clickPicks = (!live && picksOpen) || (live && replacementTargetSlot() !== null);

  const profileSearch = (player: FieldPlayer) => {
    const params = new URLSearchParams(searchParams);
    params.set("player", playerSlug(player));
    return `?${params.toString()}`;
  };

  const openProfile = (player: FieldPlayer) => {
    handleLeave();
    navigate(profileSearch(player), { state: { fromField: true } });
  };

  const standingsSource = liveEvent;
  const sheetOrder = useMemo(() => {
    if (view === "standings" && live) {
      const round = standingsRound(standingsSource, searchParams.get("round"));
      return standingsAfter(standingsSource, round).map((row) => row.player);
    }
    if (view === "top8" && topEightOpen) {
      return seeded;
    }
    return fieldGroups(filters.players).flatMap((group) => group.players);
  }, [view, live, topEightOpen, standingsSource, searchParams, seeded, filters.players]);
  const sheetName = sheetPlayer ? fullName(sheetPlayer) : null;
  const sheetIndex = sheetOrder.findIndex((player) => fullName(player) === sheetName);
  const neighborSearch = (offset: number) => {
    const neighbor = sheetIndex >= 0 ? sheetOrder[sheetIndex + offset] : undefined;
    return neighbor ? profileSearch(neighbor) : undefined;
  };

  const profileEventFor = (player: FieldPlayer) =>
    roundsPlayed > 0 ? replayProfileEvent(liveEvent, player, (opponent) => profileSearch(opponent)) : undefined;

  const closeProfile = () => {
    if ((location.state as { fromField?: boolean } | null)?.fromField) {
      navigate(-1);
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete("player");
    navigate({ search: params.toString() }, { replace: true });
  };

  const profileSheet = sheetPlayer ? (
    <PlayerProfileSheet
      player={sheetPlayer}
      event={profileEventFor(sheetPlayer)}
      footer={
        live ? null : (
          <PickButton
            activeSlot={activeSlot}
            inLineup={isPicked(sheetPlayer)}
            onToggle={() => {
              picker.toggle(sheetPlayer);
              closeProfile();
            }}
          />
        )
      }
      prevHref={neighborSearch(-1)}
      nextHref={neighborSearch(1)}
      onClose={closeProfile}
    />
  ) : null;

  const field = (
    <FieldGroups
      loading={fieldLoading}
      picker={picker}
      filters={filters}
      compact={isMobile}
      replacedSlotByName={replacedSlotByName}
      onTileClick={handleTileClick}
      onTileLongPress={openProfile}
      onTileHover={handleHover}
      onTileLeave={handleLeave}
    />
  );

  const leaderboard = (
    <MembersLeaderboard
      rows={memberRows}
      days={standingsDays}
      results={results}
      seeded={seeded}
      compact={isMobile}
      onInspect={openProfile}
      onHover={handleHover}
      onLeave={handleLeave}
    />
  );
  const bracketProps = {
    seeded,
    picks: bracketPicks,
    results,
    onChange: bracketOpen ? setBracketPicks : undefined,
    onInspect: openProfile,
    onHover: handleHover,
    onLeave: handleLeave,
  };
  const bracket = isMobile ? <Top8BracketList {...bracketProps} /> : <Top8Bracket {...bracketProps} />;
  const standingsView = live ? (
    <ReplayStandings
      source={standingsSource}
      compact={isMobile}
      onOpen={openProfile}
      onSelect={handleTileClick}
      teamSlot={teamSlotOf}
      onHover={handleHover}
      onLeave={handleLeave}
    />
  ) : (
    <ViewPlaceholder
      backdrop={<StandingsSkeleton compact={isMobile} rows={16} />}
      title="Standings appear after Round 1"
      detail="Follow every player's rank and record round by round"
      at={<PicksLockDate size={14} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />}
    />
  );
  const bracketView = topEightOpen ? (
    bracket
  ) : (
    <ViewPlaceholder
      backdrop={isMobile ? <Top8BracketList seeded={[]} results={null} /> : <Top8Bracket seeded={[]} results={null} />}
      title="Top 8 Bracket opens after the last Swiss round"
      detail="Pick who wins each Top 8 match to add points to your total"
    />
  );
  const leaderboardView = live ? (
    leaderboard
  ) : (
    <ViewPlaceholder
      backdrop={<LeaderboardSkeleton compact={isMobile} rows={14} />}
      title="Leaderboard starts after Round 1"
      detail="Follow every member's team and points round by round"
      at={<PicksLockDate size={14} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />}
    />
  );
  const viewTabs = (
    <div className="flex border-b border-border">
      {SHEET_VIEWS.map((option) => (
        <TabLink key={option} active={view === option} to={viewPath(option)}>
          {VIEW_LABEL[option]}
        </TabLink>
      ))}
    </div>
  );
  const showField = view === "field";
  const viewBody = { field, standings: standingsView, top8: bracketView, leaderboard: leaderboardView }[view];

  if (isMobile) {
    return (
      <main className="flex-1 pb-[190px]">
        <MobileHeader status={liveStatus(true)} />
        <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur border-b border-border">
          {viewTabs}
          {showField ? (
            <div className="px-3 py-2.5 flex flex-col gap-2">
              <SearchBox value={filters.search} onChange={filters.setSearch} className="w-full" />
              <div className="-mx-3 px-3 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
                <div className="w-max">
                  <QualificationChips
                    active={filters.qualification}
                    onChange={filters.setQualification}
                    players={liveEvent.players}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>
        <div className="px-3 pt-3">{viewBody}</div>
        <MobileTray
          picker={picker}
          cta={live ? null : loginCta}
          showSaved={!live}
          onOpenProfile={openProfile}
          onSelect={selectCard}
          cardPoints={cardPoints}
          cardOut={cardOut}
          cardRecord={cardRecord}
          replacedPick={replacedPick}
        />
        {profileSheet}
      </main>
    );
  }

  return (
    <main className="flex-1 min-h-0 grid grid-cols-[510px_1fr] overflow-hidden">
      <section className="themed-scrollbar h-full border-r border-border bg-surface px-6 py-6 flex flex-col min-h-0 overflow-y-auto">
        <div className="flex justify-center">
          <EventTitle
            event={fantasyEvent}
            switcher={<EventSwitcher activeCode={fantasyEvent.code} />}
            crest={eventCrest(fantasyEvent, 56)}
            crestRaised
            labelSize={13}
            glyphSize={36}
            titleSize={42}
            citySize={18}
          />
        </div>
        {live ? (
          <div className="mt-3 flex flex-col items-center gap-3">{liveStatus(false)}</div>
        ) : (
          <div className="mt-3 flex flex-col items-center gap-0.5">
            <PicksPremise compact={false} />
            <PicksCountdown size={13} />
            <PicksLockDate size={13} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />
          </div>
        )}

            <div
              ref={cardAreaRef}
              className="flex-1 flex flex-col items-center justify-center gap-5 py-3"
              style={{ minHeight: cardAreaMinHeight }}
            >
              <PhaseNote />
              <div className="grid grid-cols-2 gap-x-5 gap-y-4">
                {SLOTS.map((slot) => {
                  const player = picker.lineup[slot.key];
                  return (
                    <SheetCard
                      key={slot.key}
                      slot={slot}
                      player={player}
                      active={picker.activeSlot === slot.key}
                      size="lg"
                      width={cardWidth}
                      points={cardPoints(slot.key)}
                      record={cardRecord(slot.key)}
                      out={cardOut(slot.key)}
                      replaced={replacedPick(slot.key)}
                      onClick={() => selectCard(slot.key)}
                      onHover={(element) => (player ? handleHover(player, element) : undefined)}
                      onReplacedHover={handleHover}
                      onReplacedOpen={openProfile}
                      onLongPress={player ? () => openProfile(player) : undefined}
                      onLeave={handleLeave}
                    />
                  );
                })}
              </div>
            </div>
            {live || !loginCta ? null : <div className="flex justify-center pb-3">{loginCta}</div>}
            <div className="flex flex-col items-center pt-3 border-t border-border">
              <ScoringRules />
            </div>
      </section>

      <section className="themed-scrollbar min-w-0 h-full overflow-y-auto [scrollbar-gutter:stable] px-7 pb-6">
        <div className={cn("sticky top-0 z-10 -mx-7 px-7 mb-3 bg-bg/95 backdrop-blur", showField && "border-b border-border")}>
          {viewTabs}
          {showField ? (
        <div className="py-3 flex items-center gap-4">
          <span className="shrink-0 grid text-[14px] text-subtle whitespace-nowrap">
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">Picking Constructed</span>
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">
              Replace before Round {liveEvent.cutRound + 1}
            </span>
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">
              <DiscordIcon size={14} className="inline-block mr-1.5" />
              Log in to save picks
            </span>
            <span className="col-start-1 row-start-1">
              <PickingStatus picker={picker} phase={phase} signedIn={!loginCta} onSignIn={onSignIn} />
            </span>
          </span>
          <div className="flex-1 min-w-0 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
            <div className="w-max">
              <QualificationChips
                active={filters.qualification}
                onChange={filters.setQualification}
                players={liveEvent.players}
              />
            </div>
          </div>
          <SearchBox
            value={filters.search}
            onChange={filters.setSearch}
            placeholder="Search players"
            className="ml-auto w-[180px] shrink-0"
          />
        </div>
          ) : null}
        </div>
        <div className={showField ? undefined : "pt-3"}>{viewBody}</div>
      </section>

      {profileSheet}
      {hoverTarget ? (
        <HoverCard target={hoverTarget}>
          <PlayerProfile
            player={hoverTarget.player}
            compact
            preview
            event={profileEventFor(hoverTarget.player)}
          />
          <ProfileHint rightClick={clickPicks} />
        </HoverCard>
      ) : null}
    </main>
  );
}

function FieldGroups({
  loading,
  picker,
  filters,
  compact,
  replacedSlotByName,
  onTileClick,
  onTileLongPress,
  onTileHover,
  onTileLeave,
}: {
  loading: boolean;
  picker: Picker;
  filters: Filters;
  compact: boolean;
  replacedSlotByName: Map<string, SlotKey>;
  onTileClick: (player: FieldPlayer) => void;
  onTileLongPress: (player: FieldPlayer) => void;
  onTileHover: (player: FieldPlayer, element: HTMLElement) => void;
  onTileLeave: () => void;
}) {
  const liveEvent = useLiveEvent();
  const groups = useMemo(() => fieldGroups(filters.players), [filters.players]);

  const minColumn = compact ? 160 : 210;
  const columns = `repeat(auto-fill, minmax(${minColumn}px, 1fr))`;
  const gridClass = cn("grid gap-y-2.5", compact ? "gap-x-1.5" : "gap-x-2.5");
  const grid = { className: gridClass, style: { gridTemplateColumns: columns } };
  if (loading) {
    return <FieldSkeleton grid={grid} compact={compact} />;
  }
  return (
    <div className={cn("flex flex-col", compact ? "gap-5" : "gap-7")}>
      {groups.map((group) => (
        <div key={group.key}>
          <SectionLabel size={compact ? 16 : 18} color="#ffffff" className="mb-3">
            {qualificationLabel(group.key, liveEvent.players).toUpperCase()}
          </SectionLabel>
          <div {...grid}>
            {group.players.map((player) => (
              <FieldTile
                key={fullName(player)}
                player={player}
                pickedSlot={picker.pickedSlotByName.get(fullName(player)) ?? null}
                replacedSlot={replacedSlotByName.get(fullName(player)) ?? null}
                out={isOut(liveEvent, player)}
                detail={
                  <span className="truncate">
                    {isOut(liveEvent, player) ? dayOneRecord(liveEvent, player) : player.country}
                  </span>
                }
                onClick={() => onTileClick(player)}
                onLongPress={() => onTileLongPress(player)}
                onHover={(element) => onTileHover(player, element)}
                onLeave={onTileLeave}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function FieldSkeleton({ grid, compact }: { grid: { className: string; style: CSSProperties }; compact: boolean }) {
  const nameWidths = [62, 48, 70, 55, 66, 44, 58, 74];
  return (
    <div>
      <SectionLabel size={compact ? 16 : 18} color="transparent" className={compact ? "mb-2" : "mb-3"}>
        LOADING
      </SectionLabel>
      <div {...grid}>
        {Array.from({ length: compact ? 12 : 24 }, (_, index) => (
          <div
            key={index}
            className={cn("flex items-center gap-2.5 pr-2 border border-border bg-surface", compact ? "h-[57px]" : "h-[48px]")}
          >
            <span className="self-stretch w-12 shrink-0 bg-surface2" />
            <span className="h-3 bg-surface2" style={{ width: `${nameWidths[index % nameWidths.length]}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function stateFromRegistry(event: FantasyEventEntry): FantasyEventState {
  return {
    revealedThroughRound: 0,
    completedThroughRound: 0,
    picksLockAt: event.picksLockAt,
    dayTwoStartedAt: null,
    bracketLockAt: event.bracketLockAt,
    top8StartedAt: null,
  };
}

function fieldGroups(players: FieldPlayer[]): { key: Qualification; players: FieldPlayer[] }[] {
  const byQualification = new Map<Qualification, FieldPlayer[]>();
  for (const player of players) {
    const key = qualificationOf(player);
    const list = byQualification.get(key) ?? [];
    list.push(player);
    byQualification.set(key, list);
  }
  return QUALIFICATION_ORDER.filter((key) => byQualification.has(key)).map((key) => ({
    key,
    players: byQualification.get(key) ?? [],
  }));
}

function MobileTray({
  picker,
  cta,
  onOpenProfile,
  onSelect,
  cardPoints,
  cardOut,
  cardRecord,
  replacedPick,
  showSaved,
}: {
  picker: Picker;
  cta: ReactNode;
  showSaved: boolean;
  onOpenProfile: (player: FieldPlayer) => void;
  onSelect: (key: SlotKey) => void;
  cardPoints: (key: SlotKey) => number | undefined;
  cardOut: (key: SlotKey) => boolean;
  cardRecord: (key: SlotKey) => string | undefined;
  replacedPick: (key: SlotKey) => FieldPlayer | undefined;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 bg-surface border-t border-border px-2 pt-1.5 pb-2">
      {cta ? (
        <div className="absolute left-1/2 bottom-full mb-3 -translate-x-1/2 drop-shadow-[0_6px_16px_rgba(0,0,0,0.6)]">{cta}</div>
      ) : showSaved ? (
        <SavedFlash lineup={picker.lineup} />
      ) : null}
      <div className="mx-auto grid grid-cols-4 gap-1.5" style={{ maxWidth: TRAY_MAX_WIDTH }}>
        {SLOTS.map((slot) => {
          const player = picker.lineup[slot.key];
          return (
            <SheetCard
              key={slot.key}
              slot={slot}
              player={player}
              active={picker.activeSlot === slot.key}
              size="xs"
              points={cardPoints(slot.key)}
              record={cardRecord(slot.key)}
              out={cardOut(slot.key)}
              replaced={replacedPick(slot.key)}
              onReplacedOpen={onOpenProfile}
              onClick={() => {
                const alreadyReplacing = player && picker.activeSlot === slot.key;
                if (alreadyReplacing) {
                  picker.setActiveSlot(null);
                  return;
                }
                onSelect(slot.key);
              }}
              onLongPress={player ? () => onOpenProfile(player) : undefined}
            />
          );
        })}
      </div>
    </div>
  );
}

function LiveStatus({
  phase,
  roundsPlayed,
  score,
  rank,
  loading,
  memberCount,
  short,
  spoilerControl,
}: {
  loading: boolean;
  phase: EventPhase;
  roundsPlayed: number;
  spoilerControl: ReactNode;
  score: number;
  rank: number | null;
  memberCount: number;
  short: boolean;
}) {
  const { swissRounds, topEightStarted } = useLiveEvent();
  const quietStatus = phase === "top8" && topEightStarted ? undefined : QUIET_STATUS[phase];
  return (
    <span className="flex flex-col items-center text-center gap-1">
      <span className="flex items-baseline gap-x-6 gap-y-1 flex-wrap justify-center">
        {loading ? <span className="self-center h-[18px] w-[180px] rounded bg-surface2 animate-pulse" /> : null}
        {loading || rank === null ? null : (
          <>
            <span className="flex items-baseline gap-1.5">
              <span className="font-num text-[18px] font-semibold text-green leading-none">{score}</span>
              <span className="text-[13px] text-subtle">pts</span>
            </span>
            <span className="text-[14px] text-text">
              Rank <b>{rank}</b> <span className="text-subtle">of {memberCount}</span>
            </span>
          </>
        )}
        <span className="inline-flex items-center gap-2 text-[13px] text-subtle">
          {quietStatus ? (
            quietStatus
          ) : (
            <>
              <LivePulse />
              {phase === "top8" ? "Top 8 Live" : `Round ${roundsPlayed + 1} of ${swissRounds}`}
            </>
          )}
          {spoilerControl}
        </span>
      </span>
      {short ? <PhaseNote /> : null}
    </span>
  );
}

function SpoilerEye({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  const [hover, setHover] = useState(false);
  const [tapToast, setTapToast] = useState(0);
  const Icon = on ? EyeOff : Eye;

  useEffect(() => {
    if (tapToast === 0) {
      return;
    }
    const timer = window.setTimeout(() => setTapToast(0), 2500);
    return () => window.clearTimeout(timer);
  }, [tapToast]);

  const showToastOnTap = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType !== "mouse") {
      setTapToast(Date.now());
    }
  };

  return (
    <Tooltip label={on ? SPOILER_FREE_TOOLTIP : SPOILERS_ON_TOOLTIP} side="bottom" open={hover || tapToast > 0}>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Spoiler free"
        onClick={onToggle}
        onPointerUp={showToastOnTap}
        onPointerEnter={(event) => event.pointerType === "mouse" && setHover(true)}
        onPointerLeave={() => setHover(false)}
        className="flex p-0.5 bg-transparent border-0 cursor-pointer text-subtle hover:text-text transition-colors"
      >
        <Icon size={16} />
      </button>
    </Tooltip>
  );
}

const SPOILER_FREE_TOOLTIP = (
  <>
    <span className="font-display text-[13px] tracking-[0.06em]">SPOILER FREE:</span> live coverage results only
  </>
);

const SPOILERS_ON_TOOLTIP = (
  <>
    <span className="font-display text-[13px] tracking-[0.06em]">SPOILERS ON:</span> latest results from melee.gg
  </>
);

const QUIET_STATUS: Partial<Record<EventPhase, string>> = {
  cut: "Day 1 Complete",
  top8: "Top 8 on Sunday",
  final: "Event Complete",
};

function PhaseNote() {
  const { phase, cutRound, bracketWindowOpen, topEightStarted } = useLiveEvent();
  if (phase === "cut") {
    return (
      <span className="text-[13px] text-text">
        Replace players who missed <b>Day 2</b> before Round {cutRound + 1}
      </span>
    );
  }
  if (phase === "top8" && bracketWindowOpen && !topEightStarted) {
    return (
      <span className="text-[13px] text-text">
        Fill in your <b>Top 8</b> Bracket before Sunday's Quarterfinals
      </span>
    );
  }
  return null;
}

function LivePulse() {
  return <span className="h-2.5 w-2.5 self-center rounded-full bg-green animate-liveHalo" />;
}

function SavedFlash({ lineup }: { lineup: Picker["lineup"] }) {
  const [visible, setVisible] = useState(false);
  const lineupKey = SLOTS.map((slot) => (lineup[slot.key] ? fullName(lineup[slot.key] as FieldPlayer) : "")).join("|");
  const previousKey = useRef(lineupKey);

  useEffect(() => {
    if (previousKey.current === lineupKey) {
      return;
    }
    previousKey.current = lineupKey;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 1400);
    return () => window.clearTimeout(timer);
  }, [lineupKey]);

  return (
    <span
      className={cn(
        "pointer-events-none absolute right-2 -top-8 flex items-center gap-1 rounded-full bg-surface border border-border2 px-2.5 py-1 text-[12px] text-green transition-opacity duration-300",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      <Check size={13} />
      Saved
    </span>
  );
}

function PickingStatus({
  picker,
  phase,
  signedIn,
  onSignIn,
}: {
  picker: Picker;
  phase: EventPhase;
  signedIn: boolean;
  onSignIn: () => void;
}) {
  const { cutRound } = useLiveEvent();
  if (phase === "day1" || phase === "day2" || phase === "top8" || phase === "final") {
    return (
      <>
        <Lock size={14} className="inline-block mr-1.5 align-[-2px]" />
        Picks are locked
      </>
    );
  }
  if (phase === "cut" && !picker.activeSlot) {
    return <>Replace before Round {cutRound + 1}</>;
  }
  if (!picker.activeSlot) {
    const complete = picker.filledCount === SLOTS.length;
    if (!complete) {
      return null;
    }
    if (!signedIn) {
      return (
        <button
          type="button"
          onClick={onSignIn}
          className="bg-transparent border-0 p-0 cursor-pointer text-green hover:underline text-[14px]"
        >
          <DiscordIcon size={14} className="inline-block align-[-2px] mr-1.5" />
          Log in to save picks
        </button>
      );
    }
    return (
      <>
        <Check size={14} className="inline-block align-[-2px] mr-1.5 text-green" />
        Picks saved
      </>
    );
  }
  const slot = slotFor(picker.activeSlot);
  return (
    <>
      Picking <span style={{ color: slot.accent }}>{slot.label}</span>
    </>
  );
}

const MOBILE_CREST_HEIGHT = 46;

function eventCrest(event: FantasyEventHeader, height: number): ReactNode {
  return event.crestUrl ? <EventCrest src={event.crestUrl} alt={event.crestAlt} height={height} /> : null;
}

function MobileHeader({ status }: { status: ReactNode }) {
  const fantasyEvent = useFantasyEvent();
  const [open, setOpen] = useState(true);
  return (
    <div className="px-3 pt-3 pb-3 bg-surface border-b border-border flex flex-col gap-2.5">
      <div className="flex justify-center">
        <EventTitle
          event={fantasyEvent}
          switcher={<EventSwitcher activeCode={fantasyEvent.code} mobile />}
          crest={eventCrest(fantasyEvent, MOBILE_CREST_HEIGHT)}
          labelSize={12}
          glyphSize={26}
          titleSize={30}
          citySize={15}
        />
      </div>
      <div className="flex justify-center">
        <span className="relative flex items-center">
          {status ?? <PicksCountdown size={13} compact />}
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            aria-label={open ? "Hide rules" : "Show rules"}
            className="absolute left-full top-1/2 -translate-y-1/2 ml-1.5 flex bg-transparent border-0 p-0 cursor-pointer"
          >
            <ChevronDown size={18} className={`text-subtle transition-transform ${open ? "" : "-rotate-90"}`} />
          </button>
        </span>
      </div>
      {open ? (
        <div className="flex flex-col items-center">
          {status ? null : (
            <>
              <div className="mb-2">
                <PicksLockDate size={13} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />
              </div>
              <PicksPremise compact />
            </>
          )}
          <ScoringRules short />
        </div>
      ) : null}
    </div>
  );
}

function PicksPremise({ compact }: { compact: boolean }) {
  const { picksLockAt, shortName } = useFantasyEvent();
  const picksOpen = useNow(30_000) < picksLockAt.getTime();
  if (!picksOpen) {
    return null;
  }
  return (
    <p
      className={cn(
        "m-0 mb-2 text-center text-subtle",
        compact ? "text-[clamp(12px,3.45vw,13.5px)] leading-[1.5] whitespace-nowrap" : "text-[14px] leading-[1.55]",
      )}
    >
      Put together a team of four Pro Players from <span className="font-semibold text-text">{shortName}</span>
      <br />
      <span className="text-[max(12px,calc(1em-1px))]">You score points every time they win a match</span>
    </p>
  );
}

function ScoringRules({ short = false }: { short?: boolean }) {
  const { phase, constructedFormat } = useLiveEvent();
  const phaseNoteSaysIt = short && phase === "cut";
  return (
    <div className="text-[14px] text-subtle leading-[1.6] text-center">
      <div>
        <b className="text-text">3 points</b> per match win and <b className="text-text">1</b> per draw
      </div>
      <div>
        <RoleName slotKey="captain" /> scores <b className="text-text">double</b> in All rounds
      </div>
      <div>
        <RoleName slotKey="drafter" /> scores <b className="text-text">triple</b> in Draft rounds
      </div>
      <div>
        <RoleName slotKey="constructed" /> scores <b className="text-text">double</b> in {constructedFormat} rounds
      </div>
      {phaseNoteSaysIt ? null : (
        <div
          className={cn("mt-1.5", short && "whitespace-nowrap")}
          style={short ? { fontSize: "clamp(11px, 3.3vw, 14px)" } : undefined}
        >
          <DayTwoNote />
        </div>
      )}
      {short ? <div className="mt-1.5 italic">Press and hold a player for more details</div> : null}
    </div>
  );
}

function RoleName({ slotKey }: { slotKey: SlotKey }) {
  const slot = slotFor(slotKey);
  return <span className="font-semibold" style={{ color: slot.accent }}>{slot.label}</span>;
}

function DayTwoNote() {
  const { cutRound } = useLiveEvent();
  return (
    <>
      Players who miss <span className="font-semibold text-text">Day 2</span> can be replaced before Round {cutRound + 1}
    </>
  );
}

const LARGE_CARD_WIDTH = 172;
const SMALLEST_CARD_WIDTH = 140;
const CARD_ASPECT = 63 / 88;
const TRAY_MAX_WIDTH = `calc(4 * 24svh * ${CARD_ASPECT} + 18px)`;
const CARD_AREA_CHROME = 24 + 16;
const CARD_NOTE_GAP = 20;

function useFittedCardWidth() {
  const cardAreaRef = useRef<HTMLDivElement>(null);
  const [cardWidth, setCardWidth] = useState(LARGE_CARD_WIDTH);
  useLayoutEffect(() => {
    const area = cardAreaRef.current?.parentElement;
    const cards = cardAreaRef.current;
    if (!area || !cards) {
      return;
    }
    const fit = () => {
      const cardNotes = cards.childElementCount - 1;
      let notesHeight = 0;
      for (const child of Array.from(cards.children).slice(0, cardNotes)) {
        notesHeight += (child as HTMLElement).offsetHeight + CARD_NOTE_GAP;
      }
      const restOfColumn = area.scrollHeight - cards.offsetHeight;
      const available = area.clientHeight - restOfColumn - notesHeight - CARD_AREA_CHROME;
      const fitted = Math.floor((available / 2) * CARD_ASPECT);
      setCardWidth(Math.max(SMALLEST_CARD_WIDTH, Math.min(LARGE_CARD_WIDTH, fitted)));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(area);
    for (const child of Array.from(area.children)) {
      if (child !== cards) {
        observer.observe(child);
      }
    }
    fit();
    return () => observer.disconnect();
  }, []);
  const cardAreaMinHeight = Math.ceil((cardWidth / CARD_ASPECT) * 2) + CARD_AREA_CHROME;
  return { cardAreaRef, cardWidth, cardAreaMinHeight };
}

function SheetCard({
  slot,
  player,
  active,
  size,
  width = LARGE_CARD_WIDTH,
  onClick,
  onHover,
  onLeave,
  onLongPress,
  points,
  record,
  out = false,
  replaced,
  onReplacedHover,
  onReplacedOpen,
}: {
  slot: Slot;
  player: FieldPlayer | undefined;
  active: boolean;
  size: "lg" | "xs";
  width?: number;
  points?: number;
  record?: string;
  out?: boolean;
  replaced?: FieldPlayer;
  onClick: () => void;
  onHover?: (element: HTMLElement) => void;
  onReplacedHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onReplacedOpen?: (player: FieldPlayer) => void;
  onLeave?: () => void;
  onLongPress?: () => void;
}) {
  const tiny = size === "xs";
  const longPress = useLongPress(() => onLongPress?.());
  const frameColor = player || active ? slot.accent : `${slot.accent}55`;
  const cardWidth = tiny ? undefined : width;
  return (
    <button
      data-fantasy-pick-target
      type="button"
      onClick={() => {
        if (!longPress.consumeFired()) {
          onClick();
        }
      }}
      onMouseEnter={(event) => onHover?.(event.currentTarget)}
      onMouseLeave={onLeave}
      onTouchStart={onLongPress ? longPress.start : undefined}
      onTouchEnd={onLongPress ? longPress.cancel : undefined}
      onTouchMove={onLongPress ? longPress.cancel : undefined}
      onContextMenu={(event) => {
        event.preventDefault();
        onLongPress?.();
      }}
      className={cn(
        "relative flex flex-col border-0 text-left cursor-pointer transition-transform duration-150 hover:-translate-y-0.5 select-none [-webkit-touch-callout:none]",
        tiny ? "w-full p-[3px] rounded-[6px]" : "p-[5px] rounded-[9px]",
      )}
      style={{
        width: cardWidth,
        aspectRatio: "63 / 88",
        background: "#0a0c10",
        boxShadow: `inset 0 0 0 2px ${frameColor}${active ? `, 0 0 22px ${slot.accent}40` : ""}`,
      }}
    >
      <span className={cn("flex flex-col h-full overflow-hidden bg-surface2", tiny ? "rounded-[4px]" : "rounded-[5px]")}>
        {player ? (
          <span className={cn("flex items-center bg-surface", tiny ? "px-1.5 h-[22px]" : "px-2 h-[28px]")}>
            <FitText text={tiny ? shortLastName(player) : cardName(player)} maxSize={tiny ? 12 : 15} />
          </span>
        ) : null}
        <span className="relative flex-1 min-h-0 overflow-hidden">
          {player ? (
            <>
              <span className={cn("block w-full h-full transition-opacity", (active || out) && "opacity-30", out && "grayscale")}>
                <PlayerPortrait player={player} initialsSize={tiny ? 16 : 48} />
              </span>
              {record !== undefined && !tiny ? <CardStatPill className="left-1 bottom-1">{record}</CardStatPill> : null}
              {points !== undefined && !tiny ? <CardStatPill className="right-1 bottom-1">{points} pts</CardStatPill> : null}
              {replaced ? (
                <ReplacedThumb
                  player={replaced}
                  size={tiny ? 22 : 40}
                  onHover={onReplacedHover}
                  onOpen={onReplacedOpen}
                  onLeave={(cardElement) => onHover?.(cardElement)}
                />
              ) : null}
              {tiny ? <TinyStatRow record={record} points={points} /> : null}
              {active ? (
                <span className="absolute inset-0 flex flex-col items-center justify-center gap-1">
                  <Repeat size={tiny ? 20 : 30} strokeWidth={2} style={{ color: slot.accent }} />
                  <span
                    className={cn("font-display tracking-[0.12em]", tiny ? "text-[12px]" : "text-[15px]")}
                    style={{ color: slot.accent }}
                  >
                    REPLACE
                  </span>
                </span>
              ) : null}
            </>
          ) : (
            <span className="absolute inset-0 flex items-center justify-center">
              <Plus size={tiny ? 18 : 34} strokeWidth={1.5} style={{ color: active ? slot.accent : "#3b4458" }} />
            </span>
          )}
        </span>
        <span className={cn("bg-surface flex items-center justify-between gap-1", tiny ? "px-1.5 h-[22px]" : "px-2 h-[28px]")}>
          <span
            className={cn(
              "font-display whitespace-nowrap [text-box:trim-both_cap_alphabetic]",
              tiny ? "text-[13px] tracking-[0.06em]" : "text-[15px] tracking-[0.12em]",
            )}
            style={{ color: slot.accent }}
          >
            {slot.label.toUpperCase()}
          </span>
          {player && !tiny ? <CountryFlag code={player.countryCode} width={21} /> : null}
        </span>
      </span>
    </button>
  );
}

function CardStatPill({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        "absolute rounded bg-black/80 px-1 py-0.5 font-num font-semibold leading-none text-[13px] text-text",
        className,
      )}
    >
      {children}
    </span>
  );
}

function TinyStatRow({ record, points }: { record?: string; points?: number }) {
  const pillClass = "rounded bg-black/80 px-1 py-0.5 font-num font-semibold leading-none text-text whitespace-nowrap";
  const fontSize = "clamp(10px, 3.1vw, 12px)";
  return (
    <span className="absolute inset-x-0.5 bottom-0.5 flex justify-between gap-0.5" style={{ fontSize }}>
      {record !== undefined ? <span className={pillClass}>{record}</span> : <span />}
      {points !== undefined ? <span className={pillClass}>{points} pts</span> : null}
    </span>
  );
}

function ReplacedThumb({
  player,
  size,
  onHover,
  onOpen,
  onLeave,
}: {
  player: FieldPlayer;
  size: number;
  onOpen?: (player: FieldPlayer) => void;
  onHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave?: (cardElement: HTMLElement) => void;
}) {
  return (
    <span
      onClick={(event) => {
        event.stopPropagation();
        onOpen?.(player);
      }}
      onMouseEnter={(event) => onHover?.(player, event.currentTarget)}
      onMouseLeave={(event) => {
        const cardElement = event.currentTarget.closest("button");
        if (cardElement) {
          onLeave?.(cardElement);
        }
      }}
      className="absolute right-1 top-1 overflow-hidden rounded-[3px] opacity-70 grayscale ring-1 ring-black/80"
      style={{ width: size, height: size }}
    >
      <PlayerPortrait player={player} initialsSize={Math.round(size * 0.4)} />
    </span>
  );
}

const SHEET_VIEWS: SheetView[] = ["field", "standings", "top8", "leaderboard"];

const SHEET_VIEW_SLUG: Record<SheetView, string> = {
  field: "players",
  standings: "standings",
  top8: "top-8",
  leaderboard: "leaderboard",
};

function sheetViewFromSlug(slug: string | undefined): SheetView | undefined {
  for (const option of SHEET_VIEWS) {
    if (SHEET_VIEW_SLUG[option] === slug) {
      return option;
    }
  }
  return undefined;
}

const VIEW_LABEL: Record<SheetView, string> = {
  field: "PLAYERS",
  standings: "STANDINGS",
  top8: "TOP 8",
  leaderboard: "LEADERBOARD",
};

function ViewPlaceholder({
  title,
  detail,
  at,
  backdrop,
}: {
  title: string;
  detail: string;
  at?: ReactNode;
  backdrop?: ReactNode;
}) {
  return (
    <div className="relative">
      {backdrop ? (
        <div
          aria-hidden="true"
          className="pointer-events-none select-none opacity-50 [mask-image:linear-gradient(to_bottom,black_40%,transparent)]"
        >
          {backdrop}
        </div>
      ) : null}
      <div className={cn("flex justify-center", backdrop ? "absolute inset-x-0 top-16" : "py-16")}>
        <div
          className={cn(
            "max-w-[520px] flex flex-col items-center gap-2 text-center",
            backdrop && "mx-3 px-8 py-6 bg-surface border border-border2 shadow-2xl",
          )}
        >
          <span className="font-display text-[20px] tracking-[0.06em] text-text">{title.toUpperCase()}</span>
          <span className="text-[14px] text-subtle leading-[1.5]">{detail}</span>
          <span className="mt-1">{at}</span>
        </div>
      </div>
    </div>
  );
}

function defaultViewFor(phase: EventPhase): SheetView {
  if (phase === "top8") {
    return "top8";
  }
  if (phase === "final") {
    return "leaderboard";
  }
  return "field";
}
