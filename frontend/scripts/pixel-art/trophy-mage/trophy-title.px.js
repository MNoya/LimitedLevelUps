pal({
  k: "#1a120b",
  S: "#05070a",
  L: "#fff3cf",
  l: "#f6c95e",
  m: "#cf8e2c",
  K: "#0b1430",
  A: "#e3efff",
  a: "#7fb0f0",
  z: "#4479d0",
  I: "#ffffff",
  i: "#9ff3ff",
  j: "#3fb6e6",
  V: "#e6e9ff",
  v: "#8aa2ff",
  w: "#4a5fd0",
})

const BLUE_STYLES = {
  blue: { L: "A", l: "a", m: "z", k: "K" },
  ice: { L: "I", l: "i", m: "j", k: "K" },
  arcane: { L: "V", l: "v", m: "w", k: "K" },
}

const GLYPHS = {
  T: ["XXXXXXXX", "...XX...", "...XX...", "...XX...", "...XX...", "...XX...", "...XX...", "...XX...", "...XX..."],
  r: ["", "", "", "XX.XX", "XXX..", "XX...", "XX...", "XX...", "XX..."],
  o: ["", "", "", ".XXXX.", "XX..XX", "XX..XX", "XX..XX", "XX..XX", ".XXXX."],
  p: ["", "", "", "XXXXX.", "XXX.XX", "XX..XX", "XX..XX", "XXX.XX", "XXXXX.", "XX....", "XX....", "XX...."],
  h: ["XX....", "XX....", "XX....", "XXXXX.", "XXX.XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX"],
  M: [
    "XX......XX",
    "XXX....XXX",
    "XXXX..XXXX",
    "XX.XXXX.XX",
    "XX..XX..XX",
    "XX......XX",
    "XX......XX",
    "XX......XX",
    "XX......XX",
  ],
  a: ["", "", "", ".XXXX.", "....XX", ".XXXXX", "XX..XX", "XX..XX", ".XXXXX"],
  g: ["", "", "", ".XXXXX", "XX..XX", "XX..XX", "XX..XX", "XX.XXX", ".XXXXX", "....XX", "XX..XX", ".XXXX."],
  e: ["", "", "", ".XXXX.", "XX..XX", "XXXXXX", "XX....", "XX..XX", ".XXXX."],
}
const WORDS = ["Troph*", "Mage"]
const TOP = 3
const TROPHY_WIDTH = 13
const LETTER_GAP = 1
const WORD_GAP = 5
const ROW_SHADE = ["L", "L", "L", "l", "l", "l", "m", "m", "m", "m", "m", "m"]

const layout = []
let cursor = 2
for (const word of WORDS) {
  for (const ch of word) {
    if (ch === "*") {
      layout.push({ trophy: true, x: cursor - 1 })
      cursor += TROPHY_WIDTH - 2 + LETTER_GAP
      continue
    }
    const glyph = GLYPHS[ch]
    const width = Math.max(...glyph.map((row) => row.length))
    layout.push({ glyph, x: cursor })
    cursor += width + LETTER_GAP
  }
  cursor += WORD_GAP - LETTER_GAP
}
const WIDTH = cursor - WORD_GAP + 3
const HEIGHT = TOP + 12 + 2

for (const item of layout) {
  if (item.trophy) {
    console.log(`trophy slot x=${item.x} width=${TROPHY_WIDTH} title=${WIDTH + 1}x${HEIGHT + 1}`)
  }
}

sprite("_title_core", { w: WIDTH, h: HEIGHT, outline: "k" }, (c) => {
  for (const item of layout) {
    if (!item.glyph) {
      continue
    }
    item.glyph.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        if (row[x] === "X") {
          c.px(item.x + x, TOP + y, ROW_SHADE[y])
        }
      }
    })
  }
})

sprite("trophy_title", { w: WIDTH + 1, h: HEIGHT + 1 }, (c) => {
  const shadow = []
  c.stamp("_title_core", 0, 0)
  for (let y = 0; y < c.h; y++) {
    for (let x = 0; x < c.w; x++) {
      if (!c.is(x, y, ".") && c.is(x + 1, y + 1, ".")) {
        shadow.push([x + 1, y + 1])
      }
    }
  }
  for (const [x, y] of shadow) {
    if (c.is(x, y, ".")) {
      c.px(x, y, "S")
    }
  }
})

for (const [style, swap] of Object.entries(BLUE_STYLES)) {
  sprite(`trophy_title_${style}`, { base: "trophy_title", swap })
}
