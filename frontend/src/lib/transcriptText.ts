import type { TranscriptSegment } from "../data/transcript";

// Caption speaker-change markers (>>) are a display artifact; strip for reading and export.
export const stripSpeakerTurns = (text: string): string =>
  text
    .replace(/\s*>{2,}\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();

export function transcriptToText(title: string, segments: TranscriptSegment[]): string {
  const lines: string[] = [title];
  for (const segment of segments) {
    const text = stripSpeakerTurns(segment.text);
    if (segment.heading) {
      lines.push("", `# ${segment.heading}`, "", text);
    } else if (segment.subheading) {
      lines.push("", `## ${segment.subheading}`, "", text);
    } else {
      lines.push(text);
    }
  }
  return `${lines.join("\n").replace(/\n{3,}/g, "\n\n").trim()}\n`;
}

export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
