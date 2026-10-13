import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNow } from "../../lib/countdown";
import { Search } from "lucide-react";
import { cn } from "../../lib/utils";
import { viewerTimeZoneAbbr } from "../../lib/podSlots";
import { useFantasyEvent } from "./fantasyEvents";
import { formatRemaining } from "../p0p1/Countdown";
import playerStats from "../../data/fantasyPlayerStats.json";

export type FieldPlayer = {
  id?: number;
  firstName: string;
  lastName: string;
  country: string;
  countryCode: string | null;
  sources: string[];
  photoUrl: string | null;
  photoSource: "melee" | "magicgg" | "magicgg-face" | "x" | "other" | null;
};

export type SlotKey = "captain" | "drafter" | "constructed" | "player";

export type Slot = {
  key: SlotKey;
  label: string;
  accent: string;
  special: boolean;
};

export type Qualification = "worlds" | "proTour" | "points" | "regional" | "arena" | "mocs";

export type MatchRecord = {
  wins: number;
  losses: number;
  draws: number;
};

export type RecentStats = {
  events: number;
  day2s: number;
  top8s: number;
  trophyDrafts: number;
  limited: MatchRecord;
  constructed: MatchRecord;
  dayOne: MatchRecord;
  dayTwo: MatchRecord;
};

export type CareerStats = {
  proTours: number | null;
  ptTop8s: number | null;
  ptWins: number | null;
  worldsTop8s: number | null;
  worldsWins: number | null;
  gpTop8s: number | null;
  topFinishes: number | null;
  regionalTop8s: number | null;
  hallOfFameYear: number | null;
  proRecord: MatchRecord | null;
  proRecordSince: string | null;
  eloId: string | null;
  mtgwikiPage: string | null;
};

export type PlayerStats = { recent: RecentStats; career: CareerStats };

export type Lineup = Partial<Record<SlotKey, FieldPlayer>>;

export const SLOTS: Slot[] = [
  { key: "captain", label: "Captain", accent: "#f5c542", special: true },
  { key: "drafter", label: "Drafter", accent: "#2ee85c", special: true },
  { key: "constructed", label: "Constructed", accent: "#4fb8ff", special: true },
  { key: "player", label: "Player", accent: "#a98eff", special: false },
];

export const QUALIFICATION_LABEL: Record<Qualification, string> = {
  worlds: "Worlds 31 Top 8",
  proTour: "Pro Tour",
  points: "Points",
  arena: "Arena Championship",
  mocs: "MOCS Showcase",
  regional: "Regional Championship",
};

export const QUALIFICATION_ORDER = Object.keys(QUALIFICATION_LABEL) as Qualification[];


export type EventHeader = { title: string; city: string; setCode: string };



export function useLineupPicker() {
  const [lineup, setLineup] = useState<Lineup>({});
  const [activeSlot, setActiveSlot] = useState<SlotKey | null>("captain");

  const pickedSlotByName = useMemo(() => {
    const byName = new Map<string, SlotKey>();
    for (const slot of SLOTS) {
      const player = lineup[slot.key];
      if (player) {
        byName.set(fullName(player), slot.key);
      }
    }
    return byName;
  }, [lineup]);

  const assign = (player: FieldPlayer, slotKey: SlotKey | null = activeSlot) => {
    if (!slotKey) {
      return;
    }
    const next = { ...lineup, [slotKey]: player };
    setLineup(next);
    setActiveSlot(SLOTS.find((slot) => !next[slot.key])?.key ?? null);
  };

  const clear = (slotKey: SlotKey) => {
    const next = { ...lineup };
    delete next[slotKey];
    setLineup(next);
    setActiveSlot(slotKey);
  };

  const toggle = (player: FieldPlayer) => {
    const currentSlot = pickedSlotByName.get(fullName(player));
    if (currentSlot) {
      clear(currentSlot);
      return;
    }
    assign(player);
  };

  return {
    lineup,
    setLineup,
    activeSlot,
    setActiveSlot,
    pickedSlotByName,
    assign,
    toggle,
    clear,
    filledCount: Object.keys(lineup).length,
  };
}

export function useFieldFilters(field: FieldPlayer[]) {
  const [search, setSearch] = useState("");
  const [qualification, setQualification] = useState<Qualification | null>(null);

  const players = useMemo(() => {
    const query = normalizeSearch(search);
    const matching = field.filter((player) => {
      const matchesSearch = !query || normalizeSearch(`${fullName(player)} ${player.country}`).includes(query);
      const matchesQualification = !qualification || qualificationOf(player) === qualification;
      return matchesSearch && matchesQualification;
    });
    return matching.sort((a, b) => a.lastName.localeCompare(b.lastName));
  }, [field, search, qualification]);

  return { players, search, setSearch, qualification, setQualification };
}

export function PlayerPortrait({
  player,
  initialsSize,
  wide = false,
}: {
  player: FieldPlayer;
  initialsSize: number;
  wide?: boolean;
}) {
  if (player.photoUrl) {
    const stagePhoto = player.photoSource === "magicgg";
    const framing = stagePhoto
      ? wide
        ? "scale-[1.7] object-[50%_20%] origin-[50%_20%]"
        : "scale-[1.8] origin-[50%_28%]"
      : wide
        ? "object-[50%_30%]"
        : "object-top";
    return (
      <img
        src={player.photoUrl}
        alt={fullName(player)}
        loading="lazy"
        className={cn("w-full h-full object-cover", framing)}
      />
    );
  }
  return (
    <span className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface2 to-border">
      <span className="font-display text-subtle tracking-[0.08em]" style={{ fontSize: initialsSize }}>
        {initialsOf(player)}
      </span>
    </span>
  );
}

export function CountryFlag({ code, width = 18 }: { code: string | null; width?: number }) {
  const height = Math.round(width * (2 / 3));
  if (!code) {
    return (
      <span
        className="shrink-0 flex items-center justify-center overflow-hidden bg-[#4a5468]"
        style={{ width, height }}
        title="Country not listed"
      >
        <i className="ms ms-planeswalker text-white" style={{ fontSize: Math.max(height, 9), lineHeight: 1 }} />
      </span>
    );
  }
  return (
    <img
      src={`https://flagcdn.com/w40/${code.toLowerCase()}.png`}
      alt=""
      className="object-cover shrink-0"
      style={{ width, height }}
    />
  );
}

export function QualificationChips({
  active,
  onChange,
  players,
}: {
  active: Qualification | null;
  onChange: (value: Qualification | null) => void;
  players: FieldPlayer[];
}) {
  const options = QUALIFICATION_ORDER;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {options.map((option) => {
        const on = active === option;
        return (
          <button
            key={option}
            type="button"
            onClick={() => onChange(on ? null : option)}
            className={cn(
              "px-2 py-1 border text-[13px] whitespace-nowrap cursor-pointer transition-colors",
              on ? "border-green/60 bg-green/10 text-text" : "border-border2 bg-surface text-subtle hover:text-text",
            )}
          >
            {qualificationLabel(option, players)}
          </button>
        );
      })}
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  className,
  placeholder = "Search players or countries...",
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
}) {
  const searching = value.trim() !== "";
  return (
    <div className={cn("relative w-[240px]", className)}>
      <Search
        size={15}
        className={cn(
          "absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none transition-colors",
          searching ? "text-green" : "text-muted",
        )}
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "w-full bg-surface border pl-8 pr-2.5 py-1.5 text-text text-[14px] placeholder:text-muted outline-none focus:border-green/60 transition-colors",
          searching ? "border-green" : "border-border2",
        )}
      />
    </div>
  );
}

export function PicksCountdown({ size, compact = false }: { size: number; compact?: boolean }) {
  const now = useNow(30_000);
  const remaining = useFantasyEvent().picksLockAt.getTime() - now;
  return (
    <span style={{ fontSize: size }}>
      {remaining > 0 ? (
        <>
          <span className="text-subtle">Closes in </span>
          <span className="text-green">{formatRemaining(remaining, compact)}</span>
        </>
      ) : (
        <span className="text-subtle">Picks are closed</span>
      )}
    </span>
  );
}

export function PicksLockDate({ size, prefix, at }: { size: number; prefix?: string; at: Date }) {
  const day = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(at);
  const minute = at.getMinutes() === 0 ? undefined : "2-digit";
  const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute }).format(at);
  return (
    <span style={{ fontSize: size }}>
      {prefix ? <span className="text-subtle">{prefix} </span> : null}
      <span className="font-semibold text-text">{day}</span>
      <span className="text-subtle"> at </span>
      <span className="text-green">{time}</span>
      <span className="text-subtle"> {viewerTimeZoneAbbr()}</span>
    </span>
  );
}

export function FitText({ text, maxSize, minSize = 9 }: { text: string; maxSize: number; minSize?: number }) {
  const boxRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const [fontSize, setFontSize] = useState(maxSize);

  useLayoutEffect(() => {
    const box = boxRef.current;
    const label = textRef.current;
    if (!box || !label) {
      return;
    }
    const fit = () => {
      let size = maxSize;
      label.style.fontSize = `${size}px`;
      while (size > minSize && label.getBoundingClientRect().width > box.clientWidth) {
        size -= 0.5;
        label.style.fontSize = `${size}px`;
      }
      setFontSize(size);
    };
    fit();
    document.fonts.ready.then(fit);
    const observer = new ResizeObserver(fit);
    observer.observe(box);
    return () => observer.disconnect();
  }, [text, maxSize, minSize]);

  return (
    <span ref={boxRef} className="block w-full overflow-hidden text-ellipsis whitespace-nowrap font-semibold">
      <span ref={textRef} style={{ fontSize }}>
        {text}
      </span>
    </span>
  );
}

export function fullName(player: FieldPlayer): string {
  return `${player.firstName} ${player.lastName}`.trim();
}

export function playerSlug(player: FieldPlayer): string {
  return normalizeSearch(fullName(player)).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function shortLastName(player: FieldPlayer): string {
  const surnameParticles = new Set(["de", "del", "della", "di", "da", "dos", "van", "von", "le", "la", "du", "mac"]);
  const familyNameFirstCountries = new Set(["Hong Kong", "China", "Chinese Taipei", "Taiwan", "Korea", "South Korea"]);
  if (!player.lastName.trim()) {
    return player.firstName;
  }
  const words = player.lastName.trim().split(/\s+/);
  const startsWithParticle = surnameParticles.has(words[0].toLowerCase());
  const familyNameFirst = familyNameFirstCountries.has(player.country);
  if (words.length === 1 || startsWithParticle || familyNameFirst) {
    return player.lastName;
  }
  return words[0];
}

export function cardName(player: FieldPlayer): string {
  if (!player.lastName.trim()) {
    return player.firstName;
  }
  const firstWord = player.firstName.trim().split(/\s+/)[0];
  return `${firstWord} ${shortLastName(player)}`.trim();
}

function initialsOf(player: FieldPlayer): string {
  return `${player.firstName.charAt(0)}${player.lastName.charAt(0)}`.toUpperCase();
}

export function slotFor(key: SlotKey): Slot {
  const slot = SLOTS.find((s) => s.key === key);
  if (!slot) {
    throw new Error(`Unknown slot ${key}`);
  }
  return slot;
}

export function qualificationLabel(qualification: Qualification, players: FieldPlayer[]): string {
  if (qualification !== "worlds") {
    return QUALIFICATION_LABEL[qualification];
  }
  for (const player of players) {
    const match = player.sources.join(" ").match(WORLDS_TOP_8);
    if (match) {
      return `Worlds ${match[1]} Top 8`;
    }
  }
  return QUALIFICATION_LABEL.worlds;
}

const WORLDS_TOP_8 = /World Championship (\d+) Top 8/;

export function qualificationOf(player: FieldPlayer): Qualification {
  const sources = player.sources.join(" ");
  if (WORLDS_TOP_8.test(sources)) {
    return "worlds";
  }
  if (sources.includes("Match Points or Top 8")) {
    return "proTour";
  }
  if (sources.includes("Arena Championship")) {
    return "arena";
  }
  if (sources.includes("MOCS")) {
    return "mocs";
  }
  if (sources.includes("Regional Championship")) {
    return "regional";
  }
  return "points";
}

export function statsFor(player: FieldPlayer): PlayerStats | undefined {
  return (playerStats as Record<string, PlayerStats>)[fullName(player)];
}

export function formatRecord(record: MatchRecord): string {
  const winsAndLosses = `${record.wins}-${record.losses}`;
  if (record.draws === 0) {
    return winsAndLosses;
  }
  return `${winsAndLosses}-${record.draws}`;
}

export function normalizeSearch(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}
