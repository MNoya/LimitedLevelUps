import { type ReactNode } from "react";
import { AppHeader } from "./AppHeader";
import { SiteFooter } from "./SiteFooter";
import { cn } from "../lib/utils";
import { useLockedViewport } from "../lib/use-locked-viewport";

// Standard community-site page frame: themed header, a growing main, and the
// shared footer. Sections own their own width via <Container>, so main stays
// full-bleed to let the hero and bands run edge to edge.
//
// `fill` locks the frame to one viewport on desktop (no page scroll) so a child
// dashboard can flex its panels into the exact rendered space; mobile keeps the
// normal growing-and-scrolling flow.
export function PageShell({
  subtitle,
  fill = false,
  sponsorVariant = "gray",
  children,
}: {
  subtitle?: string;
  fill?: boolean;
  sponsorVariant?: "color" | "gray";
  children: ReactNode;
}) {
  useLockedViewport(fill);

  return (
    <div
      className={cn(
        "bg-bg text-text flex flex-col page-fade min-h-screen",
        fill && "lg:h-screen lg:min-h-0 lg:overflow-hidden",
      )}
    >
      <AppHeader subtitle={subtitle} fill={fill} />
      <main className={cn("flex-1", fill ? "lg:min-h-0 lg:overflow-hidden" : "flex flex-col")}>{children}</main>
      <SiteFooter sponsorVariant={sponsorVariant} />
    </div>
  );
}
