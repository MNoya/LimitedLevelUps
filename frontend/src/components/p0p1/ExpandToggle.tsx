import { ChevronDown, ChevronUp } from "lucide-react";

export function ExpandToggle({
  expanded,
  onToggle,
  className = "",
}: {
  expanded: boolean;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={`flex items-center gap-1 bg-transparent border-0 p-0 cursor-pointer text-subtle hover:text-green font-display text-[13px] tracking-[0.1em] whitespace-nowrap ${className}`}
    >
      {expanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
      {expanded ? "COLLAPSE" : "EXPAND"}
    </button>
  );
}
