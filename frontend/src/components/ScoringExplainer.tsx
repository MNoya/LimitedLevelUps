import type { ReactNode } from "react";

// The leaderboard scoring breakdown — formula, per-queue weights, and pod
// points. Shared by the scoring modal (opened from the POINTS header) and the
// standalone /about page so the explanation stays identical in both.
export function ScoringExplainer() {
  return (
    <section>
      <h2 className="font-display text-[16px] md:text-[18px] text-text tracking-[0.18em] mb-3 md:mb-4">
        LEADERBOARD <span className="text-green">POINTS</span>
      </h2>
      <Scoring />
    </section>
  );
}

function Scoring() {
  return (
    <div className="flex flex-col gap-5 md:gap-6">
      <div className="bg-surface border border-border2 px-2.5 py-4 md:px-6 md:py-5 mono tracking-tight">
        <div
          className="flex flex-nowrap items-center justify-center md:justify-start whitespace-nowrap"
          style={{ fontSize: "clamp(9px, 2.8vw, 17px)" }}
        >
          <span className="relative inline-block mr-[0.4em] align-middle">
            <span className="relative -top-[0.1em] text-text text-[2em] leading-none">Σ</span>
            <span className="absolute left-1/2 -translate-x-1/2 top-full -mt-[0.1em] text-green text-[0.6em] tracking-normal leading-none">
              queues
            </span>
          </span>
          <span className="text-text">Trophies</span>
          <span className="text-green mx-[0.35em]">×</span>
          <span className="text-text">Weight</span>
          <span className="text-green mx-[0.35em]">×</span>
          <span className="text-text">Trophy Rate</span>
          <span className="text-green mx-[0.35em]">×</span>
          <span className="text-text">Confidence</span>
          <span className="text-green mx-[0.35em] text-[1.3em] align-middle">+</span>
          <span className="text-text">Pod</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12">
        <div className="flex flex-col gap-2 text-[13px] md:text-[14px] text-muted leading-[1.6]">
          <p>
            Each queue is scored based on <span className="text-text">trophies</span>, then summed
            into a single total.<br/>
            The goal is to reward performance while considering volume.</p>
          <p>
            <span className="text-text">Weight</span> values events by difficulty, cost, and
            prestige.
          </p>
          <p>
            <span className="text-text">Confidence</span> factor{" "}
            <code className="mono text-muted text-[11px] md:text-[12px] whitespace-nowrap">
              trophies / (trophies + 2)
            </code>{" "}
            provides sample-size protection.
          </p>
          <p>
            Filtering by format or deck colors recalculates points using only the matching events.
          </p>
        </div>

        <div className="flex flex-col">
          <div className="mono text-[10px] text-muted tracking-[0.24em] pb-2 flex justify-between">
            <span>QUEUE</span>
            <span>WEIGHT</span>
          </div>
          <Leader label="Premier Draft" value="10" />
          <Leader label="Platinum Trophy" value="11" nested />
          <Leader label="Diamond Trophy" value="13" nested />
          <Leader label="Mythic Trophy" value="15" nested />
          <Leader label="Traditional Draft" value="8" />
          <Leader label="Sealed" note="Includes Arena Direct" value="10" />
          <Leader label="Quick & Pick Two Draft" value="4" />
          <Leader label="ALCQ Draft 1" value="30" />
          <Leader label="ALCQ Draft 2" note="Per Game Win" value="10" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-12">
        <div className="flex flex-col gap-2 text-[13px] md:text-[14px] text-muted leading-[1.6]">
          <p>
            <span className="text-text">Pod Drafts</span> score on their own, adding flat points
            directly to the total with no other factors applied.
          </p>
        </div>

        <div className="flex flex-col">
          <div className="mono text-[10px] text-muted tracking-[0.24em] pb-2 flex justify-between">
            <span>POD DRAFT</span>
            <span>POINTS</span>
          </div>
          <Leader label="Trophy" value="5" />
          <Leader label="2-1 Record" value="2" />
        </div>
      </div>

      <p
        className="text-dim italic leading-[1.6] text-right whitespace-nowrap -my-2 md:-my-3"
        style={{ fontSize: "clamp(10px, 3.2vw, 13px)" }}
      >
        Scoring may change based on community feedback.
      </p>
    </div>
  );
}

function Leader({
  label,
  note,
  value,
  nested,
}: {
  label: string;
  note?: string;
  value: ReactNode;
  nested?: boolean;
}) {
  return (
    <div className={`flex items-baseline gap-2 py-1.5${nested ? " pl-4 md:pl-5" : ""}`}>
      <span
        className={
          nested
            ? "text-[12px] md:text-[13px] text-muted shrink-0"
            : "font-display text-[13px] md:text-[15px] tracking-[0.04em] text-text shrink-0"
        }
      >
        {label}
      </span>
      {note && (
        <span className="text-[11px] md:text-[12px] text-muted italic shrink-0">{note}</span>
      )}
      <span className="flex-1 border-b border-dotted border-dim relative -top-1.5" />
      <span className="mono text-[13px] md:text-[14px] text-muted tabular-nums">{value}</span>
    </div>
  );
}
