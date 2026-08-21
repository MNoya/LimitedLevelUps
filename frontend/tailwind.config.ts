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
        display: ["'Bebas Neue'", "sans-serif"],
        body: ["'Space Grotesk'", "Inter", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
        spectral: ["Spectral", "Georgia", "serif"],
      },
      fontVariantNumeric: {
        tabular: ["tabular-nums"],
      },
      keyframes: {
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
      },
      animation: {
        pulse: "pulse 1.4s infinite",
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
