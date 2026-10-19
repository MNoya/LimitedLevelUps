pal({
  k: "#1a120b",
  S: "#05070a",
  L: "#fff3cf",
  l: "#f6c95e",
  m: "#cf8e2c",
  e: "#5a3a1e",
  W: "#94693a",
  w: "#bd8f57",
  b: "#e2bd84",
  r: "#d23a33",
  R: "#7d1c18",
  g: "#f2b933",
  s: "#a3b0ba",
  o: "#f4e9cc",
  F: "#ff00ff",
})

const GLYPHS = {
  W: ["XX......XX", "XX......XX", "XX......XX", "XX..XX..XX", "XX..XX..XX", "XX.XXXX.XX", "XXXX..XXXX", "XXX....XXX", "XX......XX"],
  h: ["XX....", "XX....", "XX....", "XXXXX.", "XXX.XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX"],
  e: ["", "", "", ".XXXX.", "XX..XX", "XXXXXX", "XX....", "XX..XX", ".XXXX."],
  l: ["XX", "XX", "XX", "XX", "XX", "XX", "XX", "XX", "XX"],
  f: ["..XXX", ".XX..", ".XX..", "XXXX.", ".XX..", ".XX..", ".XX..", ".XX..", ".XX.."],
  F: ["XXXXXX", "XX....", "XX....", "XXXXX.", "XX....", "XX....", "XX....", "XX....", "XX...."],
  o: ["", "", "", ".XXXX.", "XX..XX", "XX..XX", "XX..XX", "XX..XX", ".XXXX."],
  r: ["", "", "", "XX.XX", "XXX..", "XX...", "XX...", "XX...", "XX..."],
  t: ["", ".XX.", ".XX.", "XXXX", ".XX.", ".XX.", ".XX.", ".XX.", "..XX"],
  u: ["", "", "", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX.XXX", ".XXXXX"],
  n: ["", "", "", "XXXXX.", "XXX.XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX"],
}
const WORDS = ["Wheel", "*f", "Fortune"]
const TOP = 6
const WHEEL_SIZE = 9
const LETTER_GAP = 1
const WORD_GAP = 5
const ROW_SHADE = ["L", "L", "L", "l", "l", "l", "m", "m", "m"]

const layout = []
let cursor = 2
for (const word of WORDS) {
  for (const ch of word) {
    if (ch === "*") {
      layout.push({ wheel: true, x: cursor })
      cursor += WHEEL_SIZE + LETTER_GAP
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
const HEIGHT = TOP + 9 + 4

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

sprite("wheel_title", { w: WIDTH + 1, h: HEIGHT + 1 }, (c) => {
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
