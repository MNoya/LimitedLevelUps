# Typography

Five semantic font roles. Each is a Tailwind `font-<role>` utility backed by a CSS variable, so swapping the font for a role is one line in `frontend/src/styles.css` `:root` and it changes everywhere.

| Utility | Role | Default font | Use for |
|---------|------|--------------|---------|
| `font-display` | Display | Bebas Neue | Headlines, hero titles, set codes, ranks, big stat values |
| `font-body` | Body | Space Grotesk | Default UI text: names, prose, buttons, most labels (also the page base, so plain text needs no class) |
| `font-num` | Data figures | Hanken Grotesk | Every number that reads as data: win rate, points, trophies, ALSA/ATA, counts, percentages. Tabular figures are baked in, so columns always align |
| `font-mono` | Mono label | JetBrains Mono | Terminal-flavored text that is NOT a number: countdowns, "UPDATED 4mo ago", "Results in 10 days", meta labels |
| `font-serif` | Editorial | Spectral | Flavor text: draft-log notes, quotes |

## Swapping a font

Edit one line in `frontend/src/styles.css`:

```css
:root {
  --font-display: "Bebas Neue", sans-serif;
  --font-body: "Space Grotesk", Inter, sans-serif;
  --font-num: "Hanken Grotesk", sans-serif;
  --font-mono: "JetBrains Mono", monospace;
  --font-serif: "Spectral", Georgia, serif;
}
```

Load the new family in `frontend/index.html`, change its `--font-*` line, done. The Tailwind tokens in `tailwind.config.ts` only reference the vars.

## The number vs mono rule

`font-num` and `font-mono` are the pair that used to be conflated. The line: a figure that reads as data goes to `font-num`; text that happens to look terminal-ish but carries words ("Results in 10 days", "#3 of 20", "12 picked", avatar initials) stays on `font-mono`. Numbers get the clean, presence-carrying figures; labels keep the mono texture.
