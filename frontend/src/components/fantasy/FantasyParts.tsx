import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { SetGlyph } from "../Brand";
import { FilterDropdown } from "../FilterDropdown";
import { ChevronDown } from "../Icons";
import {
  FANTASY_EVENTS,
  eventDays,
  fantasyEventPath,
  switcherTag,
  type FantasyEventEntry,
} from "./fantasyEvents";
import { SectionLabel } from "../SectionLabel";
import { cn } from "../../lib/utils";
import { CountryFlag, PlayerPortrait, fullName, slotFor, type EventHeader, type FieldPlayer, type SlotKey } from "./fantasyField";

export type HoverTarget = { player: FieldPlayer; rect: DOMRect };

export function EventTitle({
  event,
  label = "shown",
  switcher,
  labelSize,
  glyphSize,
  titleSize,
  citySize,
  className,
  crest,
  crestRaised = false,
  balanced = true,
  children,
}: {
  event: EventHeader;
  label?: "shown" | "hidden" | "removed";
  switcher?: ReactNode;
  crest?: ReactNode;
  crestRaised?: boolean;
  balanced?: boolean;
  children?: ReactNode;
  labelSize: number;
  glyphSize: number;
  titleSize: number;
  citySize: number;
  className?: string;
}) {
  return (
    <span
      className={cn("grid items-end gap-x-3", balanced ? "grid-cols-[1fr_auto_1fr]" : "grid-cols-[auto_auto_auto]", className)}
    >
      {label === "removed" ? null : (
        <SectionLabel
          size={labelSize}
          color="#b8c0d0"
          className={cn("col-start-2 text-center mb-1", label === "hidden" && "invisible")}
        >
          FANTASY MAGIC
        </SectionLabel>
      )}
      <span className={cn("col-start-1 row-start-2 flex justify-end self-center", balanced ? "-mr-2" : "-mr-1")}>
        <span className="relative flex">
          {crest ? (
            <span
              className={cn("absolute right-full top-1/2 mr-2 pointer-events-none", crestRaised ? "-translate-y-[70%]" : "-translate-y-[60%]")}
            >
              {crest}
            </span>
          ) : null}
          <SetGlyph code={event.setCode} size={glyphSize} />
        </span>
      </span>
      <span
        className="col-start-2 row-start-2 font-display tracking-[0.04em] text-text text-center whitespace-nowrap"
        style={{ fontSize: titleSize, lineHeight: 0.9 }}
      >
        {event.title}
      </span>
      <span className="col-start-3 row-start-2 justify-self-start flex items-end gap-1.5">
        <span
          className="text-left font-display text-subtle tracking-[0.06em] whitespace-nowrap"
          style={{ fontSize: citySize, lineHeight: 1 }}
        >
          {event.city}
        </span>
        {switcher}
      </span>
      {children}
    </span>
  );
}

export function EventCrest({
  src,
  alt,
  height,
  className,
}: {
  src: string;
  alt: string;
  height: number;
  className?: string;
}) {
  return <img src={src} alt={alt} className={cn("shrink-0 max-w-none w-auto", className)} style={{ height }} />;
}

export function EventSwitcher({ activeCode, mobile = false }: { activeCode: string; mobile?: boolean }) {
  const options = FANTASY_EVENTS.map((event) => ({ value: event.code, label: event.name }));
  const eventByCode = new Map(FANTASY_EVENTS.map((event) => [event.code, event]));
  const now = new Date();
  return (
    <FilterDropdown
      value={activeCode}
      options={options}
      variant={mobile ? "mobile" : "desktop"}
      mobileCentered
      hrefFor={(code) => fantasyEventPath(eventByCode.get(code) as FantasyEventEntry)}
      renderOption={(option) => {
        const event = eventByCode.get(option.value) as FantasyEventEntry;
        const tag = switcherTag(event, now);
        return (
          <span className="flex w-full min-w-0 items-center gap-2.5">
            <SetGlyph code={event.setCode} size={24} />
            <span className="flex flex-col min-w-0">
              <span className="font-display text-[18px] tracking-[0.04em] leading-none">{event.shortName.toUpperCase()}</span>
              <span className="text-[12px] text-subtle truncate">
                {event.city} {eventDays(event, now)}
              </span>
            </span>
            {tag ? (
              <span
                className={cn("ml-auto pl-3 shrink-0 text-[13px] tracking-[0.18em]", tag === "LIVE" && "text-green")}
                style={tag === "NEXT UP" ? { color: "#cca54e" } : undefined}
              >
                {tag}
              </span>
            ) : null}
          </span>
        );
      }}
      renderTrigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={toggle}
          aria-label="Switch event"
          className="flex items-center justify-center w-6 h-6 -mb-0.5 border border-border2 bg-surface text-subtle hover:text-text hover:bg-surface2 cursor-pointer transition-colors"
        >
          <ChevronDown strokeWidth={2.5} className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
        </button>
      )}
    />
  );
}

export function FieldTile({
  player,
  detail,
  aside,
  pickedSlot = null,
  replacedSlot = null,
  showSlotTag = false,
  out = false,
  faded = false,
  large = false,
  href,
  onClick,
  onLongPress,
  onHover,
  onLeave,
}: {
  player: FieldPlayer;
  detail: ReactNode;
  aside?: ReactNode;
  pickedSlot?: SlotKey | null;
  replacedSlot?: SlotKey | null;
  showSlotTag?: boolean;
  out?: boolean;
  faded?: boolean;
  large?: boolean;
  href?: string;
  onClick?: () => void;
  onLongPress?: () => void;
  onHover: (element: HTMLElement) => void;
  onLeave: () => void;
}) {
  const tagSlotKey = pickedSlot ?? replacedSlot;
  const slot = tagSlotKey ? slotFor(tagSlotKey) : undefined;
  const slotTag = slot && replacedSlot ? `${slot.label.toUpperCase()}-DAY 1` : slot?.label.toUpperCase();
  const longPress = useLongPress(() => onLongPress?.());
  const className = cn(
    "relative flex items-center border bg-surface cursor-pointer transition-colors text-left min-w-0 select-none no-underline text-text [-webkit-touch-callout:none]",
    large ? "gap-3 pr-3 min-h-[64px]" : "gap-2.5 pr-2 min-h-[48px]",
    !slot && "border-border hover:border-border2 hover:bg-surface2",
    out && "opacity-45",
  );
  const body = (
    <>
      {slot && showSlotTag ? (
        <span
          className="absolute -top-[10px] right-2 px-1 bg-bg font-display text-[13px] leading-none [text-box:trim-both_cap_alphabetic] py-[2px] tracking-[0.12em]"
          style={{ color: slot.accent }}
        >
          {slotTag}
        </span>
      ) : null}
      <span
        className={cn(
          "relative self-stretch shrink-0 overflow-hidden bg-surface2",
          large ? "w-16" : "w-12",
          out && "grayscale",
          faded && "opacity-60",
        )}
      >
        <span className="absolute inset-0">
          <PlayerPortrait player={player} initialsSize={large ? 20 : 16} />
        </span>
      </span>
      <span className="flex-1 min-w-0 flex flex-col gap-0.5">
        <span className="flex items-baseline justify-between gap-2">
          <span className={cn("font-semibold leading-tight line-clamp-2", large ? "text-[15px]" : "text-[13px]")}>
            {fullName(player)}
          </span>
          {aside}
        </span>
        <span className={cn("flex items-center gap-1.5 text-subtle min-w-0", large ? "text-[13px]" : "text-[12px]")}>
          <CountryFlag code={player.countryCode} width={large ? 18 : 14} />
          {detail}
        </span>
      </span>
    </>
  );
  if (href) {
    return (
      <Link
        to={href}
        state={{ fromList: true }}
        onMouseEnter={(event) => onHover(event.currentTarget)}
        onMouseLeave={onLeave}
        className={className}
      >
        {body}
      </Link>
    );
  }
  return (
    <button
      data-fantasy-pick-target
      type="button"
      onClick={() => {
        if (!longPress.consumeFired()) {
          onClick?.();
        }
      }}
      onMouseEnter={(event) => onHover(event.currentTarget)}
      onMouseLeave={onLeave}
      onTouchStart={longPress.start}
      onTouchEnd={longPress.cancel}
      onTouchMove={longPress.cancel}
      onContextMenu={(event) => {
        event.preventDefault();
        onLongPress?.();
      }}
      className={className}
      style={slot ? { borderColor: slot.accent, background: `${slot.accent}14` } : undefined}
    >
      {body}
    </button>
  );
}

export function HoverCard({ target, children }: { target: HoverTarget; children: ReactNode }) {
  const width = 350;
  const gap = 12;
  const fitsRight = target.rect.right + gap + width < window.innerWidth;
  const left = fitsRight ? target.rect.right + gap : target.rect.left - gap - width;
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardHeight, setCardHeight] = useState(0);
  useLayoutEffect(() => {
    setCardHeight(cardRef.current?.offsetHeight ?? 0);
  }, [target, children]);
  const viewportMargin = 8;
  const top = Math.max(Math.min(target.rect.top - 40, window.innerHeight - cardHeight - viewportMargin), viewportMargin);
  return (
    <div
      ref={cardRef}
      className="fixed z-40 border border-border2 bg-surface p-4 shadow-2xl pointer-events-none animate-fadeIn"
      style={{ width, left, top, visibility: cardHeight ? "visible" : "hidden" }}
    >
      {children}
    </div>
  );
}

export function ProfileHint({ rightClick }: { rightClick: boolean }) {
  return (
    <p className="m-0 mt-3 text-center text-[13px] italic text-subtle">
      {rightClick ? "Right click for full Player Profile" : "Click for full Player Profile"}
    </p>
  );
}

export function useHoverTarget(disabled: boolean) {
  const [hoverTarget, setHoverTarget] = useState<HoverTarget | null>(null);
  const hoverTimer = useRef<number | null>(null);

  useEffect(() => () => clearHoverTimer(hoverTimer), []);

  const onHover = (player: FieldPlayer, element: HTMLElement) => {
    if (disabled) {
      return;
    }
    clearHoverTimer(hoverTimer);
    hoverTimer.current = window.setTimeout(() => setHoverTarget({ player, rect: element.getBoundingClientRect() }), 350);
  };

  const onLeave = () => {
    clearHoverTimer(hoverTimer);
    setHoverTarget(null);
  };

  return { hoverTarget, onHover, onLeave };
}

export function useLongPress(onLongPress: () => void) {
  const timer = useRef<number | null>(null);
  const fired = useRef(false);
  return {
    start: () => {
      fired.current = false;
      timer.current = window.setTimeout(() => {
        fired.current = true;
        onLongPress();
      }, 450);
    },
    cancel: () => clearHoverTimer(timer),
    consumeFired: () => {
      const wasFired = fired.current;
      fired.current = false;
      return wasFired;
    },
  };
}

function clearHoverTimer(timer: { current: number | null }) {
  if (timer.current !== null) {
    window.clearTimeout(timer.current);
    timer.current = null;
  }
}
