// Win-rate presentation helpers shared by the card table and the archetype panel: a diverging color
// around 50% and a Wilson score interval so a low sample reads as a wide, uncertain band.

export interface Interval {
  lo: number;
  hi: number;
}

export function wilsonInterval(p: number, n: number, z = 1.96): Interval | null {
  if (n <= 0) {
    return null;
  }
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const center = (p + z2 / (2 * n)) / denom;
  const margin = (z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom;
  return { lo: Math.max(0, center - margin), hi: Math.min(1, center + margin) };
}

const GOOD = [92, 201, 141];
const NEUTRAL = [200, 207, 221];
const BAD = [224, 106, 106];
const MUTED = "rgb(122,131,149)";
const SATURATE_AT = 0.07;

function lerp(a: number[], b: number[], t: number): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

export function winRateColor(p: number | null): string {
  if (p == null) {
    return MUTED;
  }
  const t = Math.max(-1, Math.min(1, (p - 0.5) / SATURATE_AT));
  return t >= 0 ? lerp(NEUTRAL, GOOD, t) : lerp(NEUTRAL, BAD, -t);
}
