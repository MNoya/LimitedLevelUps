import type { CSSProperties, ReactNode } from "react";
import { ArrowRight, Check, Trophy, X } from "lucide-react";

import { cn } from "../../../lib/utils";
import { TROPHY_RECORD, type TrophyRecord } from "../../../data/trophyMage";

const CHIP = "flex items-center gap-1 whitespace-nowrap px-2 pt-1.5 pb-1 font-display leading-none";
const FRAME = "flex shrink-0 items-stretch border-2 border-[color:var(--px-ink)] shadow-[2px_2px_0_#05070a]";
const GOLD = "bg-[linear-gradient(180deg,#fff3cf,#f6c95e_45%,#cf8e2c)] text-[#1a120b]";
const ICE = "bg-[color:var(--px-accent)] text-[color:var(--px-ink)]";
const GREEN = "bg-green text-[#0b1a10]";
const RED = "bg-red text-[#1a0b0b]";

export function CallTag({ record, className }: { record: TrophyRecord; className?: string }) {
  return (
    <span className={cn(FRAME, className)}>
      <span className={cn(CHIP, ICE)}>
        <RecordText record={record} />
      </span>
    </span>
  );
}

export function TruthTag({ record, className }: { record: TrophyRecord; className?: string }) {
  return (
    <span className={cn("flex shrink-0 items-stretch border-2 border-[color:var(--px-ink)]", className)}>
      <span className={cn(CHIP, record === TROPHY_RECORD ? GOLD : "bg-[#3a4458] text-text")}>
        <RecordText record={record} />
      </span>
    </span>
  );
}

export function ResultTag({
  call,
  actual,
  style,
  className,
}: {
  call: TrophyRecord | null;
  actual: TrophyRecord;
  style?: CSSProperties;
  className?: string;
}) {
  if (call === actual) {
    return (
      <span className={cn(FRAME, "animate-stamp", className)} style={style}>
        <span className={cn(CHIP, actual === TROPHY_RECORD ? GOLD : GREEN)}>
          <RecordText record={call} />
          <Check className="size-[0.9em]" strokeWidth={4} />
        </span>
      </span>
    );
  }
  if (!call) {
    return (
      <span className={cn("flex items-center animate-stamp", className)} style={style}>
        <TruthTag record={actual} />
      </span>
    );
  }
  return (
    <span className={cn("flex items-center gap-1.5 animate-stamp", className)} style={style}>
      <span className={FRAME}>
        <span className={cn(CHIP, RED)}>
          <RecordText record={call} />
          <X className="size-[0.9em]" strokeWidth={4} />
        </span>
      </span>
      <ArrowRight className="size-[0.9em] shrink-0 text-subtle" strokeWidth={3} />
      <TruthTag record={actual} />
    </span>
  );
}

export function RecordText({ record }: { record: TrophyRecord }): ReactNode {
  return (
    <>
      {record}
      {record === TROPHY_RECORD && <Trophy className="size-[0.85em]" strokeWidth={3} />}
    </>
  );
}
