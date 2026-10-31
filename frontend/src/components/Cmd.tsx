import type { ReactNode } from "react";

export function Cmd({ children }: { children: ReactNode }) {
  return (
    <code className="font-mono text-text bg-surface2 border border-border2 px-1.5 py-px text-[13px] whitespace-nowrap">
      {children}
    </code>
  );
}
