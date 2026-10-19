pal({
  k: "#1a120b",
  U: "#5b8fd9",
  u: "#2f5aa8",
  n: "#1d3770",
  s: "#0b0f1c",
  h: "#e8b98a",
  y: "#f6c95e",
  Y: "#cf8e2c",
  i: "#9ff3ff",
  o: "#ffffff",
  g: "#f6c95e",
  q: "#5fd4f5",
  p: "#c47cf0",
  G: "#a86a1c",
  Q: "#2389b8",
  P: "#7a3cb0",
})

sprite("_mage", { mx: "c", outline: "k" }, `
  .........u
  ........uU
  .......uuU
  ......uuUU
  .h....usss
  .hh..uusis
  ..nn.uusss
  ...nnuuuss
  ....nnuuuu
  .....nuuUy
  .....nuuUy
  ....nnuuUy
  ....nuuuUy
  ...nnuuuUy
  ...nuuuuUy
  ..nnuuuuUy
  ..nuuuuuUy
  .nnuuuuuUy
  .nuuuuuuUy
  nnuuuuuuUy
  YYYYYYYYYY`)

const FRAMES = 24
const ORBS = [
  { light: "g", dark: "G" },
  { light: "q", dark: "Q" },
  { light: "p", dark: "P" },
]
const LEFT_HAND = 8
const RIGHT_HAND = 24
const HAND_Y = 17
const ARC_HEIGHT = 13
const THROW_SHARE = 0.72

const orbPosition = (t) => {
  const span = RIGHT_HAND - LEFT_HAND
  if (t < THROW_SHARE) {
    const u = t / THROW_SHARE
    return [LEFT_HAND + span * u, HAND_Y - ARC_HEIGHT * Math.sin(Math.PI * u)]
  }
  const u = (t - THROW_SHARE) / (1 - THROW_SHARE)
  return [RIGHT_HAND - span * u, HAND_Y + 2 * Math.sin(Math.PI * u)]
}

anim("mage_emoji", { w: 33, h: 37, frames: FRAMES, fps: 12 }, (c) => {
  const placed = ORBS.map((orb, n) => {
    const t = (c.phase + n / 3) % 1
    const [x, y] = orbPosition(t)
    return { orb, x: Math.round(x) - 2, y: Math.round(y) - 2, behind: t >= THROW_SHARE }
  })
  const drawOrb = ({ orb, x, y }) => {
    c.rect(x + 1, y, 3, 5, "k")
    c.rect(x, y + 1, 5, 3, "k")
    c.rect(x + 1, y + 1, 3, 3, orb.light)
    c.px(x + 3, y + 3, orb.dark)
    c.px(x + 2, y + 3, orb.dark)
    c.px(x + 3, y + 2, orb.dark)
    c.px(x + 1, y + 1, "o")
  }
  placed.filter((p) => p.behind).forEach(drawOrb)
  c.stamp("_mage", 6, 14)
  placed.filter((p) => !p.behind).forEach(drawOrb)
  glow("gqpi", { r: 3, strength: 0.5 })
})
