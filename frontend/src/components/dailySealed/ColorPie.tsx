import { Pips } from "../ManaPips";
import { colorSplashRows } from "../../data/dailySealedBreakdown";
import type { DailySealedBuild } from "../../data/dailySealed";

const PIE_ORDER = ["W", "U", "B", "R", "G"];
const PIE_SIZE = 220;
const NODE_RADIUS = 22;

export const ColorPie = ({ builds, size = PIE_SIZE }: { builds: DailySealedBuild[]; size?: number }) => {
  const center = size / 2;
  const radius = center - NODE_RADIUS - 2;
  const points = new Map(
    PIE_ORDER.map((color, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      return [color, { x: center + radius * Math.cos(angle), y: center + radius * Math.sin(angle) }];
    }),
  );
  const links = colorLinks(builds);
  const presence = new Map(colorSplashRows(builds).map((row) => [row.color as string, row.main + row.splash]));
  let mostDecks = 1;
  for (const link of links) {
    mostDecks = Math.max(mostDecks, link.decks);
  }
  return (
    <div className="flex justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Colors played together">
        {links.map((link) => {
          const a = points.get(link.from)!;
          const b = points.get(link.to)!;
          return (
            <g key={`${link.from}${link.to}${link.splash}`}>
              <title>{`${link.from}${link.to}: ${link.decks} of ${builds.length}${link.splash ? " as a splash" : ""}`}</title>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#2ee85c"
                strokeOpacity={link.splash ? 0.7 : 0.35 + 0.6 * (link.decks / mostDecks)}
                strokeWidth={link.splash ? 2 : 2 + 12 * (link.decks / mostDecks)}
                strokeDasharray={link.splash ? "4 5" : undefined}
                strokeLinecap="round"
              />
            </g>
          );
        })}
        {PIE_ORDER.map((color) => {
          const point = points.get(color)!;
          return (
            <g key={color}>
              <circle cx={point.x} cy={point.y} r={NODE_RADIUS} fill="#14181f" stroke="#3b4458" />
              <foreignObject x={point.x - 14} y={point.y - 16} width={28} height={32}>
                <div className="flex flex-col items-center">
                  <Pips colors={color} size={15} />
                  <span className="font-num text-[12px] leading-none text-text">{presence.get(color) ?? 0}</span>
                </div>
              </foreignObject>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

const colorLinks = (builds: DailySealedBuild[]) => {
  const links = new Map<string, { from: string; to: string; decks: number; splash: boolean }>();
  const add = (from: string, to: string, splash: boolean) => {
    const [a, b] = PIE_ORDER.indexOf(from) < PIE_ORDER.indexOf(to) ? [from, to] : [to, from];
    const key = `${a}${b}${splash}`;
    const link = links.get(key) ?? { from: a, to: b, decks: 0, splash };
    link.decks += 1;
    links.set(key, link);
  };
  for (const build of builds) {
    const main = build.colors.split("").filter((letter) => letter === letter.toUpperCase());
    const splash = build.colors.split("").filter((letter) => letter !== letter.toUpperCase()).map((letter) => letter.toUpperCase());
    for (let i = 0; i < main.length; i += 1) {
      for (let k = i + 1; k < main.length; k += 1) {
        add(main[i], main[k], false);
      }
      for (const color of splash) {
        add(main[i], color, true);
      }
    }
  }
  return [...links.values()].sort((a, b) => Number(b.splash) - Number(a.splash));
};
