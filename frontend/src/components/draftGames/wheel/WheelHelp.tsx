import { useState } from "react";

import { FIRST_PICK_POINTS, WHEEL_CARD_POINTS, WHEEL_GAME_ART } from "../../../data/draftGames";
import { GameHelpDialog, HelpScoreRow, HelpSection, HelpSteps } from "../GameDialog";
import { cn } from "../../../lib/utils";
import { GOLD_BUTTON, PIXEL_TAG } from "../pixelStyles";
import { CallChipFace } from "./PackGrid";
import { WheelEmoji } from "./WheelEmoji";

const HELP_CHIP = "flex text-[19px]";

export function WheelHelpDialog({
  open,
  onClose,
  touchVerb,
}: {
  open: boolean;
  onClose: () => void;
  touchVerb: string;
}) {
  return (
    <GameHelpDialog
      open={open}
      onClose={onClose}
      art={WHEEL_GAME_ART}
      artPosition="60% 38%"
      icon={<SpinningWheel />}
      playButton={GOLD_BUTTON}
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
        <ul className="grid grid-cols-[auto_auto_1fr] items-center gap-x-3 gap-y-2.5">
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
                <CallChipFace yourIndex={0} realIndex={0} outcome="first" still />
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

export function QuickHelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <GameHelpDialog
      open={open}
      onClose={onClose}
      title="Quick Mode"
      art={WHEEL_GAME_ART}
      artPosition="60% 38%"
      icon={<SpinningWheel />}
      playButton={GOLD_BUTTON}
      footnote="Every pack was pod-drafted on"
    >
      <HelpSection title="Find the Wheel">
        <HelpSteps steps={["Each round shows 3 cards from one Pod pack", "Select the card you think wheeled"]} />
      </HelpSection>
      <HelpSection title="Difficulty">
        <ul className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2.5">
          <li className="contents">
            <span className={cn(PIXEL_TAG, "text-lg")}>Easy</span>
            <span className="font-bold">One picked 1st to 3rd, and another 6th to 8th</span>
          </li>
          <li className="contents">
            <span className={cn(PIXEL_TAG, "text-lg")}>Hard</span>
            <span className="font-bold">Both picked right before the wheel</span>
          </li>
        </ul>
      </HelpSection>
    </GameHelpDialog>
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
