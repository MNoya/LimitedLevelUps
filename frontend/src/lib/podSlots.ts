// Mirrors WEEKDAY_BUCKETS in bot/services/pod_signals.py
export const POD_SLOTS = [
  { label: "EARLY POD", easternHour: 14 },
  { label: "LATE POD", easternHour: 20 },
] as const;

export function easternHourLabel(hour: number): string {
  const twelve = hour % 12 || 12;
  return `${twelve} ${hour < 12 ? "AM" : "PM"}`;
}

export function easternHourInLocalTime(hour: number): string {
  return formatLocalTime(podSlotInstant(hour).toISOString());
}

export function podSlotInstant(hour: number, base: Date = new Date()): Date {
  const asIfUtc = Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), base.getUTCDate(), hour);
  return new Date(asIfUtc + easternOffsetMs(asIfUtc));
}

export function nextPodSlotInstant(hour: number): Date {
  const today = podSlotInstant(hour);
  if (today.getTime() > Date.now()) {
    return today;
  }
  const tomorrow = new Date();
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  return podSlotInstant(hour, tomorrow);
}

const EASTERN_CLOCK = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour12: false,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatLocalTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const minute = d.getMinutes() === 0 ? undefined : "2-digit";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute }).format(d);
}

function easternOffsetMs(atMs: number): number {
  const parts = EASTERN_CLOCK.formatToParts(new Date(atMs));
  const value = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const eastern = Date.UTC(value("year"), value("month") - 1, value("day"), value("hour"), value("minute"));
  return atMs - eastern;
}
