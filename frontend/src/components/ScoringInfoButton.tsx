import { HelpCircle } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { Tooltip } from "./Tooltip";
import { SCORING_HASH } from "./ScoringModal";
import { cn } from "../lib/utils";
import { OPENED_IN_APP } from "../lib/modal-history";

export function ScoringInfoButton({
  className,
  size = 14,
  label,
}: {
  className?: string;
  size?: number;
  label?: string;
}) {
  const location = useLocation();

  const button = (
    <Link
      to={{ pathname: location.pathname, search: location.search, hash: SCORING_HASH }}
      state={OPENED_IN_APP}
      aria-label={label ?? "About Points"}
      className={cn(
        "inline-flex items-center justify-center cursor-pointer transition-colors no-underline",
        label
          ? "gap-1.5 text-muted hover:text-green font-display tracking-[0.10em] text-[12px] leading-none whitespace-nowrap"
          : "text-muted hover:text-green",
        className,
      )}
    >
      <HelpCircle size={size} strokeWidth={2} />
      {label ? <span>{label}</span> : null}
    </Link>
  );

  if (label) {
    return button;
  }
  return <Tooltip label="About Points">{button}</Tooltip>;
}
