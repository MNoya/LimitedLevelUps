import type { ReactNode } from "react";
import { Coins, Hammer, Library, type LucideIcon } from "lucide-react";
import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { PanelShell } from "../components/CommunityBits";
import { WildcardIcon } from "../components/WildcardIcon";
import { ArrowRight } from "../components/Icons";
import { cn } from "../lib/utils";

interface Tool {
  title: string;
  blurb: string;
  Icon: LucideIcon;
  to?: string;
  extra?: ReactNode;
}

export function ToolsPage() {
  const wildcards = (
    <span className="flex items-center gap-2">
      <WildcardIcon rarity="common" size={22} />
      <WildcardIcon rarity="uncommon" size={22} />
      <WildcardIcon rarity="rare" size={22} />
      <WildcardIcon rarity="mythic" size={22} />
    </span>
  );
  const tools: Tool[] = [
    {
      title: "Bulk Crafting",
      blurb: "Importable deck lists to craft a whole set in a few clicks",
      Icon: Hammer,
      to: "/tools/craft",
      extra: wildcards,
    },
    { title: "Event EV", blurb: "Expected gems and packs per event at your win rate", Icon: Coins },
    { title: "Set Completion", blurb: "Packs and wildcards left to complete a set", Icon: Library },
  ];

  return (
    <PageShell subtitle="TOOLS">
      <Container className="pt-4 sm:pt-6 lg:pt-10 pb-10">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-5">
          {tools.map((tool) => (
            <ToolCard key={tool.title} tool={tool} />
          ))}
        </div>
      </Container>
    </PageShell>
  );
}

function ToolCard({ tool }: { tool: Tool }) {
  const live = Boolean(tool.to);
  return (
    <PanelShell
      href={tool.to}
      watermark={tool.Icon}
      watermarkClassName={cn(
        "opacity-30",
        live && "transition-[opacity,color] duration-300 group-hover:opacity-100 group-hover:text-green/[0.14]",
      )}
      className={cn("min-h-[190px]", !live && "opacity-60")}
    >
      <div className="relative flex flex-1 flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <tool.Icon
            size={26}
            className={cn("shrink-0 text-subtle", live && "transition-colors group-hover:text-green")}
          />
          <span
            className={cn(
              "font-display text-text text-[26px] leading-[0.95] tracking-[0.03em]",
              live && "transition-colors group-hover:text-green",
            )}
          >
            {tool.title}
          </span>
        </div>
        <p className="text-subtle text-[14px] leading-[1.55] max-w-[340px]">{tool.blurb}</p>
        <div className="mt-auto flex items-end justify-between gap-3">
          {tool.extra ?? <span />}
          {live ? (
            <span className="inline-flex items-center gap-1.5 font-display text-[15px] tracking-[0.08em] text-green">
              OPEN
              <ArrowRight size={15} />
            </span>
          ) : (
            <span className="font-display text-[13px] tracking-[0.18em] text-muted">COMING SOON</span>
          )}
        </div>
      </div>
    </PanelShell>
  );
}
