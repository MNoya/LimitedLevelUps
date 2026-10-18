import { useState, type ReactNode } from "react";

import { RECORD_POINTS, TROPHY_MAGE_ART, TROPHY_POINTS } from "../../../data/trophyMage";
import { GameHelpDialog, HelpScoreRow, HelpSection, HelpSteps } from "../GameDialog";
import { ACCENT_BUTTON } from "../pixelStyles";
import { CallTag, RevealChip } from "./RecordChip";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";

export function TrophyHelpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <GameHelpDialog
      open={open}
      onClose={onClose}
      art={TROPHY_MAGE_ART}
      artPosition="50% 30%"
      icon={<ShiningTrophy />}
      playButton={ACCENT_BUTTON}
      footnote="Every deck was pod-drafted on"
      className="game-theme-ice"
    >
      <HelpSection title="Guess the 3-0 Deck">
        <HelpSteps
          steps={[
            "Each round shows the decks from one Pod",
            "Pick the deck you think went 3-0",
            "Place the other decks for bonus points",
          ]}
        />
      </HelpSection>
      <HelpSection title="Scoring">
        <ul className="grid grid-cols-[auto_auto_1fr] items-center gap-x-3 gap-y-2.5">
          <HelpScoreRow
            plate={
              <ScorePlate>
                <CallTag record="3-0" />
              </ScorePlate>
            }
            points={TROPHY_POINTS}
          >
            Correct Trophy
          </HelpScoreRow>
          <HelpScoreRow
            plate={
              <ScorePlate>
                <RevealChip call="1-2" actual="1-2" />
              </ScorePlate>
            }
            points={RECORD_POINTS}
          >
            Correct Record
          </HelpScoreRow>
        </ul>
      </HelpSection>
    </GameHelpDialog>
  );
}

function ScorePlate({ children }: { children: ReactNode }) {
  return <span className="flex w-28 justify-center text-xl">{children}</span>;
}

function ShiningTrophy() {
  const [shines, setShines] = useState(0);
  return (
    <button
      type="button"
      aria-label="Shine the trophy"
      onClick={() => setShines((count) => count + 1)}
      className="cursor-pointer drop-shadow-[2px_2px_0_#05070a] active:scale-95"
    >
      <SpriteStrip sheet={TROPHY_SPRITE} scale={3} restMs={1800} playToken={shines} />
    </button>
  );
}
