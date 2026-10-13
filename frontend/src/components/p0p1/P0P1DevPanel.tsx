import { DevStatePanel, DevStateSection } from "../DevStatePanel";
import {
  useP0P1DevPreset,
  setP0P1DevPreset,
  P0P1_DEV_PRESETS,
  useP0P1DevSelfPlacement,
  setP0P1DevSelfPlacement,
  P0P1_DEV_SELF_PLACEMENTS,
} from "../../data/p0p1DevState";

export function P0P1DevPanel() {
  const preset = useP0P1DevPreset();
  const selfPlacement = useP0P1DevSelfPlacement();
  return (
    <DevStatePanel
      title="DEV - P0P1 STATE"
      options={P0P1_DEV_PRESETS}
      value={preset}
      onChange={setP0P1DevPreset}
      liveValue="live"
    >
      {preset === "finalScoring" ? (
        <DevStateSection
          title="DEV - YOUR ROW"
          options={P0P1_DEV_SELF_PLACEMENTS}
          value={selfPlacement}
          onChange={setP0P1DevSelfPlacement}
        />
      ) : null}
    </DevStatePanel>
  );
}
