import type { Config } from "tailwindcss";

// Theme tokens from src/theme.ts ported to Tailwind. Surfaces, accents, and
// fonts are exposed as utility classes (e.g. `bg-bg`, `text-muted`,
// `font-display`) so component code reads as "background = bg" instead of
// "background = #0a0c10".
//
// Where shadcn primitives expect HSL CSS vars (--primary, etc.), we mirror the
// values into vars so future shadcn components Just Work.

const config: Config = {
  darkMode: "class",
  future: { hoverOnlyWhenSupported: true },
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0c10",
        surface: "#14181f",
        surface2: "#1d2330",
        border: "#2a3142",
        border2: "#3b4458",
        text: "#e6ecf5",
        subtle: "#b8c0d0",
        muted: "#7a8395",
        dim: "#4a5163",

        green: {
          DEFAULT: "#2ee85c",
          2: "#1fd14c",
        },
        teal: "#22d4c0",
        gold: "#ffc63a",
        red: "#ff5e5e",
        cyan: "#00e5ff",
        magenta: "#ff2cdf",
        blue: "#4aa8ff",
        indigo: "#6d6cf5",
        purple: "#a98eff",
        orange: "#ff9d42",
        pink: "#ff79c6",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        num: ["var(--font-num)", { fontFeatureSettings: '"tnum"' }],
        mono: ["var(--font-mono)"],
        serif: ["var(--font-serif)"],
      },
      fontVariantNumeric: {
        tabular: ["tabular-nums"],
      },
      keyframes: {
        slotPulse: {
          "50%": { filter: "drop-shadow(0 0 3px rgba(246, 201, 94, 0.4))" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeOut: {
          "0%": { opacity: "1" },
          "100%": { opacity: "0" },
        },
        fadeUpIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { transform: "translateX(100%)" },
          "100%": { transform: "translateX(0)" },
        },
        slideInUp: {
          "0%": { transform: "translateY(100%)" },
          "100%": { transform: "translateY(0)" },
        },
        loadingBar: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(400%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        drawCheck: {
          "0%": { strokeDashoffset: "24" },
          "100%": { strokeDashoffset: "0" },
        },
        chipExtend: {
          "0%": { maxWidth: "0", opacity: "0" },
          "100%": { maxWidth: "12em", opacity: "1" },
        },
        chipRingFromGold: {
          "0%": { boxShadow: "0 0 0 1px #f6c95e, 2px 2px 0 1px #05070a" },
        },
        chipFillFromGold: {
          "0%": { backgroundColor: "#f6c95e", color: "#1a120b" },
        },
        stamp: {
          "0%": { opacity: "0", transform: "scale(1.7)" },
          "60%": { opacity: "1", transform: "scale(0.92)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        flipIn: {
          "0%": { transform: "rotateX(90deg)" },
          "100%": { transform: "rotateX(0deg)" },
        },
        dealIn: {
          "0%": { opacity: "0", transform: "translateY(-10px) scale(0.97)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        rowIn: {
          "0%": { opacity: "0", translate: "-10px 0" },
          "100%": { opacity: "1", translate: "0 0" },
        },
        nudge: {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.06)" },
        },
        cardDeal: {
          "0%": { opacity: "0", transform: "translateY(-28px) rotateX(35deg) scale(0.92)" },
          "70%": { opacity: "1", transform: "translateY(2px) rotateX(0deg) scale(1.01)" },
          "100%": { opacity: "1", transform: "translateY(0) rotateX(0deg) scale(1)" },
        },
        scoredGlow: {
          "0%": { boxShadow: "0 0 0 0 rgba(46, 232, 92, 0)" },
          "40%": { boxShadow: "0 0 26px 6px rgba(46, 232, 92, 0.55)" },
          "100%": { boxShadow: "0 0 10px 2px rgba(46, 232, 92, 0.4)" },
        },
        missShake: {
          "0%, 100%": { transform: "translateX(0)" },
          "20%": { transform: "translateX(-4px) rotate(-0.6deg)" },
          "40%": { transform: "translateX(4px) rotate(0.6deg)" },
          "60%": { transform: "translateX(-3px)" },
          "80%": { transform: "translateX(2px)" },
        },
        artDrift: {
          "0%": { transform: "scale(1.04) translate(-1.5%, -1%)" },
          "100%": { transform: "scale(1.04) translate(1.5%, 1%)" },
        },
        softPulse: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(46, 232, 92, 0.35)" },
          "50%": { boxShadow: "0 0 0 6px rgba(46, 232, 92, 0)" },
        },
        liveHalo: {
          "0%": { boxShadow: "0 0 8px rgba(46, 232, 92, 0.8), 0 0 0 0 rgba(46, 232, 92, 0.75)" },
          "50%": { boxShadow: "0 0 4px rgba(46, 232, 92, 0.4), 0 0 0 9px rgba(46, 232, 92, 0)" },
          "100%": { boxShadow: "0 0 8px rgba(46, 232, 92, 0.8), 0 0 0 0 rgba(46, 232, 92, 0)" },
        },
      },
      animation: {
        slotPulse: "slotPulse 2.4s ease-in-out infinite",
        pulse: "pulse 1.4s infinite",
        liveHalo: "liveHalo 1.6s ease-out infinite",
        chipExtend: "chipExtend 360ms cubic-bezier(0.22, 1, 0.36, 1) both",
        chipRingFromGold: "chipRingFromGold 300ms ease-out backwards",
        chipFillFromGold: "chipFillFromGold 300ms ease-out backwards",
        stamp: "stamp 260ms cubic-bezier(0.34, 1.56, 0.64, 1) both",
        flipIn: "flipIn 260ms cubic-bezier(0.22, 1, 0.36, 1) both",
        dealIn: "dealIn 240ms cubic-bezier(0.22, 1, 0.36, 1) both",
        rowIn: "rowIn 200ms ease-out both",
        nudge: "nudge 300ms ease-out",
        cardDeal: "cardDeal 420ms cubic-bezier(0.22, 1, 0.36, 1) both",
        scoredGlow: "scoredGlow 700ms ease-out both",
        missShake: "missShake 380ms ease-in-out both",
        softPulse: "softPulse 1.6s ease-out infinite",
        fadeIn: "fadeIn 220ms ease-out both",
        fadeOut: "fadeOut 220ms ease-out both",
        fadeUpIn: "fadeUpIn 260ms ease-out both",
        slideInRight: "slideInRight 280ms cubic-bezier(0.22, 1, 0.36, 1) both",
        slideInUp: "slideInUp 280ms cubic-bezier(0.22, 1, 0.36, 1) both",
        loadingBar: "loadingBar 1.1s ease-in-out infinite",
        marquee: "marquee 40s linear infinite",
        drawCheck: "drawCheck 420ms cubic-bezier(0.65, 0, 0.35, 1) 160ms both",
      },
    },
  },
  plugins: [],
};

export default config;
