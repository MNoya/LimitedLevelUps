export function formatEventDays(event: { startDate: string; endDate: string }, withYear: boolean): string {
  const start = new Date(`${event.startDate}T12:00:00Z`);
  const end = new Date(`${event.endDate}T12:00:00Z`);
  const month = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
  const startYear = start.getUTCFullYear();
  const endYear = end.getUTCFullYear();
  const endSuffix = !withYear && startYear === endYear ? "" : `, ${endYear}`;
  const startLabel = `${month.format(start)} ${start.getUTCDate()}${startYear === endYear ? "" : `, ${startYear}`}`;
  const endMonth = month.format(start) === month.format(end) && startYear === endYear ? "" : `${month.format(end)} `;
  return `${startLabel} - ${endMonth}${end.getUTCDate()}${endSuffix}`;
}

export function proPlayTabLabel(event: { shortName: string }): string {
  return event.shortName.replace(/^Pro Tour /, "PT ");
}
