pal({
  k: "#1a120b",
  L: "#fff3cf",
  l: "#f6c95e",
  m: "#cf8e2c",
  e: "#5a3a1e",
  W: "#94693a",
  o: "#ffffff",
})

sprite("_trophy", { outline: "k" }, `
  ..LLLLLLL..
  llmLllllmll
  l.mLllllm.l
  l.mLllllm.l
  .lmLllllml.
  ...mLllm...
  ....mlm....
  .....l.....
  .....l.....
  ....mlm....
  ...LLLLL...
  ...mmmmm...
  ..WWWWWWW..`)

sprite("_trophy_clean", { outline: "k" }, `
  ..LLLLLLL..
  llmllllllll
  l.mllllll.l
  l.mllllll.l
  .lmlllllml.
  ...mlllm...
  ....mlm....
  .....l.....
  .....l.....
  ....mlm....
  ...LLLLL...
  ...mmmmm...
  ..WWWWWWW..`)

const FRAMES = 24
const GOLD = ["L", "l", "m"]

const shiningTrophy = (part) => (c) => {
  c.stamp(part, 0, 0)
  const sweep = c.frame - 2
  if (sweep < 0 || sweep > 22) {
    return
  }
  for (let y = 0; y < c.h; y++) {
    for (let x = 0; x < c.w; x++) {
      const band = x + y - sweep
      const onGold = GOLD.some((key) => c.is(x, y, key))
      if (onGold && (band === 0 || band === 1)) {
        c.px(x, y, band === 0 ? "o" : "L")
      }
    }
  }
}

anim("trophy_emoji", { w: 13, h: 15, frames: FRAMES, fps: 12 }, shiningTrophy("_trophy"))
anim("trophy_clean_emoji", { w: 13, h: 15, frames: FRAMES, fps: 12 }, shiningTrophy("_trophy_clean"))
