// Registered custom cube formats, mirrored from CUSTOM_FORMATS in bot/services/pod_format.py.
// The bot owns the canonical mapping; keep the cube ids and labels here in sync when it changes.

interface PodCustomFormat {
  code: string;
  label: string;
  cubeId: string;
}

const CUSTOM_FORMATS: PodCustomFormat[] = [
  { code: "PEASANT", label: "Peasant Cube", cubeId: "DaneeliusPeasantAllStars" },
  { code: "MEMA", label: "Middle-Earth Masters", cubeId: "MEMA" },
  { code: "SAMP", label: "samp Cube", cubeId: "samp" },
];

const BY_CODE = new Map(CUSTOM_FORMATS.map((f) => [f.code, f]));

function customFormat(code: string | undefined): PodCustomFormat | undefined {
  return code ? BY_CODE.get(code.toUpperCase()) : undefined;
}

export function cubeCobraUrl(code: string | undefined): string | null {
  const fmt = customFormat(code);
  return fmt ? `https://cubecobra.com/cube/list/${fmt.cubeId}` : null;
}

export function customFormatLabel(code: string | undefined): string | undefined {
  return customFormat(code)?.label;
}
