import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Check, X } from "lucide-react";
import { TbQuestionMark } from "../Icons";
import { ScoreCell, TrophyCell } from "../LeaderboardTable";
import { SeatAvatar } from "../pod/PodStandingRow";
import { cn } from "../../lib/utils";
import { playerPath } from "../../data/utils";
import {
  formatChampionshipDay,
  type ChampionshipEntrant,
  type ChampionshipRsvp,
} from "../../data/setChampionship";

export function QualificationList({
  entrants,
  seated,
  frozenAt,
  setCode,
  compact = false,
}: {
  entrants: ChampionshipEntrant[];
  seated: ChampionshipEntrant[];
  frozenAt: string | null;
  setCode: string;
  compact?: boolean;
}) {
  const frozen = frozenAt !== null;
  const seatedKeys = new Set(seated.map(entrantKey));
  const rows = withWildcardUnderSeats(entrants, seatedKeys);
  const columns = qualificationColumns(frozen, compact);
  return (
    <div className="flex flex-col border border-border bg-surface">
      <div
        className={cn(
          "relative grid items-center gap-x-3 h-[40px] px-3",
          "bg-surface2 border-b border-border shrink-0",
        )}
        style={{ gridTemplateColumns: columns }}
      >
        <span className="col-span-2 pl-[22px] font-display text-[16px] tracking-[0.14em] leading-none text-text">
          {frozen ? "FROZEN STANDINGS" : "LIVE STANDINGS"}
        </span>
        {frozenAt && !compact ? (
          <span className="absolute left-1/2 -translate-x-1/2 text-[13px] text-subtle">
            {formatChampionshipDay(frozenAt)}
          </span>
        ) : null}
        <HeadingLabel>{compact ? "TR" : "TROPHIES"}</HeadingLabel>
        <HeadingLabel className="translate-x-3">POINTS</HeadingLabel>
        {frozen ? <HeadingLabel>RSVP</HeadingLabel> : null}
      </div>
      <div className="flex flex-col gap-[1px] bg-bg">
        {rows.map((entrant) => (
          <QualificationRow
            key={entrantKey(entrant)}
            entrant={entrant}
            seated={seatedKeys.has(entrantKey(entrant))}
            frozen={frozen}
            setCode={setCode}
            columns={columns}
            compact={compact}
          />
        ))}
      </div>
    </div>
  );
}

function QualificationRow({
  entrant,
  seated,
  frozen,
  setCode,
  columns,
  compact,
}: {
  entrant: ChampionshipEntrant;
  seated: boolean;
  frozen: boolean;
  setCode: string;
  columns: string;
  compact: boolean;
}) {
  const name = (
    <span className="flex items-center gap-2.5 min-w-0">
      <SeatAvatar name={entrant.displayName} avatarUrl={entrant.avatarUrl} size={28} teamSide={null} />
      <span className="font-display text-[16px] leading-none tracking-[0.04em] truncate">
        {entrant.displayName.toUpperCase()}
      </span>
      {entrant.wildcard ? (
        <span className="shrink-0 ml-4 font-display text-[16px] leading-none tracking-[0.04em] text-gold">
          POD WILDCARD
        </span>
      ) : null}
    </span>
  );
  return (
    <div
      className={cn(
        "relative grid items-center gap-x-3 py-2.5 px-3 bg-surface",
        seated && "bg-green/10",
      )}
      style={{ gridTemplateColumns: columns }}
    >
      {seated ? <span aria-hidden="true" className="absolute left-0 inset-y-0 w-[3px] bg-green" /> : null}
      <span className={cn("font-num text-center tabular-nums text-[13px]", seated ? "text-green" : "text-muted")}>
        {entrant.rank === Number.MAX_SAFE_INTEGER ? "" : entrant.rank}
      </span>
      {entrant.slug ? (
        <Link
          to={playerPath(entrant.slug, setCode)}
          className="flex min-w-0 no-underline text-text hover:text-green transition-colors"
        >
          {name}
        </Link>
      ) : (
        <span className="flex min-w-0 text-text">{name}</span>
      )}
      <span className="flex justify-center">
        <TrophyCell trophies={entrant.trophies ?? 0} compact={compact} />
      </span>
      <span className="flex justify-center translate-x-3">
        <ScoreCell score={entrant.score} large={!compact} />
      </span>
      {frozen ? <RsvpCell rsvp={entrant.rsvp} /> : null}
    </div>
  );
}

function RsvpCell({ rsvp }: { rsvp: ChampionshipRsvp | null }) {
  return <span className="flex items-center justify-center">{rsvpIcon(rsvp)}</span>;
}

function rsvpIcon(rsvp: ChampionshipRsvp | null): ReactNode {
  if (rsvp === "yes") {
    return <Check size={18} className="text-green" aria-label="Yes" />;
  }
  if (rsvp === "no") {
    return <X size={18} className="text-muted" aria-label="No" />;
  }
  if (rsvp === "maybe") {
    return <TbQuestionMark size={18} className="text-subtle" aria-label="Maybe" />;
  }
  return <span className="text-[13px] text-dim">—</span>;
}

function HeadingLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "flex justify-center font-display text-[12px] tracking-[0.16em] leading-none text-muted whitespace-nowrap",
        className,
      )}
    >
      {children}
    </span>
  );
}

function qualificationColumns(frozen: boolean, compact: boolean): string {
  const statColumn = compact ? "44px" : "64px";
  const base = `${compact ? "30px" : "44px"} 1fr ${statColumn} ${statColumn}`;
  return frozen ? `${base} ${statColumn}` : base;
}

function withWildcardUnderSeats(entrants: ChampionshipEntrant[], seatedKeys: Set<string>): ChampionshipEntrant[] {
  const wildcard = entrants.find((entrant) => entrant.wildcard && seatedKeys.has(entrantKey(entrant)));
  if (!wildcard) {
    return entrants;
  }
  const rest = entrants.filter((entrant) => entrant !== wildcard);
  let insertAt = 0;
  rest.forEach((entrant, index) => {
    if (seatedKeys.has(entrantKey(entrant))) {
      insertAt = index + 1;
    }
  });
  return [...rest.slice(0, insertAt), wildcard, ...rest.slice(insertAt)];
}

function entrantKey(entrant: ChampionshipEntrant): string {
  return entrant.slug ?? entrant.displayName;
}
