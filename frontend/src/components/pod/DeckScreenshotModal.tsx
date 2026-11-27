import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  CloudUpload,
  LoaderCircle,
  Pencil,
  X,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { ArrowRight, GiRoundTable, ImageIcon, LuScrollText, SiDiscord, TbCards } from "../Icons";
import { ChamferedButton } from "../ChamferedButton";
import { CopyTextButton } from "../CopyTextButton";
import { Tooltip } from "../Tooltip";
import { Pips } from "../ManaPips";
import { Record } from "../Record";
import { cn } from "../../lib/utils";
import { DeckPoolBoard, poolFromMainboard } from "./DeckPoolBoard";
import type { CardImages } from "../../data/cardImages";
import { useIsMobile } from "../../lib/use-is-mobile";
import { useResolvedDeckUrl } from "../../data/refresh-deck-url";
import { onPlainClick } from "./podLinks";
import type { DeckChanges, DeckEditor, DeckSaveStatus } from "./useDeckEditor";
import type { Mainboard } from "../../types/leaderboard";

const BREAKDOWN_CAPTION = "Seats, logs & replays";

export interface DeckLike {
  eventId?: string;
  displayName: string;
  participantDisplayName?: string;
  deckColors: string | null;
  deckScreenshotUrl: string | null;
  deckScreenshotCaption?: string | null;
  // Original public post that created a self-reported deck; surfaced as a "View on Discord" link
  deckSourceUrl?: string | null;
  mainboard?: Mainboard | null;
  record?: string | null;
  // Self-reported trophies refresh their Discord CDN screenshot by message ref instead of pod event
  screenshotChannelId?: string | null;
  screenshotMessageId?: string | null;
}

export type DeckTab = "screenshot" | "decklist";

interface Props {
  participant: DeckLike;
  initialTab?: DeckTab;
  tab?: DeckTab;
  onTabChange?: (tab: DeckTab) => void;
  breakdownHref?: string;
  hideDraftLog?: boolean;
  draftLogHref?: string | null;
  // A whole-draft image map warmed upstream; when passed the Card Pool reuses it instead of re-fetching its subset
  cardImages?: CardImages;
  editor?: DeckEditor;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  prevHref?: string;
  nextHref?: string;
}

export function DeckScreenshotModal({
  participant,
  initialTab = "screenshot",
  tab: controlledTab,
  onTabChange,
  breakdownHref,
  hideDraftLog = false,
  draftLogHref,
  cardImages,
  editor,
  onClose,
  onPrev,
  onNext,
  prevHref,
  nextHref,
}: Props) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState<(() => void) | null>(null);
  const editHint = useEditHint();
  const unsaved = editor?.status === "dirty";
  const guarded = (action: () => void) => () => {
    if (unsaved) {
      setLeaving(() => action);
    } else {
      action();
    }
  };
  const leaveTo = (href: string) => setLeaving(() => () => navigate(href));
  const guardLink = (href: string) => (e: React.MouseEvent) => {
    if (unsaved) {
      e.preventDefault();
      leaveTo(href);
    }
  };
  const close = guarded(onClose);
  const goPrev = onPrev && guarded(onPrev);
  const goNext = onNext && guarded(onNext);
  const keyActions = useRef({ close, goPrev, goNext, leaving });
  keyActions.current = { close, goPrev, goNext, leaving };

  const hasScreenshot = participant.deckScreenshotUrl !== null;
  const recordWins = Number((participant.record ?? "").split("-")[0] || 0);
  const recordLosses = Number((participant.record ?? "").split("-")[1] || 0);
  const hasRecord = participant.record != null && recordWins + recordLosses > 0;
  const mainboard = editor?.mainboard ?? participant.mainboard ?? null;
  const viewPool = useMemo(
    () => (participant.mainboard ? poolFromMainboard(participant.mainboard) : null),
    [participant.mainboard],
  );
  const pool = editor?.pool ?? viewPool;
  const hasDecklist = editor !== undefined || (mainboard?.cards.length ?? 0) > 0;
  const deckKey = `${participant.eventId ?? ""}::${participant.participantDisplayName ?? participant.displayName}`;
  const [ownTab, setOwnTab] = useState<DeckTab>(initialTab);
  const tab = controlledTab ?? ownTab;
  const selectTab = (next: DeckTab) => {
    setOwnTab(next);
    onTabChange?.(next);
  };
  const effectiveTab: DeckTab = hasScreenshot && hasDecklist ? tab : hasDecklist ? "decklist" : "screenshot";
  const showPanelToggle = hasScreenshot && hasDecklist;
  const showDraftLogTab = !hideDraftLog;
  const hasTabs = showPanelToggle || showDraftLogTab;
  const hasSourceLink = !!participant.deckSourceUrl;
  const panelHasControls = hasTabs || !!onPrev || !!onNext;
  const showTabBar = panelHasControls || hasSourceLink;

  const { url: resolvedUrl, resolving: isResolving } = useResolvedDeckUrl(participant);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const [zoomed, setZoomed] = useState(true);

  useEffect(() => {
    setZoomed(true);
  }, [participant.deckScreenshotUrl]);

  useEffect(() => {
    setImgLoaded(false);
    setImgFailed(false);
    if (!resolvedUrl) return;
    const preloader = new Image();
    preloader.onload = () => setImgLoaded(true);
    preloader.onerror = () => setImgFailed(true);
    preloader.src = resolvedUrl;
  }, [resolvedUrl]);

  const showSkeleton = isResolving || (resolvedUrl !== null && !imgLoaded && !imgFailed);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { close, goPrev, goNext, leaving } = keyActions.current;
      if (leaving) {
        if (e.key === "Escape") {
          setLeaving(null);
        }
        return;
      }
      if (e.key === "Escape") {
        close();
      } else if (e.key === "ArrowLeft" && goPrev) {
        e.preventDefault();
        goPrev();
      } else if (e.key === "ArrowRight" && goNext) {
        e.preventDefault();
        goNext();
      }
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col items-center bg-black/80 backdrop-blur-sm animate-fadeIn px-[4px] md:px-6 pt-28 pb-6 lg:pt-28 lg:pb-8"
      onClick={close}
      role="dialog"
      aria-modal="true"
      aria-label={`${participant.displayName}'s deck`}
    >
      <div
        className="relative bg-surface border border-border w-full max-w-[1400px] h-[70vh] shrink-0 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 lg:gap-6 pl-9 pr-5 py-3 border-b border-border shrink-0">
          <Pips colors={participant.deckColors ?? ""} size={18} />
          <span
            className="font-display text-text truncate flex-1 text-center lg:text-left"
            style={{
              fontSize: 26,
              lineHeight: 1,
              letterSpacing: "0.04em",
              fontFamily: "'Bebas Neue', sans-serif",
              paddingTop: 4,
            }}
          >
            {participant.displayName}
          </span>
          {hasRecord && <Record wins={recordWins} losses={recordLosses} className="font-num text-[20px] shrink-0" />}
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="text-muted hover:text-text transition-colors p-1 bg-transparent border-0 cursor-pointer shrink-0"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-hidden">
          <div key={deckKey} className="h-full animate-fadeIn">
            {effectiveTab === "decklist" && pool ? (
              <DeckPoolBoard
                pool={pool}
                warmedImages={cardImages}
                onDeckChange={editor?.track}
                floatingAction={editor && <DeckEditStatus editor={editor} hint={editHint} />}
                showGrid={(editHint.pinned || (!isMobile && editHint.hovered)) && editor?.status === "clean"}
              />
            ) : showSkeleton ? (
              <div className="h-full p-4 md:p-5">
                <div className="w-full h-full bg-surface2 animate-pulse" />
              </div>
            ) : imgFailed ? (
              <div className="h-full flex items-center justify-center px-5 text-center text-muted font-body">
                Deck screenshot failed to load
              </div>
            ) : resolvedUrl ? (
              isMobile ? (
                <div className="relative h-full">
                  {zoomed ? (
                    <div className="h-full overflow-x-auto overflow-y-hidden themed-scrollbar">
                      <img
                        src={resolvedUrl}
                        alt={`${participant.displayName} deck screenshot`}
                        className="block h-full w-auto max-w-none select-none"
                        draggable={false}
                      />
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center overflow-hidden">
                      <img
                        src={resolvedUrl}
                        alt={`${participant.displayName} deck screenshot`}
                        className="block max-h-full max-w-full w-auto h-auto select-none"
                        draggable={false}
                      />
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => setZoomed((z) => !z)}
                    aria-label={zoomed ? "Fit deck to screen" : "Zoom deck"}
                    className="absolute left-2 bottom-2 z-10 inline-flex items-center gap-1.5 rounded bg-bg/85 border border-border text-text px-2.5 py-1.5 font-display tracking-[0.14em] text-[11px] cursor-pointer backdrop-blur-sm"
                  >
                    {zoomed ? <ZoomOut size={13} /> : <ZoomIn size={13} />}
                    {zoomed ? "ZOOM OUT" : "ZOOM IN"}
                  </button>
                </div>
              ) : (
                <div className="h-full flex items-center justify-center overflow-hidden px-4 py-6">
                  <img
                    src={resolvedUrl}
                    alt={`${participant.displayName} deck screenshot`}
                    className="block max-h-full max-w-full w-auto h-auto select-none"
                    draggable={false}
                  />
                </div>
              )
            ) : (
              <div className="h-full flex items-center justify-center px-5 text-center text-muted font-body">
                No deck screenshot available
              </div>
            )}
          </div>
        </div>

        {breakdownHref && (
          <div className="hidden lg:block border-t border-border shrink-0">
            <div className="relative flex items-center justify-between gap-4 px-4 py-3 bg-surface hover:bg-green/5 transition-colors cursor-pointer">
              <div className="flex flex-1 items-center gap-3 min-w-0 pl-5">
                {participant.deckScreenshotCaption && (
                  <span className="text-muted text-[15px] font-body italic leading-snug min-w-0 truncate">
                    {participant.deckScreenshotCaption}
                  </span>
                )}
                {mainboard && <CopyDeckButton mainboard={mainboard} className="relative z-10 ml-auto" />}
              </div>
              <Link
                to={breakdownHref}
                onClick={guardLink(breakdownHref)}
                className={cn(
                  "flex items-center gap-4 shrink-0 no-underline",
                  "after:absolute after:inset-0 after:content-['']",
                )}
              >
                <span className="text-muted text-[13px] font-body">{BREAKDOWN_CAPTION}</span>
                <ChamferedButton>
                  <span className="inline-flex items-center gap-2">
                    <GiRoundTable size={30} className="-my-[6px]" />
                    VIEW BREAKDOWN
                    <ArrowRight size={14} />
                  </span>
                </ChamferedButton>
              </Link>
            </div>
          </div>
        )}
        {(participant.deckScreenshotCaption || hasDecklist) && (
          <div
            className={cn(
              "flex items-center gap-3 px-4 py-3 lg:pl-9 lg:pr-5 lg:py-4 border-t border-border shrink-0 bg-surface",
              breakdownHref && "lg:hidden",
            )}
          >
            {participant.deckScreenshotCaption && (
              <span className="text-muted text-[15px] font-body italic leading-snug min-w-0">
                {participant.deckScreenshotCaption}
              </span>
            )}
            {mainboard && <CopyDeckButton mainboard={mainboard} className="ml-auto" />}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0 w-full max-w-[1400px] flex flex-col items-center justify-center gap-4 pt-4 lg:gap-10 lg:pt-0 px-4 md:px-0">
        {showTabBar && (
          <div
            onClick={(e) => e.stopPropagation()}
            className={cn(
              "shrink-0 flex items-center rounded-2xl bg-surface border border-border shadow-lg px-3 py-2 lg:px-4",
              hasTabs ? "w-full lg:w-auto justify-between gap-2 lg:gap-4" : "justify-center gap-2 lg:gap-3",
            )}
          >
            {goPrev ? (
              <PanelChevron side="left" onClick={goPrev} href={prevHref} />
            ) : hasTabs ? (
              <span className="w-10 shrink-0" />
            ) : null}
            <div className="flex items-center gap-1.5">
              {hasSourceLink && (
                <a
                  href={participant.deckSourceUrl!}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-border bg-surface2 text-muted hover:text-text px-4 py-2.5 font-display tracking-[0.14em] no-underline transition-colors"
                  style={{ fontSize: 14 }}
                >
                  <SiDiscord size={16} />
                  VIEW ON DISCORD
                </a>
              )}
              {showPanelToggle && (
                <PanelTab
                  active={effectiveTab === "screenshot"}
                  onClick={guarded(() => selectTab("screenshot"))}
                  icon={<ImageIcon size={16} />}
                >
                  IMAGE
                </PanelTab>
              )}
              {showPanelToggle && (
                <PanelTab
                  active={effectiveTab === "decklist"}
                  onClick={() => selectTab("decklist")}
                  icon={<TbCards size={17} />}
                >
                  <span className="lg:hidden">POOL</span>
                  <span className="hidden lg:inline">CARD POOL</span>
                </PanelTab>
              )}
              {!hideDraftLog && (
                <PanelTab
                  disabled={!draftLogHref}
                  href={draftLogHref ?? undefined}
                  onClick={draftLogHref && unsaved ? () => leaveTo(draftLogHref) : undefined}
                  icon={<LuScrollText size={16} />}
                >
                  <span className="lg:hidden">LOG</span>
                  <span className="hidden lg:inline">DRAFT LOG</span>
                </PanelTab>
              )}
            </div>
            {goNext ? (
              <PanelChevron side="right" onClick={goNext} href={nextHref} />
            ) : hasTabs ? (
              <span className="w-10 shrink-0" />
            ) : null}
          </div>
        )}
        {breakdownHref && (
          <Link
            to={breakdownHref}
            onClick={(e) => {
              e.stopPropagation();
              guardLink(breakdownHref)(e);
            }}
            aria-label="View breakdown"
            className="lg:hidden self-end inline-flex items-center gap-1.5 pr-1 text-green hover:text-green/80 no-underline font-display tracking-[0.18em] leading-none"
            style={{ fontSize: 13 }}
          >
            VIEW BREAKDOWN
            <ArrowRight size={13} />
          </Link>
        )}
      </div>
      {leaving && editor && (
        <UnsavedDeckDialog
          editor={editor}
          onProceed={() => {
            setLeaving(null);
            leaving();
          }}
          onCancel={() => setLeaving(null)}
        />
      )}
    </div>,
    document.body,
  );
}

function DeckChangeList({ changes: { added, removed } }: { changes: DeckChanges }) {
  return (
    <div className="mt-5 border border-border bg-surface2/50 px-4 py-3">
      <h3 className="font-body text-[14px] font-semibold text-text">Maindeck changes</h3>
      <ul className="mt-2 flex max-h-[40vh] flex-col gap-1 overflow-y-auto themed-scrollbar">
        {added.map((name, i) => (
          <DeckChange key={`add-${i}`} name={name} added />
        ))}
        {removed.map((name, i) => (
          <DeckChange key={`remove-${i}`} name={name} added={false} />
        ))}
      </ul>
    </div>
  );
}

function DeckChange({ name, added }: { name: string; added: boolean }) {
  const Icon = added ? CirclePlus : CircleMinus;
  return (
    <li className="flex items-center gap-2 font-body text-[14px] text-text">
      <Icon
        size={16}
        className={cn("shrink-0", added ? "text-green" : "text-red")}
        aria-label={added ? "Added" : "Removed"}
      />
      <span className="min-w-0 truncate">{name}</span>
    </li>
  );
}

function UnsavedDeckDialog({
  editor,
  onProceed,
  onCancel,
}: {
  editor: DeckEditor;
  onProceed: () => void;
  onCancel: () => void;
}) {
  const saving = editor.status === "saving";
  const save = async () => {
    if (await editor.save()) {
      onProceed();
    }
  };
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4"
      onClick={(e) => {
        e.stopPropagation();
        onCancel();
      }}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="unsaved-deck-title"
    >
      <div
        className="w-full max-w-[400px] border border-border bg-surface p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="unsaved-deck-title"
          className="text-center font-display text-[20px] leading-tight tracking-[0.06em] text-text"
        >
          SAVE YOUR CHANGES TO THIS DECK?
        </h2>
        <DeckChangeList changes={editor.changes} />
        {editor.error && <p className="mt-3 text-center font-body text-[13px] text-red">{editor.error}</p>}
        <div className="mt-6 flex justify-center gap-4">
          <button
            type="button"
            onClick={onProceed}
            disabled={saving}
            className="inline-flex items-center rounded-full border border-border bg-surface2 px-4 py-2 font-display text-[14px] tracking-[0.14em] text-subtle transition-colors hover:text-text cursor-pointer disabled:opacity-50"
          >
            DISCARD
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full border border-green/50 bg-green/15 px-4 py-2 font-display text-[14px] tracking-[0.14em] text-green transition-colors hover:bg-green/25 cursor-pointer disabled:cursor-wait"
          >
            {saving ? <LoaderCircle size={16} className="animate-spin" /> : <CloudUpload size={16} />}
            {saving ? "SAVING" : "SAVE"}
          </button>
        </div>
      </div>
    </div>
  );
}

function CopyDeckButton({ mainboard, className }: { mainboard: Mainboard; className?: string }) {
  return (
    <CopyTextButton
      text={() => arenaDeckText(mainboard)}
      label="COPY DECK"
      ariaLabel="Copy deck to clipboard"
      className={className}
    />
  );
}

function DeckEditStatus({ editor, hint }: { editor: DeckEditor; hint: EditHint }) {
  const { status, error } = editor;
  return (
    <div className="flex flex-col items-end gap-2">
      {error && <span className="rounded bg-bg/90 px-2 py-1 font-body text-[13px] text-red">{error}</span>}
      {status === "clean" ? <EditDeckButton hint={hint} /> : <SaveDeckButton status={status} onSave={editor.save} />}
    </div>
  );
}

type EditHint = ReturnType<typeof useEditHint>;

function useEditHint() {
  const [hovered, setHovered] = useState(false);
  const [pinned, setPinned] = useState(false);
  return { hovered, setHovered, pinned, togglePinned: () => setPinned((on) => !on) };
}

function EditDeckButton({ hint }: { hint: EditHint }) {
  const isMobile = useIsMobile();
  return (
    <Tooltip
      label={
        <span className="flex flex-col items-center gap-0.5 text-center">
          <span className="inline-flex items-center gap-1.5">
            Drag cards from Deck
            <ArrowLeftRight size={13} aria-label="to and from" />
            Sideboard
          </span>
          <span className="text-subtle">{isMobile ? "or tap a card to move it" : "or click a card to move it"}</span>
        </span>
      }
      side="top"
      open={isMobile ? hint.pinned : hint.hovered}
      onOpenChange={isMobile ? undefined : hint.setHovered}
    >
      <button
        type="button"
        onClick={hint.togglePinned}
        aria-pressed={hint.pinned}
        className={cn(
          FLOATING_BUTTON_CLASS,
          "bg-surface2/95 hover:border-green/50 hover:text-green cursor-pointer",
          hint.pinned ? "border-green/60 text-green" : "border-border2 text-text",
        )}
        style={{ fontSize: FLOATING_BUTTON_TEXT }}
      >
        <Pencil size={FLOATING_BUTTON_ICON} />
        EDIT
      </button>
    </Tooltip>
  );
}

const FLOATING_BUTTON_CLASS = cn(
  "inline-flex items-center gap-2 rounded-full border px-[18px] py-2.5 shadow-lg shadow-black/60 backdrop-blur-sm",
  "font-display tracking-[0.14em] leading-none transition-colors",
  "outline-none focus:outline-none focus-visible:outline-none",
);
const FLOATING_BUTTON_TEXT = 15;
const FLOATING_BUTTON_ICON = 18;

function SaveDeckButton({ status, onSave }: { status: Exclude<DeckSaveStatus, "clean">; onSave: () => void }) {
  const look = SAVE_BUTTON_LOOKS[status];
  const Icon = look.icon;
  return (
    <Tooltip label={look.tooltip} side="top">
      <span className="inline-flex">
        <button
          type="button"
          onClick={onSave}
          disabled={status !== "dirty"}
          className={cn(FLOATING_BUTTON_CLASS, look.className)}
          style={{ fontSize: FLOATING_BUTTON_TEXT }}
        >
          <Icon size={FLOATING_BUTTON_ICON} className={cn(status === "saving" && "animate-spin")} />
          {look.label}
        </button>
      </span>
    </Tooltip>
  );
}

const SAVE_BUTTON_LOOKS: Record<
  Exclude<DeckSaveStatus, "clean">,
  { label: string; icon: LucideIcon; tooltip: string; className: string }
> = {
  dirty: {
    label: "SAVE",
    icon: CloudUpload,
    tooltip: "Save your changes to this deck",
    className: "bg-green text-black border-green hover:bg-green/85 cursor-pointer",
  },
  saving: {
    label: "SAVING",
    icon: LoaderCircle,
    tooltip: "Saving your changes",
    className: "bg-surface2/95 text-subtle border-border2 cursor-wait",
  },
  saved: {
    label: "SAVED",
    icon: CircleCheck,
    tooltip: "Your changes are saved",
    className: "bg-surface2/95 text-subtle border-border2 opacity-70 cursor-default",
  },
};

function arenaDeckText(mainboard: Mainboard): string {
  const lines = ["Deck", ...mainboard.cards.map((card) => arenaCardLine(card, mainboard.set))];
  if (mainboard.sideboard.length > 0) {
    lines.push("", "Sideboard", ...mainboard.sideboard.map((card) => arenaCardLine(card, mainboard.set)));
  }
  return lines.join("\n");
}

function arenaCardLine(card: DeckCard, deckSet: string | null): string {
  const set = card.set ?? deckSet;
  const line = `${card.count ?? 1} ${card.name}`;
  if (!set || !card.cn) {
    return line;
  }
  return `${line} (${set.toUpperCase()}) ${card.cn}`;
}

function PanelChevron({ side, onClick, href }: { side: "left" | "right"; onClick: () => void; href?: string }) {
  const Chevron = side === "left" ? ChevronLeft : ChevronRight;
  const label = side === "left" ? "Previous deck" : "Next deck";
  const className =
    "shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-full bg-surface2 border border-border text-muted hover:text-text hover:border-border2 transition-colors cursor-pointer outline-none focus:outline-none focus-visible:outline-none";
  const icon = <Chevron size={22} strokeWidth={2.25} />;
  if (href) {
    return (
      <Link to={href} replace onClick={onPlainClick(onClick)} aria-label={label} className={className}>
        {icon}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      aria-label={label}
      className={className}
    >
      {icon}
    </button>
  );
}

function PanelTab({
  active = false,
  onClick,
  href,
  disabled = false,
  icon,
  children,
}: {
  active?: boolean;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}) {
  const className = cn(
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-2 lg:px-4 lg:py-2.5 font-display tracking-[0.14em] leading-none transition-colors",
    "outline-none focus:outline-none focus-visible:outline-none",
    disabled
      ? "bg-surface2 text-subtle border-border opacity-50 cursor-not-allowed"
      : active
        ? "bg-green/15 text-green border-green/50 cursor-pointer"
        : "bg-surface2 text-muted border-border hover:text-text cursor-pointer",
  );
  const content = (
    <>
      <span className="relative inline-flex items-center justify-center">
        {icon}
        {disabled && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 h-[1.5px] w-[150%] -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-full bg-current"
          />
        )}
      </span>
      {children}
    </>
  );
  if (href && !disabled) {
    return (
      <Link
        to={href}
        onClick={onClick ? onPlainClick(onClick) : undefined}
        className={cn(className, "no-underline")}
        style={{ fontSize: 14 }}
      >
        {content}
      </Link>
    );
  }
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      disabled={disabled}
      onClick={onClick}
      className={className}
      style={{ fontSize: 14 }}
    >
      {content}
    </button>
  );
}

type DeckCard = Mainboard["cards"][number];
