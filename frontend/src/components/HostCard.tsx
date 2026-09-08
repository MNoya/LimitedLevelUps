import { AAvatar } from "./Brand";
import { ExternalLink } from "./Icons";
import type { Host } from "../data/site";

export function HostCard({ host }: { host: Host }) {
  return (
    <div className="bg-surface border border-border p-5 flex gap-4">
      <AAvatar displayName={host.name} size={56} green />
      <div className="min-w-0">
        <div className="font-display text-text text-[17px] tracking-[0.04em]">
          {host.name} <span className="text-muted">— {host.handle}</span>
        </div>
        <div className="font-mono text-[11px] tracking-[0.12em] text-green uppercase mt-1">{host.role}</div>
        <p className="text-muted text-[13px] leading-[1.6] mt-2">{host.bio}</p>
        <div className="flex flex-wrap gap-2 mt-3">
          {host.links.map((link) => (
            <a
              key={link.label}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 border border-border2 px-2.5 py-1 font-mono text-[11px] tracking-[0.08em] text-subtle no-underline transition-colors hover:border-green hover:text-green"
            >
              {link.label}
              <ExternalLink size={11} />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
