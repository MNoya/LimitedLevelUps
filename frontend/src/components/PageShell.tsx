import { useEffect, type ReactNode } from "react";
import { AppHeader } from "./AppHeader";
import { SiteFooter } from "./SiteFooter";
import { cn } from "../lib/utils";

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
  flushFooter = false,
  children,
}: {
  subtitle?: string;
  fill?: boolean;
  flushFooter?: boolean;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!fill) {
      return;
    }
    const html = document.documentElement;
    const previous = html.style.scrollbarGutter;
    const probe = document.createElement("div");
    probe.style.cssText = "position:absolute;top:-9999px;width:100px;height:100px;overflow:scroll";
    document.body.appendChild(probe);
    const scrollbarWidth = probe.offsetWidth - probe.clientWidth;
    probe.remove();
    html.style.setProperty("--app-scrollbar", `${scrollbarWidth}px`);
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = previous;
      html.style.removeProperty("--app-scrollbar");
    };
  }, [fill]);

  return (
    <div
      className={cn(
        "bg-bg text-text flex flex-col page-fade min-h-screen",
        fill && "lg:h-screen lg:min-h-0 lg:overflow-hidden",
      )}
    >
      <AppHeader subtitle={subtitle} fill={fill} />
      <main className={cn("flex-1", fill ? "lg:min-h-0 lg:overflow-hidden" : "flex flex-col")}>{children}</main>
      <SiteFooter flush={fill || flushFooter} />
    </div>
  );
}
