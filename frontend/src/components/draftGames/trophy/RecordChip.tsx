import type { CSSProperties, ReactNode } from "react";
import { ArrowRight, Check, Trophy } from "lucide-react";

import { cn } from "../../../lib/utils";
import { TROPHY_RECORD, type TrophyRecord } from "../../../data/trophyMage";

const CHIP = "flex items-center gap-1.5 whitespace-nowrap px-2.5 pt-1.5 pb-1 font-display leading-none";
const GOLD = "bg-[#f6c95e] text-[#1a120b]";
const GREEN = "bg-green text-[#0b1a10]";
const RED = "bg-red text-[#1a0b0b]";
const SLATE = "bg-[#2b3445] text-text";

export function CallTag({ record, className }: { record: TrophyRecord; className?: string }) {
  return (
    <ChipFrame className={className}>
      <span className={cn(CHIP, GOLD)}>
        <RecordText record={record} />
      </span>
    </ChipFrame>
  );
}

export function RevealChip({
  call,
  actual,
  short = false,
  style,
  className,
}: {
  call: TrophyRecord | null;
  actual: TrophyRecord;
  short?: boolean;
  style?: CSSProperties;
  className?: string;
}) {
  if (!call) {
    return (
      <ChipFrame className={cn("animate-stamp", className)} style={style}>
        <span className={cn(CHIP, actual === TROPHY_RECORD ? GOLD : SLATE)}>
          <RecordText record={actual} />
        </span>
      </ChipFrame>
    );
  }
  if (call === actual) {
    return (
      <ChipFrame className={cn("animate-chipRingFromGold shadow-[0_0_0_1px_#2ee85c]", className)} style={style}>
        <span className={cn(CHIP, GREEN, "animate-chipFillFromGold")} style={style}>
          <RecordText record={call} />
          <Check className="-mt-[0.1em] size-[0.9em] animate-stamp" strokeWidth={4} style={style} />
        </span>
      </ChipFrame>
    );
  }
  if (short) {
    return (
      <ChipFrame className={cn("animate-chipRingFromGold shadow-[0_0_0_1px_#ef4444]", className)} style={style}>
        <span className={cn(CHIP, RED, "animate-chipFillFromGold")} style={style}>
          <RecordText record={actual} />
        </span>
      </ChipFrame>
    );
  }
  return (
    <ChipFrame className={cn("animate-chipRingFromGold shadow-[0_0_0_1px_#ef4444]", className)} style={style}>
      <span className={cn(CHIP, GOLD)}>
        <RecordText record={call} />
      </span>
      <span className="flex items-stretch overflow-hidden animate-chipExtend" style={style}>
        <span className="grid place-items-center bg-[#1a120b] px-1 text-[#f6c95e]">
          <ArrowRight className="size-[0.8em]" strokeWidth={3} />
        </span>
        <span className={cn(CHIP, RED)}>
          <RecordText record={actual} />
        </span>
      </span>
    </ChipFrame>
  );
}

export function RecordText({ record }: { record: TrophyRecord }) {
  return (
    <>
      {record}
      {record === TROPHY_RECORD && <Trophy className="-mt-[0.15em] size-[0.85em]" strokeWidth={3} />}
    </>
  );
}

function ChipFrame({ className, style, children }: { className?: string; style?: CSSProperties; children: ReactNode }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-stretch border-[3px] border-[#1a120b] shadow-[0_0_0_1px_#f6c95e,2px_2px_0_1px_#05070a]",
        className,
      )}
      style={style}
    >
      {children}
    </span>
  );
}
