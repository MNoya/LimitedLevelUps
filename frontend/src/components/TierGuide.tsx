import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Info } from "./Icons";
import { Tooltip } from "./Tooltip";
import { cn } from "../lib/utils";
import { TEXT_OUTLINE } from "../lib/text-styles";
import { TIER_DESCRIPTIONS, TIER_GUIDE_BLOCKS, tierColor } from "../data/tierList";

const GUIDE_MAT = "#161b26";

type OpenGuide = (tier?: string) => void;

const GradeGuideContext = createContext<OpenGuide>(() => {});

export function GradeGuideProvider({ children }: { children: ReactNode }) {
  const [focusTier, setFocusTier] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const openGuide = useCallback<OpenGuide>((tier) => {
    setFocusTier(tier ?? null);
    setOpen(true);
  }, []);

  return (
    <GradeGuideContext.Provider value={openGuide}>
      {children}
      {open &&
        createPortal(
          <GradeGuideModal focusTier={focusTier} onClose={() => setOpen(false)} />,
          document.body,
        )}
    </GradeGuideContext.Provider>
  );
}

export function useGradeGuide(): OpenGuide {
  return useContext(GradeGuideContext);
}

export function GradeGuideTrigger({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  const openGuide = useGradeGuide();
  return (
    <Tooltip label="Grade Guide" side="bottom">
      <button
        type="button"
        onClick={() => openGuide()}
        aria-label="Grade Guide"
        className={cn("inline-flex items-center transition-colors hover:text-green", className)}
      >
        {children}
      </button>
    </Tooltip>
  );
}

export function GradeGuideIcon({ className }: { className?: string }) {
  return <Info size={13} className={cn("shrink-0", className)} />;
}

// The grade letter down the grid rail: hover for that one grade, click for the whole guide.
export function GradeLabel({
  tier,
  className,
  style,
}: {
  tier: string;
  className?: string;
  style?: CSSProperties;
}) {
  const openGuide = useGradeGuide();
  const description = TIER_DESCRIPTIONS[tier];
  const button = (
    <button
      type="button"
      onClick={() => openGuide(tier)}
      aria-label={description ? `${tier}: ${description.title}` : tier}
      className={cn("transition-colors hover:text-[var(--tier-color)]", className)}
      style={{ ...style, "--tier-color": tierColor(tier) } as CSSProperties}
    >
      {tier}
    </button>
  );
  if (!description) {
    return button;
  }
  return (
    <Tooltip
      label={<GradeText tier={tier} watermark />}
      side="right"
      className="max-w-[320px] px-3 py-2.5"
    >
      {button}
    </Tooltip>
  );
}

function GradeText({ tier, watermark = false }: { tier: string; watermark?: boolean }) {
  const { title, body } = TIER_DESCRIPTIONS[tier];
  return (
    <span
      className={
        watermark ? "relative flex min-h-[26px] flex-col justify-center pr-12" : "relative block"
      }
    >
      {watermark && (
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 font-display text-[26px] leading-none",
            TEXT_OUTLINE,
          )}
          style={{ color: tierColor(tier) }}
        >
          {tier}
        </span>
      )}
      <span className="relative block text-[13px] font-semibold leading-snug text-text">
        {title}
      </span>
      {body && (
        <span className="relative mt-1 block whitespace-pre-line text-[13px] leading-snug text-muted">
          {body}
        </span>
      )}
    </span>
  );
}

function GradeGuideModal({
  focusTier,
  onClose,
}: {
  focusTier: string | null;
  onClose: () => void;
}) {
  const focusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "center" });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[calc(100dvh-32px)] w-full max-w-[720px] flex-col rounded-xl border border-white/15 shadow-2xl sm:border-white/60"
        style={{ backgroundColor: GUIDE_MAT }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative flex items-center justify-center border-b border-white/15 px-12 py-3.5 sm:border-white/60">
          <h2 className="font-display text-[17px] leading-none tracking-[0.12em] text-text">
            GRADE GUIDE
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute right-4 top-1/2 -translate-y-1/2 px-1 text-[20px] leading-none text-muted transition-colors hover:text-text"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-1.5">
          {TIER_GUIDE_BLOCKS.map((block) => (
            <div key={block[0]} className="border-t border-white/10 py-2 first:border-t-0">
              {block.map((tier) => (
                <div
                  key={tier}
                  ref={tier === focusTier ? focusRef : undefined}
                  className={cn(
                    "grid grid-cols-[32px_minmax(0,1fr)] items-start gap-x-2 rounded-md px-2 py-1.5",
                    tier === focusTier && "bg-white/10",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-[18px] items-center font-display text-[21px] leading-none",
                      TIER_DESCRIPTIONS[tier].body && "translate-y-[1px]",
                    )}
                    style={{ color: tierColor(tier) }}
                  >
                    {tier}
                  </span>
                  <div>
                    <GradeText tier={tier} />
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
