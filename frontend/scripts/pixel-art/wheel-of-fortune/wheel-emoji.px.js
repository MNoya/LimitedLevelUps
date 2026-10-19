pal({
  k: "#1a120b",
  e: "#5a3a1e",
  W: "#94693a",
  w: "#bd8f57",
  l: "#e2bd84",
  r: "#d23a33",
  R: "#7d1c18",
  g: "#f2b933",
  o: "#f4e9cc",
  s: "#a3b0ba",
  F: "#ff00ff",
})

const CX = 11
const CY = 14
const TAU = Math.PI * 2
const SYMBOLS = ["g", "r", "s", "o"]
const RING = []
for (let j = -8; j <= 8; j++) {
  for (let i = -8; i <= 8; i++) {
    const d = Math.hypot(i + 0.5, j + 0.5)
    if (d >= 5 && d < 5.8) {
      RING.push({ x: CX + i, y: CY + j, angle: Math.atan2(j + 0.5, i + 0.5) })
    }
  }
}
RING.sort((a, b) => a.angle - b.angle)

const ringIndexNear = (angle) => {
  let best = 0
  let bestGap = Infinity
  RING.forEach((point, index) => {
    const gap = Math.abs(Math.atan2(Math.sin(point.angle - angle), Math.cos(point.angle - angle)))
    if (gap < bestGap) {
      bestGap = gap
      best = index
    }
  })
  return best
}

anim("wheel_emoji", { w: 23, h: 25, frames: 32, fps: 32 }, (c) => {
  const turn = c.phase * TAU
  const wedge = TAU / 8
  c.circ(CX, CY, 10, "k")
  c.circ(CX, CY, 9, "e")
  c.circ(CX, CY, 8, "F")
  for (let y = 0; y < c.h; y++) {
    for (let x = 0; x < c.w; x++) {
      if (!c.is(x, y, "F")) {
        continue
      }
      const dx = x - CX
      const dy = y - CY
      const a = (((Math.atan2(dy, dx) - turn) % TAU) + TAU) % TAU
      const light = Math.floor(a / wedge) % 2 === 0
      const lit = dx + dy <= -4
      if (light) {
        c.px(x, y, lit ? "l" : "w")
      } else {
        c.px(x, y, lit ? "w" : "W")
      }
    }
  }
  const step = Math.round(c.phase * RING.length)
  for (let n = 0; n < 4; n++) {
    const start = ringIndexNear((n * 2 + 0.5) * wedge)
    const point = RING[(start + step) % RING.length]
    c.rect(point.x, point.y, 2, 2, SYMBOLS[n])
  }
  c.rect(CX - 1, CY - 1, 3, 3, "k")
  c.px(CX, CY, "r")
  c.poly([7, 0, 16, 0, 11.5, 7], "k")
  c.poly([8, 1, 15, 1, 11.5, 5.5], "r")
  c.hline(9, 1, 3, "R")
})
