import { useState } from "react";

import { FIRST_PICK_POINTS, WHEEL_CARD_POINTS, WHEEL_GAME_ART } from "../../../data/draftGames";
import { GameHelpDialog, HelpScoreRow, HelpSection, HelpSteps, type GameHelpAction } from "../GameDialog";
import { cn } from "../../../lib/utils";
import { ACCENT_BUTTON } from "../pixelStyles";
import { CallChipFace } from "./PackGrid";
import { WheelEmoji } from "./WheelEmoji";

const HELP_CHIP = "flex text-[19px]";

export function WheelHelpDialog({
  open,
  onClose,
  action,
  touchVerb,
}: {
  open: boolean;
  onClose: () => void;
  action?: GameHelpAction;
  touchVerb: string;
}) {
  return (
    <GameHelpDialog
      open={open}
      onClose={onClose}
      action={action}
      art={WHEEL_GAME_ART}
      artPosition="60% 38%"
      icon={<SpinningWheel />}
      playButton={ACCENT_BUTTON}
      footnote="Every pack was pod-drafted on"
    >
      <HelpSection title="Guess the Wheel">
        <HelpSteps
          steps={[
            `${touchVerb} the cards in pick order`,
            "Cards you leave out are your wheel guess",
            "Confirm to reveal what wheeled",
          ]}
        />
      </HelpSection>
      <HelpSection title="Scoring">
        <ul className="grid grid-cols-[auto_auto_1fr] items-center gap-x-3 gap-y-5 pt-2">
          <HelpScoreRow
            plate={
              <span className={HELP_CHIP}>
                <CallChipFace yourIndex={-1} realIndex={-1} outcome="right" still />
              </span>
            }
            points={WHEEL_CARD_POINTS}
          >
            Correct Guess
          </HelpScoreRow>
          <HelpScoreRow
            plate={
              <span className={HELP_CHIP}>
                <CallChipFace yourIndex={0} realIndex={0} outcome="right" still />
              </span>
            }
            points={FIRST_PICK_POINTS}
          >
            Exact First Pick
          </HelpScoreRow>
        </ul>
      </HelpSection>
    </GameHelpDialog>
  );
}

export function QuickHelpDialog({
  open,
  onClose,
  action,
}: {
  open: boolean;
  onClose: () => void;
  action?: GameHelpAction;
}) {
  return (
    <GameHelpDialog
      open={open}
      onClose={onClose}
      action={action}
      title="Quick Mode"
      art={WHEEL_GAME_ART}
      artPosition="60% 38%"
      icon={<SpinningWheel />}
      playButton={ACCENT_BUTTON}
      footnote="Every pack was pod-drafted on"
    >
      <HelpSteps steps={["Each round shows 3 cards from one Pod pack", "Select the card you think wheeled"]} />
      <HelpSection title="Difficulty">
        <ul className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2.5">
          <li className="contents">
            <span className={cn(difficultyKey("easy", "raised"), "h-8 px-3 text-lg")}>{DIFFICULTY_LABEL.easy}</span>
            <span>One picked 1st to 3rd, another 6th to 8th</span>
          </li>
          <li className="contents">
            <span className={cn(difficultyKey("hard", "raised"), "h-8 px-3 text-lg")}>{DIFFICULTY_LABEL.hard}</span>
            <span>Both picked right before the wheel</span>
          </li>
        </ul>
      </HelpSection>
    </GameHelpDialog>
  );
}

export type QuickDifficulty = "easy" | "hard";

export const DIFFICULTY_LABEL: Record<QuickDifficulty, string> = { easy: "Normal", hard: "Hard" };

export type KeyState = "pressed" | "raised" | "framed" | "off";

export function difficultyKey(difficulty: QuickDifficulty, state: KeyState): string {
  const easy = difficulty === "easy";
  const fill = easy ? "bg-[#8fe06a] text-[#0f2408]" : "bg-[#f08a96] text-[#2a0a10]";
  const lip = easy ? "shadow-[inset_0_-3px_0_#3a7d1f]" : "shadow-[inset_0_-3px_0_#93283a]";
  const framedShadow = easy
    ? "shadow-[inset_0_-4px_0_#3a7d1f,5px_5px_0_#05070a]"
    : "shadow-[inset_0_-4px_0_#93283a,5px_5px_0_#05070a]";
  const look: Record<KeyState, string> = {
    pressed: cn("translate-y-[3px] border-b-2", fill, lip),
    raised: cn("border-b-[5px]", fill, lip),
    framed: cn("border-[3px]", fill, framedShadow),
    off: "border-b-[5px] bg-[#fff8e6] text-[#1a120b] shadow-[inset_0_-3px_0_#d9a441]",
  };
  return cn(
    "inline-flex items-center justify-center border-2 border-[#1a120b] font-display leading-none transition-transform",
    look[state],
  );
}

function SpinningWheel() {
  const [spins, setSpins] = useState(0);
  return (
    <button
      type="button"
      aria-label="Spin the wheel"
      onClick={() => setSpins((count) => count + 1)}
      className="cursor-pointer drop-shadow-[2px_2px_0_#05070a] active:scale-95"
    >
      <WheelEmoji spinToken={`help-${spins}`} scale={1.6} />
    </button>
  );
}
