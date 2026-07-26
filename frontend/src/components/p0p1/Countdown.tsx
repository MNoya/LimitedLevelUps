import { p0p1Now } from "../../data/p0p1DevState";
import type { P0P1Phase } from "../../data/p0p1Results";
import { useNow } from "../../lib/countdown";

export function pluralizeUnit(value: number, unit: string) {
  return `${value} ${unit}${value === 1 ? "" : "s"}`;
}

export function formatRemaining(diff: number): string {
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const minutes = Math.floor((diff / (1000 * 60)) % 60);
  if (days > 0) {
    return `${pluralizeUnit(days, "day")}, ${pluralizeUnit(hours, "hour")}`;
  }
  if (hours > 0) {
    return `${pluralizeUnit(hours, "hour")}, ${pluralizeUnit(minutes, "minute")}`;
  }
  return pluralizeUnit(minutes, "minute");
}

export function formatScoringRemaining(diff: number): string {
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days >= 2) {
    return pluralizeUnit(days, "day");
  }
  const totalHours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff / (1000 * 60)) % 60);
  if (totalHours > 0) {
    return `${pluralizeUnit(totalHours, "hour")}, ${pluralizeUnit(minutes, "minute")}`;
  }
  return pluralizeUnit(minutes, "minute");
}

export function P0P1Countdown({
  deadline,
  scoringDate,
  size = 13,
  phase,
}: {
  deadline: Date;
  scoringDate?: Date;
  size?: number;
  phase: P0P1Phase;
}) {
  useNow(30_000);
  const now = p0p1Now();
  const deadlineDiff = deadline.getTime() - now;

  if (phase === "voting") {
    return (
      <span className="whitespace-nowrap" style={{ fontSize: size }}>
        <span className="text-muted">Closes in </span>
        <span className="text-green">{formatRemaining(deadlineDiff)}</span>
      </span>
    );
  }

  if (phase === "final") {
    return (
      <span className="text-green" style={{ fontSize: size }}>
        Results are in!
      </span>
    );
  }

  if (phase === "finalizing") {
    return (
      <span className="text-green" style={{ fontSize: size }}>
        Finalizing results
      </span>
    );
  }

  if (scoringDate) {
    const scoringDiff = scoringDate.getTime() - now;
    if (scoringDiff > 0) {
      return (
        <span className="whitespace-nowrap" style={{ fontSize: size }}>
          <span className="text-muted">Results in </span>
          <span className="text-green">{formatScoringRemaining(scoringDiff)}</span>
        </span>
      );
    }
  }

  return (
    <span className="text-muted" style={{ fontSize: size }}>
      Entries have closed
    </span>
  );
}
