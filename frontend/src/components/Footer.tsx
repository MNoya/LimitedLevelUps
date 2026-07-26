import { cn } from "../lib/utils";

export function Footer({ className, updated }: { className?: string; updated?: string }) {
  return (
    <footer className={cn("flex items-center text-[11px] md:text-[12px] text-muted", className)}>
      <span className="mono">
        {updated ? <>UPDATED {updated}</> : null}
      </span>
    </footer>
  );
}
