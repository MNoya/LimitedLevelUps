import React from "react";
import { cubeBoardCode, CUBE_VARIANTS } from "../data/cubeVariants";
import { cn } from "../lib/utils";

// LLU brand mark — the user-supplied logo PNG. Bypasses Vite's asset pipeline
// by living in /public so the public URL is deterministic across dev / prod.
export const LLU_LOGO_SRC = `${import.meta.env.BASE_URL}llu-logo-transparent.png`;

export function ALogo({ size = 32 }: { size?: number }) {
  return (
    <img
      src={LLU_LOGO_SRC}
      alt="Limited Level-Ups"
      style={{ height: size, width: "auto" }}
      className="block"
    />
  );
}

// Wordmark — Bebas Neue "LIMITED LEVEL-UPS" + the section label. Mobile (`sm`)
// lays them on one row split by a vertical hairline; wider sizes stack the
// section label under the title so the brand stays narrow next to the nav.
export function AWordmark({
  size = "md",
  subtitle = "LEADERBOARD",
  subtitleShort,
}: {
  size?: "sm" | "md" | "lg";
  subtitle?: string;
  subtitleShort?: string;
}) {
  if (size === "sm") {
    return (
      <div className="flex items-center font-display whitespace-nowrap" style={{ gap: 10 }}>
        <span className="text-text leading-none" style={{ fontSize: 18, letterSpacing: "0.07em" }}>
          LIMITED LEVEL-UPS
        </span>
        <span className="bg-border2 shrink-0" style={{ width: 1, height: 16 }} />
        <span className="text-green leading-none" style={{ fontSize: 15, letterSpacing: "0.14em" }}>
          {subtitleShort ?? subtitle}
        </span>
      </div>
    );
  }
  const title = size === "lg" ? 26 : 18;
  const sub = size === "lg" ? 14 : 10;
  return (
    <div className="flex flex-col font-display whitespace-nowrap" style={{ lineHeight: 0.95 }}>
      <span className="text-text" style={{ fontSize: title, letterSpacing: "0.09em" }}>
        LIMITED LEVEL-UPS
      </span>
      <span className="text-green" style={{ fontSize: sub, letterSpacing: "0.28em", marginTop: 4 }}>
        {subtitle}
      </span>
    </div>
  );
}

// Top-left / bottom-right chamfer, shared by anything drawn concentric with an avatar
export const AVATAR_CLIP = "polygon(8% 0, 100% 0, 100% 92%, 92% 100%, 0 100%, 0 8%)";

// Avatar with chamfered corners. When `avatarUrl` is null (the default at launch
// per spec §"Avatar plumbing"), falls back to two-letter initials.
export function AAvatar({
  displayName,
  avatarUrl,
  size = 36,
  green = false,
}: {
  displayName: string;
  avatarUrl?: string | null;
  size?: number;
  green?: boolean;
}) {
  const [failed, setFailed] = React.useState(false);
  const initials = displayName
    .split(/[\s\-_().]+/)
    .filter(Boolean)
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  if (avatarUrl && !failed) {
    return (
      <img
        src={avatarUrl}
        alt={displayName}
        width={size}
        height={size}
        onError={() => setFailed(true)}
        className="block shrink-0 object-cover"
        style={{ clipPath: AVATAR_CLIP }}
      />
    );
  }
  return (
    <div
      className={cn(
        "bg-surface2 border flex items-center justify-center font-display tracking-[0.05em] shrink-0",
        green ? "border-green text-green" : "border-border2 text-text",
      )}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.45,
        clipPath: AVATAR_CLIP,
      }}
    >
      {initials}
    </div>
  );
}


// Trophy glyph — the marquee stat in this community (spec).
export function Trophy({
  size = 12,
  color,
  className,
}: {
  size?: number;
  color?: string;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      className={className ? `shrink-0 ${className}` : "shrink-0"}
      style={color ? { color } : undefined}
      aria-hidden="true"
    >
      <path
        d="M4 2h8v3a4 4 0 0 1-8 0V2zm-2 1h2v2a4 4 0 0 1-2-2zm10 0h2a4 4 0 0 1-2 2V3zM6 9h4v2H9v2h2v1H5v-1h2v-2H6V9z"
        fill={color ?? "currentColor"}
      />
    </svg>
  );
}

// Round-pts — the spec's score is whole points in display.
export const fmtPts = (n: number) => Math.round(n).toLocaleString("en-US");

// Set keyrune glyph wrapper (uses keyrune.css from index.html).
// Reserves a square box of `size` so swapping codes doesn't reflow neighbours
const KEYRUNE_OVERRIDES: Record<string, string> = {
  CUBE: "pz1",
  PEASANT: "pz1",
  IPA: "inv",
};

// Boards whose symbol is a bespoke PNG rather than a Keyrune font glyph, rendered as an <img>
const IMG_GLYPH_SRC: Record<string, string> = {
  EVG: LLU_LOGO_SRC,
  MEMA: `${import.meta.env.BASE_URL}set-symbols/mema.png`,
};

export function keyruneClass(code: string): string {
  return KEYRUNE_OVERRIDES[code] ?? code.toLowerCase();
}

// Cube boards borrow icons from both fonts, so each variant declares its own "<font>:<glyph>" spec.
// A season board takes the run's own icon: the set it ran under, or the plane a cube week drafted.
const CUBE_BOARD_GLYPHS: Record<string, string> = Object.fromEntries([
  ...CUBE_VARIANTS.map((v) => [cubeBoardCode(v.slug), v.glyph]),
  ...CUBE_VARIANTS.flatMap((v) =>
    (v.seasons ?? []).map((s) => [cubeBoardCode(s.code), s.glyph ?? `keyrune:${s.code.toLowerCase()}`]),
  ),
]);

// Mana icons ink out their whole em box where Keyrune set symbols keep padding, so they render a
// touch smaller to sit at the same visual weight in the square SetGlyph reserves.
const MANA_GLYPH_SCALE = 0.82;

// Icons for groupings that are not sets, in the same "<font>:<glyph>" form the cube registry uses
const NAMED_GLYPHS: Record<string, string> = {
  FLASHBACK: "mana:flashback",
};

export function glyphSpec(code: string): { className: string; scale: number } {
  const spec = NAMED_GLYPHS[code] ?? CUBE_BOARD_GLYPHS[code];
  if (spec === undefined) {
    return { className: `ss ss-${keyruneClass(code)}`, scale: 1 };
  }
  const [font, glyph] = spec.split(":");
  if (font === "mana") {
    return { className: `ms ms-${glyph}`, scale: MANA_GLYPH_SCALE };
  }
  return { className: `ss ss-${glyph}`, scale: 1 };
}

// Custom pod cube formats have no Keyrune glyph of their own; fall back to the generic cube symbol
// unless the code carries its own override or bespoke image.
export function setGlyphCode(set: { code: string; custom?: boolean; glyphCode?: string }): string {
  if (set.glyphCode) {
    return set.glyphCode;
  }
  if (set.custom && !(set.code in KEYRUNE_OVERRIDES) && !(set.code in IMG_GLYPH_SRC)) {
    return "CUBE";
  }
  return set.code;
}

export function SetGlyph({ code, size = 18, className = "text-white" }: { code: string; size?: number; className?: string }) {
  const glyph = glyphSpec(code);
  return (
    <span
      className="inline-flex items-center justify-center shrink-0 overflow-visible"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      {IMG_GLYPH_SRC[code] ? (
        <img src={IMG_GLYPH_SRC[code]} alt="" style={{ width: size, height: size }} className="block object-contain" />
      ) : (
        <i className={`${glyph.className} ${className}`} style={{ fontSize: size * glyph.scale, lineHeight: 1 }} />
      )}
    </span>
  );
}
