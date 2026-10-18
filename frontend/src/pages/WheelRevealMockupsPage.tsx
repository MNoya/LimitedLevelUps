import { useMemo, useState, type ReactNode } from "react";
import { ArrowRight, Check, RotateCcw, Star, X } from "lucide-react";

import { Container } from "../components/Container";
import { PageShell } from "../components/PageShell";
import { CardImage, CardImageMapProvider } from "../components/pod/review/ReviewCard";
import { DARK_PIXEL_BUTTON, PIXEL_HEADING } from "../components/draftGames/pixelStyles";
import { PickText } from "../components/draftGames/wheel/PackGrid";
import { useCardImageMap } from "../data/cardImages";
import { ordinal } from "../data/draftGames";
import { cn } from "../lib/utils";
import type { ArtifactCard } from "../types/leaderboard";

type Outcome = "first" | "right" | "missed" | "neutral";

interface Scenario {
  title: string;
  card: ArtifactCard;
  you: number | null;
  real: number | null;
  outcome: Outcome;
}

interface Variant {
  key: string;
  name: string;
  idea: string;
  render: (scenario: Scenario) => ReactNode;
}

const CARD_RADIUS = "rounded-[4.5%/3.2%]";
const GOLD = "bg-[#f6c95e] text-[#1a120b]";
const SLATE = "bg-[#2b3445] text-text";
const PIXEL_EDGE = "border-[3px] border-[#1a120b] shadow-[3px_3px_0_#05070a]";
const OUTCOME_FILL: Record<Outcome, string> = {
  first: "bg-[linear-gradient(180deg,#fff3cf_0%,#f6c95e_45%,#cf8e2c_100%)] text-[#1a120b]",
  right: "bg-green text-[#0b1a10]",
  missed: "bg-red text-[#1a0b0b]",
  neutral: SLATE,
};

export function WheelRevealMockupsPage() {
  const items = useMemo(
    () => [...SCENARIOS, ...WRONG_FIRST_SCENARIOS].map((s) => ({ name: s.card.n, set: s.card.s })),
    [],
  );
  const images = useCardImageMap(items);
  const [replay, setReplay] = useState(0);
  return (
    <PageShell subtitle="WHEEL OF FORTUNE" footer={false}>
      <Container className="py-8">
        <CardImageMapProvider value={images}>
          <style>{REVEAL_KEYFRAMES}</style>
          <div className="flex items-center gap-4">
            <h1 className={cn("text-4xl", PIXEL_HEADING)}>Wrong Call Reveal</h1>
            <button onClick={() => setReplay((n) => n + 1)} className={cn(DARK_PIXEL_BUTTON, "h-9 px-3 text-lg")}>
              <RotateCcw size={16} strokeWidth={3} />
              Replay
            </button>
          </div>
          <p className="mt-2 max-w-3xl text-[15px] text-subtle">
            Right calls behave as in the game: the chip turns green and gets a check in place. Each row tries a
            different way to reveal a wrong call. The cards reveal one after another, like after Confirm
          </p>
          <div key={`first-${replay}`}>
            <h2 className={cn("mt-6 text-2xl", PIXEL_HEADING)}>Wrong First Pick</h2>
            <p className="mt-1 max-w-3xl text-[15px] text-subtle">
              The four ways a first pick goes wrong, in the two finalists plus a Struck Call with a red line for
              readability
            </p>
            {FIRST_PICK_STYLES.map((style) => (
              <section key={style.name} className="mt-5 flex items-center gap-6 border-t-2 border-[#3a2a17] pt-5">
                <div className="w-56 shrink-0">
                  <div className={cn("text-xl", PIXEL_HEADING)}>{style.name}</div>
                  <p className="mt-1 text-sm leading-snug text-subtle">{style.idea}</p>
                </div>
                <div className="flex gap-3">
                  {WRONG_FIRST_SCENARIOS.map((scenario, i) => (
                    <div key={scenario.title} className="w-[150px]">
                      <RevealDemo scenario={scenario} variant={style.key} delayMs={700 + i * 450} />
                      <p className="mt-2 text-xs leading-tight font-bold text-subtle">{scenario.title}</p>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <h2 className={cn("mt-10 text-2xl", PIXEL_HEADING)}>All Options</h2>
          <div key={replay}>
            {WRONG_STYLES.map((style) => (
              <section key={style.name} className="mt-5 flex items-center gap-6 border-t-2 border-[#3a2a17] pt-5">
                <div className="w-56 shrink-0">
                  <div className={cn("text-xl", PIXEL_HEADING)}>{style.name}</div>
                  <p className="mt-1 text-sm leading-snug text-subtle">{style.idea}</p>
                </div>
                <div className="flex gap-2">
                  {SCENARIOS.map((scenario, i) => (
                    <RevealDemo key={scenario.title} scenario={scenario} variant={style.key} delayMs={700 + i * 450} />
                  ))}
                </div>
              </section>
            ))}
          </div>
          <h1 className={cn("mt-14 text-4xl", PIXEL_HEADING)}>Label Edge at Phone Size</h1>
          <p className="mt-2 max-w-3xl text-[15px] text-subtle">
            The game label at the card width a phone shows, 112px. Each row tries a different border, outline or shadow
          </p>
          {EDGE_STYLES.map((edge) => (
            <section key={edge.name} className="mt-5 flex items-center gap-6 border-t-2 border-[#3a2a17] pt-5">
              <div className="w-56 shrink-0">
                <div className={cn("text-xl", PIXEL_HEADING)}>{edge.name}</div>
                <p className="mt-1 text-sm leading-snug text-subtle">{edge.idea}</p>
              </div>
              <div className="flex gap-2">
                {SCENARIOS.map((scenario) => (
                  <PhoneCard key={scenario.title} scenario={scenario} edge={edge} />
                ))}
              </div>
            </section>
          ))}
          <h1 className={cn("mt-14 text-4xl", PIXEL_HEADING)}>Reveal Mockups</h1>
          <p className="mt-2 max-w-3xl text-[15px] text-subtle">
            Every row shows the same six outcomes in one style. The layout choice between A and B, cards in place or
            regrouped into real order, is separate and works with any row.
          </p>
          <div className="mt-6 grid grid-cols-[14rem_repeat(6,minmax(0,1fr))] gap-x-4 gap-y-2">
            <span />
            {SCENARIOS.map((s) => (
              <span key={s.title} className="text-sm leading-tight font-bold text-text">
                {s.title}
              </span>
            ))}
          </div>
          {VARIANTS.map((variant) => (
            <section
              key={variant.key}
              className="mt-6 grid grid-cols-[14rem_repeat(6,minmax(0,1fr))] items-start gap-4 border-t-2 border-[#3a2a17] pt-6"
            >
              <div>
                <div className={cn("text-2xl", PIXEL_HEADING)}>{variant.name}</div>
                <p className="mt-2 text-sm leading-snug text-subtle">{variant.idea}</p>
              </div>
              {SCENARIOS.map((s) => (
                <div key={s.title} className="relative">
                  {variant.render(s)}
                </div>
              ))}
            </section>
          ))}
        </CardImageMapProvider>
      </Container>
    </PageShell>
  );
}

const VARIANTS: Variant[] = [
  {
    key: "a",
    name: "Current A",
    idea: "Your number top left, real result as a big center plate, green or red outline",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome} outline>
        {s.you != null && <Corner className={cn("top-[11%] left-[6%]", GOLD)}>{s.you}</Corner>}
        <CenterPlate>{realLabel(s.real)}</CenterPlate>
      </Card>
    ),
  },
  {
    key: "pair",
    name: "Your Call Then Result",
    idea: "One chip reads left to right: your call, an arrow, what happened. The result half carries the color",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        <span className={cn("absolute top-[11%] left-[6%] flex items-stretch", PIXEL_EDGE)}>
          <span className={cn("px-2 pt-1 pb-0.5 font-display text-xl leading-none", GOLD)}>{yourShort(s.you)}</span>
          <span className="grid place-items-center bg-[#1a120b] px-1 text-[#f6c95e]">
            <ArrowRight size={14} strokeWidth={3} />
          </span>
          <span className={cn("px-2 pt-1 pb-0.5 font-display text-xl leading-none", OUTCOME_FILL[s.outcome])}>
            {realShort(s.real)}
          </span>
        </span>
      </Card>
    ),
  },
  {
    key: "merge",
    name: "Call Turns Green",
    idea: "A right call stays one chip and turns from gold to green. A wrong call adds an arrow and the real result in red",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        <CallChip scenario={s} />
      </Card>
    ),
  },
  {
    key: "ticks",
    name: "Call With Tick or Cross",
    idea: "Same chip, but colors stay gold and slate. A tick or a cross says right or wrong",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        <CallChip scenario={s} marks />
      </Card>
    ),
  },
  {
    key: "strike",
    name: "Struck Call",
    idea: "Only your number shows. A wrong call gets crossed out with the real result beside it, a right call gets a check",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        <span className="absolute top-[11%] left-[6%] flex items-center gap-1.5">
          <span
            className={cn(
              "relative grid size-9 place-items-center pt-0.5 font-display text-xl",
              PIXEL_EDGE,
              s.you == null ? SLATE : GOLD,
            )}
          >
            {s.you ?? "–"}
            {s.outcome === "missed" && <span className="absolute inset-x-0.5 top-1/2 h-[3px] -rotate-45 bg-red" />}
          </span>
          {s.outcome === "missed" && (
            <span className={cn("px-2 pt-1 pb-0.5 font-display text-lg leading-none", PIXEL_EDGE, SLATE)}>
              {realShort(s.real)}
            </span>
          )}
          {(s.outcome === "first" || s.outcome === "right") && (
            <span className={cn("grid size-7 place-items-center", PIXEL_EDGE, OUTCOME_FILL[s.outcome])}>
              <Check size={16} strokeWidth={4} />
            </span>
          )}
        </span>
      </Card>
    ),
  },
  {
    key: "sentence",
    name: "Two Line Caption",
    idea: "A small caption over the art in plain words: what you said on line one, what happened on line two",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        <span className={cn("absolute inset-x-[6%] top-[11%] flex flex-col", PIXEL_EDGE)}>
          <span className="bg-[#16110c] px-2 py-1 text-xs font-bold text-subtle">You: {yourWords(s.you)}</span>
          <span className={cn("px-2 py-1 text-sm font-bold", OUTCOME_FILL[s.outcome])}>{realWords(s.real)}</span>
        </span>
      </Card>
    ),
  },
  {
    key: "corners",
    name: "Opposite Corners",
    idea: "Your call top left in gold, the real result top right in slate. Only a small outcome dot is colored",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        {s.you != null && <Corner className={cn("top-[11%] left-[6%]", GOLD)}>{s.you}</Corner>}
        <Corner className={cn("top-[11%] right-[6%] text-base", SLATE)}>{realShort(s.real)}</Corner>
        <span
          className={cn(
            "absolute bottom-[46%] left-1/2 grid size-8 -translate-x-1/2 place-items-center",
            PIXEL_EDGE,
            OUTCOME_FILL[s.outcome],
          )}
        >
          {(s.outcome === "first" || s.outcome === "right") && <Check size={16} strokeWidth={4} />}
          {s.outcome === "missed" && <X size={16} strokeWidth={4} />}
        </span>
      </Card>
    ),
  },
  {
    key: "footer",
    name: "Verdict Band",
    idea: "The art stays clear. A band across the type line states your call and the result, tinted by outcome",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        {s.you != null && <Corner className={cn("top-[11%] left-[6%]", GOLD)}>{s.you}</Corner>}
        <span
          className={cn(
            "absolute inset-x-[5%] bottom-[38%] flex items-center justify-center gap-2 border-[3px] border-[#1a120b] py-1",
            "font-display text-lg leading-none",
            OUTCOME_FILL[s.outcome],
          )}
        >
          {s.outcome === "missed" && <X size={16} strokeWidth={4} />}
          {(s.outcome === "first" || s.outcome === "right") && <Check size={16} strokeWidth={4} />}
          {realShort(s.real)}
        </span>
      </Card>
    ),
  },
  {
    key: "quiet",
    name: "Misses Only",
    idea: "A miss gets a label phrased as a correction. A right wheel call gets a small check, other cards stay quiet",
    render: (s) => (
      <Card card={s.card} outcome={s.outcome}>
        {s.you != null && <Corner className={cn("top-[11%] left-[6%]", GOLD)}>{s.you}</Corner>}
        {s.outcome === "right" && (
          <Corner className={cn("top-[11%] left-[6%]", OUTCOME_FILL.right)}>
            <Check size={18} strokeWidth={4} />
          </Corner>
        )}
        {s.outcome === "missed" && (
          <span className="absolute inset-x-0 bottom-[46%] flex justify-center">
            <span className={cn("px-2 pt-1 pb-0.5 font-display text-lg leading-none", PIXEL_EDGE, OUTCOME_FILL.missed)}>
              {missWords(s)}
            </span>
          </span>
        )}
      </Card>
    ),
  },
];

type WrongVariant = "extend" | "strike" | "strikeRed" | "swap" | "below" | "cross";

const WRONG_STYLES: { key: WrongVariant; name: string; idea: string }[] = [
  {
    key: "extend",
    name: "Extend Right",
    idea: "What the game does now: one framed chip grows an arrow and the red result to the right",
  },
  {
    key: "strike",
    name: "Struck Call",
    idea: "No arrow. Your call gets a thin strike line and the red result grows right next to it in the same chip",
  },
  {
    key: "swap",
    name: "Swap in Place",
    idea: "The chip stays put and flips to the red result with a cross. Your call stays as a small struck tag above",
  },
  {
    key: "below",
    name: "Result Below",
    idea: "Your gold call stays put. The red result drops in under it, so nothing moves sideways",
  },
  {
    key: "cross",
    name: "Red With Cross",
    idea: "Mirror of a right call: the chip turns red and gets a cross. The real result shows as a small tag under it",
  },
];

const FIRST_PICK_STYLES = [
  WRONG_STYLES[0],
  WRONG_STYLES[1],
  {
    key: "strikeRed" as const,
    name: "Struck Call, Red Line",
    idea: "Same as Struck Call, but the strike line is red and thicker so it reads at phone size",
  },
];

const REVEAL_KEYFRAMES = `
@keyframes demoFadeOut { to { opacity: 0 } }
@keyframes demoFadeIn { from { opacity: 0; transform: scale(1.4) } to { opacity: 1; transform: scale(1) } }
@keyframes demoDrop { from { opacity: 0; transform: translateY(-0.6em) } to { opacity: 1; transform: translateY(0) } }
@keyframes demoGrow { from { max-width: 0; opacity: 0 } to { max-width: 12em; opacity: 1 } }
@keyframes demoStrike { from { transform: scaleX(0) } to { transform: scaleX(1) } }
@keyframes demoFromGold { from { background-color: #f6c95e; color: #1a120b } }
@keyframes demoRingFromGold { from { box-shadow: 0 0 0 1px #f6c95e, 2px 2px 0 1px #05070a } }
`;

const DEMO_CHIP =
  "flex items-center gap-[1.5cqw] whitespace-nowrap px-[3cqw] pt-[1.5cqw] pb-[1cqw] font-display leading-none";
const DEMO_FRAME = "flex items-stretch overflow-hidden border-[3px] border-[#1a120b]";
const RING = {
  gold: "shadow-[0_0_0_1px_#f6c95e,2px_2px_0_1px_#05070a]",
  green: "shadow-[0_0_0_1px_#2ee85c,2px_2px_0_1px_#05070a]",
  red: "shadow-[0_0_0_1px_#ef4444,2px_2px_0_1px_#05070a]",
};

function RevealDemo({ scenario: s, variant, delayMs }: { scenario: Scenario; variant: WrongVariant; delayMs: number }) {
  const right = s.outcome === "first" || s.outcome === "right";
  const wrong = s.outcome === "missed";
  const at = (name: string, ms = 320, fill = "both") => ({
    animation: `${name} ${ms}ms ease-out ${delayMs}ms ${fill}`,
  });
  const call = s.you == null ? "Wheel" : <PickText pick={s.you} />;
  const result = s.real == null ? "Wheeled" : <PickText pick={s.real} />;
  const resultFill = wrong ? OUTCOME_FILL.missed : SLATE;
  const ring = wrong ? RING.red : RING.gold;
  let label: ReactNode;
  if (right) {
    label = (
      <span
        className={cn(DEMO_FRAME, RING.green)}
        style={s.you == null ? at("demoFadeIn") : at("demoRingFromGold", 300, "backwards")}
      >
        <span
          className={cn(DEMO_CHIP, OUTCOME_FILL.right)}
          style={s.you == null ? undefined : at("demoFromGold", 300, "backwards")}
        >
          {call}
          <Check className="size-[0.9em]" strokeWidth={4} style={at("demoFadeIn")} />
        </span>
      </span>
    );
  } else if (variant === "extend") {
    label = (
      <span className={cn(DEMO_FRAME, ring)} style={at("demoRingFromGold", 300, "backwards")}>
        <span className={cn(DEMO_CHIP, GOLD)}>{call}</span>
        <span className="flex items-stretch overflow-hidden" style={at("demoGrow", 360)}>
          <span className="grid place-items-center bg-[#1a120b] px-[1cqw] text-[#f6c95e]">
            <ArrowRight className="size-[0.8em]" strokeWidth={3} />
          </span>
          <span className={cn(DEMO_CHIP, resultFill)}>{result}</span>
        </span>
      </span>
    );
  } else if (variant === "strike" || variant === "strikeRed") {
    label = (
      <span className={cn(DEMO_FRAME, ring)} style={at("demoRingFromGold", 300, "backwards")}>
        <span className={cn(DEMO_CHIP, GOLD, "relative")}>
          {call}
          {wrong && (
            <span
              className={cn(
                "absolute inset-x-[2cqw] top-1/2 origin-left",
                variant === "strikeRed" ? "h-[0.14em] -translate-y-1/2 bg-[#d6332f]" : "h-[0.09em] bg-[#1a120b]",
              )}
              style={at("demoStrike", 260)}
            />
          )}
        </span>
        <span className="flex items-stretch overflow-hidden" style={at("demoGrow", 360)}>
          <span className={cn(DEMO_CHIP, resultFill)}>{result}</span>
        </span>
      </span>
    );
  } else if (variant === "swap") {
    label = (
      <span className="flex flex-col items-center gap-[1cqw]">
        <span
          className="bg-[#16110c]/85 px-[2cqw] text-[0.7em] text-[#f6c95e] line-through decoration-2"
          style={at("demoDrop")}
        >
          {call}
        </span>
        <span className="grid">
          <span
            className={cn(DEMO_FRAME, RING.gold, "[grid-area:1/1] justify-self-center")}
            style={at("demoFadeOut", 200)}
          >
            <span className={cn(DEMO_CHIP, GOLD)}>{call}</span>
          </span>
          <span className={cn(DEMO_FRAME, ring, "[grid-area:1/1] justify-self-center")} style={at("demoFadeIn")}>
            <span className={cn(DEMO_CHIP, resultFill)}>
              {result}
              {wrong && <X className="size-[0.9em]" strokeWidth={4} />}
            </span>
          </span>
        </span>
      </span>
    );
  } else if (variant === "below") {
    label = (
      <span className="flex flex-col items-center gap-[1.5cqw]">
        <span className={cn(DEMO_FRAME, RING.gold)}>
          <span className={cn(DEMO_CHIP, GOLD)}>{call}</span>
        </span>
        <span className={cn(DEMO_FRAME, ring)} style={at("demoDrop")}>
          <span className={cn(DEMO_CHIP, resultFill)}>{result}</span>
        </span>
      </span>
    );
  } else {
    label = (
      <span className="flex flex-col items-center gap-[1.5cqw]">
        <span className={cn(DEMO_FRAME, ring)} style={at("demoRingFromGold", 300, "backwards")}>
          <span
            className={cn(DEMO_CHIP, wrong ? OUTCOME_FILL.missed : GOLD)}
            style={at("demoFromGold", 300, "backwards")}
          >
            {call}
            {wrong && <X className="size-[0.9em]" strokeWidth={4} style={at("demoFadeIn")} />}
          </span>
        </span>
        <span
          className="bg-[#16110c]/90 px-[2cqw] pt-[1cqw] pb-[0.5cqw] font-display text-[0.75em] leading-none text-text"
          style={at("demoDrop")}
        >
          {result}
        </span>
      </span>
    );
  }
  return (
    <div className={cn("relative w-[150px] [container-type:inline-size]", CARD_RADIUS)}>
      <CardImage card={s.card} className={CARD_RADIUS} />
      <span className="absolute inset-x-[4%] bottom-[45.5%] flex justify-center text-[8.5cqw]">{label}</span>
    </div>
  );
}

interface EdgeStyle {
  name: string;
  idea: string;
  frame: string;
  band?: boolean;
  resultRing?: boolean;
}

const EDGE_STYLES: EdgeStyle[] = [
  {
    name: "Gold Ring",
    idea: "What the game has now: dark border, 1px gold ring, 2px black shadow",
    frame: "border-[3px] border-[#1a120b] shadow-[0_0_0_1px_#f6c95e,2px_2px_0_1px_#05070a]",
  },
  {
    name: "Result Ring",
    idea: "Gold Ring, but the ring takes the result color: green when right, red when wrong, gold otherwise",
    frame: "border-[3px] border-[#1a120b]",
    resultRing: true,
  },
  {
    name: "Cream Ring",
    idea: "Dark border, 1px cream ring, 2px black shadow",
    frame: "border-[3px] border-[#1a120b] shadow-[0_0_0_1px_#fff1d6,2px_2px_0_1px_#05070a]",
  },
  {
    name: "Shadow Only",
    idea: "Dark border and a 2px black shadow, no ring",
    frame: "border-[3px] border-[#1a120b] shadow-[2px_2px_0_#05070a]",
  },
  {
    name: "Thin Dark Border",
    idea: "A 2px dark border, no shadow. Lighter on small cards",
    frame: "border-2 border-[#1a120b]",
  },
  {
    name: "Cream Border",
    idea: "A 2px cream border and no shadow. The label reads as a sticker on the art",
    frame: "border-2 border-[#fff1d6]",
  },
  {
    name: "Soft Halo",
    idea: "Dark border plus a blurred dark halo that darkens the art right around the label",
    frame: "border-[3px] border-[#1a120b] shadow-[0_0_10px_3px_rgba(5,7,10,0.85)]",
  },
  {
    name: "Bevel",
    idea: "Dark border, a light inner top edge like a pixel button, 2px black shadow",
    frame: "border-[3px] border-[#1a120b] shadow-[inset_0_2px_0_rgba(255,255,255,0.45),2px_2px_0_#05070a]",
  },
  {
    name: "Dark Band",
    idea: "The label sits on a dark strip across the art, so the art never touches it",
    frame: "border-2 border-[#1a120b]",
    band: true,
  },
];

const RING_BY_OUTCOME: Record<Outcome, string> = {
  first: "shadow-[0_0_0_1px_#2ee85c,2px_2px_0_1px_#05070a]",
  right: "shadow-[0_0_0_1px_#2ee85c,2px_2px_0_1px_#05070a]",
  missed: "shadow-[0_0_0_1px_#ef4444,2px_2px_0_1px_#05070a]",
  neutral: "shadow-[0_0_0_1px_#f6c95e,2px_2px_0_1px_#05070a]",
};

function PhoneCard({ scenario: s, edge }: { scenario: Scenario; edge: EdgeStyle }) {
  const right = s.outcome === "first" || s.outcome === "right";
  const chip = "flex items-center whitespace-nowrap px-[3cqw] pt-[1.5cqw] pb-[1cqw] font-display leading-none";
  return (
    <div
      className={cn(
        "relative w-[112px] [container-type:inline-size]",
        CARD_RADIUS,
        s.outcome === "first" && "shadow-[0_0_0_3px_#f6c95e,0_0_18px_4px_rgba(246,201,94,0.6)]",
      )}
    >
      <CardImage card={s.card} className={CARD_RADIUS} />
      {edge.band && <span className="absolute inset-x-[4%] bottom-[43.5%] h-[13cqw] bg-[#05070a]/85" />}
      <span className="absolute inset-x-[4%] bottom-[45.5%] flex justify-center">
        <span
          className={cn(
            "flex items-stretch overflow-hidden text-[8.5cqw]",
            edge.frame,
            edge.resultRing && RING_BY_OUTCOME[s.outcome],
          )}
        >
          <span className={cn(chip, "gap-[1.5cqw]", right ? OUTCOME_FILL.right : GOLD)}>
            {s.you == null ? "Wheel" : <PickText pick={s.you} />}
            {right && <Check className="size-[0.9em]" strokeWidth={4} />}
          </span>
          {!right && (
            <>
              <span className="grid place-items-center bg-[#1a120b] px-[1cqw] text-[#f6c95e]">
                <ArrowRight className="size-[0.8em]" strokeWidth={3} />
              </span>
              <span className={cn(chip, s.outcome === "neutral" ? SLATE : OUTCOME_FILL.missed)}>
                {s.real == null ? "Wheeled" : <PickText pick={s.real} />}
              </span>
            </>
          )}
        </span>
      </span>
    </div>
  );
}

function CallChip({ scenario: s, marks = false }: { scenario: Scenario; marks?: boolean }) {
  const right = s.outcome === "first" || s.outcome === "right";
  const chip = "flex items-center gap-1.5 px-2 pt-1 pb-0.5 font-display text-xl leading-none";
  const call = s.you == null ? "Wheel" : s.you === 1 ? "1st Pick" : ordinal(s.you);
  let callFill = GOLD;
  if (right && !marks) {
    callFill = OUTCOME_FILL.right;
  }
  return (
    <span className={cn("absolute top-[11%] left-[6%] flex items-stretch", PIXEL_EDGE)}>
      <span className={cn(chip, callFill)}>
        {call}
        {marks && right && <Tick />}
        {!marks && right && <Check size={16} strokeWidth={4} />}
      </span>
      {!right && (
        <>
          <span className="grid place-items-center bg-[#1a120b] px-1 text-[#f6c95e]">
            <ArrowRight size={14} strokeWidth={3} />
          </span>
          <span className={cn(chip, marks || s.outcome === "neutral" ? SLATE : OUTCOME_FILL.missed)}>
            {resultLabel(s.real)}
            {marks && s.outcome === "missed" && <Cross />}
          </span>
        </>
      )}
    </span>
  );
}

function Tick() {
  return (
    <span className="grid size-5 place-items-center border-2 border-[#1a120b] bg-green text-[#0b1a10]">
      <Check size={13} strokeWidth={4} />
    </span>
  );
}

function Cross() {
  return (
    <span className="grid size-5 place-items-center border-2 border-[#1a120b] bg-red text-[#1a0b0b]">
      <X size={13} strokeWidth={4} />
    </span>
  );
}

function resultLabel(real: number | null): string {
  if (real == null) {
    return "Wheeled";
  }
  return real === 1 ? "1st Pick" : ordinal(real);
}

function Card({
  card,
  outcome,
  outline = false,
  children,
}: {
  card: ArtifactCard;
  outcome: Outcome;
  outline?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative",
        CARD_RADIUS,
        outcome === "first" && "shadow-[0_0_0_4px_#f6c95e,0_0_28px_6px_rgba(246,201,94,0.6)]",
        outline && outcome === "right" && "shadow-[0_0_0_3px_#2ee85c]",
        outline && outcome === "missed" && "shadow-[0_0_0_3px_#ef4444]",
      )}
    >
      <CardImage card={card} className={CARD_RADIUS} />
      {children}
      {outcome === "first" && <FirstPickRibbon />}
    </div>
  );
}

function FirstPickRibbon() {
  return (
    <span className="pointer-events-none absolute inset-x-0 -bottom-3 z-20 flex justify-center">
      <span
        className={cn(
          "flex items-center gap-1.5 px-3 pt-1.5 pb-1 font-display text-lg leading-none",
          PIXEL_EDGE,
          OUTCOME_FILL.first,
        )}
      >
        <Star size={16} className="-mt-0.5 fill-current" />
        First Pick
        <Star size={16} className="-mt-0.5 fill-current" />
      </span>
    </span>
  );
}

function Corner({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        "absolute z-10 grid min-w-9 place-items-center px-1.5 pt-1 pb-0.5 font-display text-xl leading-none",
        PIXEL_EDGE,
        className,
      )}
    >
      {children}
    </span>
  );
}

function CenterPlate({ children }: { children: ReactNode }) {
  return (
    <span className="absolute inset-x-0 bottom-[45.5%] flex justify-center">
      <span className={cn("px-2.5 pt-1 pb-0.5 font-display text-2xl leading-none", PIXEL_EDGE, SLATE)}>{children}</span>
    </span>
  );
}

function realLabel(real: number | null): string {
  return real == null ? "Wheeled" : `${ordinal(real)} Pick`;
}

function realShort(real: number | null): string {
  return real == null ? "Wheeled" : ordinal(real);
}

function yourShort(you: number | null): string {
  return you == null ? "Out" : ordinal(you);
}

function yourWords(you: number | null): string {
  return you == null ? "left it out" : `${ordinal(you)} pick`;
}

function realWords(real: number | null): string {
  return real == null ? "It wheeled" : `Taken ${ordinal(real)}`;
}

function missWords(s: Scenario): string {
  if (s.real == null) {
    return "It Wheeled";
  }
  if (s.you == null) {
    return `Taken ${ordinal(s.real)}`;
  }
  return `Real ${ordinal(s.real)}`;
}

const card = (n: string, cn: string): ArtifactCard => ({ n, cn, s: "fra", r: null, c: null, cmc: null, type: null });

const WRONG_FIRST_SCENARIOS: Scenario[] = [
  { title: "You 1st, real 4th", card: card("Violent Echoes", "95"), you: 1, real: 4, outcome: "missed" },
  {
    title: "You 1st, it wheeled",
    card: card("Saheeli, Jewel of Avishkar", "275"),
    you: 1,
    real: null,
    outcome: "missed",
  },
  { title: "You 3rd, real 1st", card: card("Tenured Tethermage", "357"), you: 3, real: 1, outcome: "missed" },
  {
    title: "You left it out, real 1st",
    card: card("Thalia, the Survivor", "205"),
    you: null,
    real: 1,
    outcome: "missed",
  },
];

const SCENARIOS: Scenario[] = [
  {
    title: "You 1st, real 1st",
    card: card("Tenured Tethermage", "357"),
    you: 1,
    real: 1,
    outcome: "first",
  },
  {
    title: "You 6th, it wheeled",
    card: card("Archive Arbiter", "167"),
    you: 6,
    real: null,
    outcome: "missed",
  },
  {
    title: "You left it out, it wheeled",
    card: card("Surgical Precision", "22"),
    you: null,
    real: null,
    outcome: "right",
  },
  {
    title: "You 5th, real 2nd",
    card: card("Loot, the Anomaly", "232"),
    you: 5,
    real: 2,
    outcome: "neutral",
  },
  {
    title: "You left it out, real 3rd",
    card: card("Thalia, the Survivor", "205"),
    you: null,
    real: 3,
    outcome: "missed",
  },
  { title: "You 1st, real 4th", card: card("Violent Echoes", "95"), you: 1, real: 4, outcome: "missed" },
];

const SLOT_DEMO_PICKS = [
  card("Tenured Tethermage", "357"),
  card("Loot, the Anomaly", "232"),
  card("Violent Echoes", "95"),
];
