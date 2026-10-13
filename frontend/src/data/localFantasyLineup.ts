export type LocalLineup = Partial<Record<string, number>>;

export function readLocalLineup(eventCode: string): LocalLineup {
  try {
    const raw = localStorage.getItem(storageKey(eventCode));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function writeLocalLineup(eventCode: string, lineup: LocalLineup) {
  localStorage.setItem(storageKey(eventCode), JSON.stringify(lineup));
}

export function clearLocalLineup(eventCode: string) {
  localStorage.removeItem(storageKey(eventCode));
}

function storageKey(eventCode: string) {
  return `fantasy-lineup-${eventCode}`;
}
