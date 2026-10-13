import { useSyncExternalStore } from "react";

export const devToolsEnabled = import.meta.env.DEV && typeof window !== "undefined";

export type DevPresetStore<T extends string> = {
  get: () => T;
  set: (value: T) => void;
  useValue: () => T;
};

export function createDevPresetStore<T extends string>(
  storageKey: string,
  values: readonly T[],
  fallback: T,
  enabled = devToolsEnabled,
): DevPresetStore<T> {
  const listeners = new Set<() => void>();
  let current = readStored();

  function readStored(): T {
    if (!enabled) {
      return fallback;
    }
    const stored = window.localStorage.getItem(storageKey) as T | null;
    return stored !== null && values.includes(stored) ? stored : fallback;
  }

  function subscribe(notify: () => void) {
    listeners.add(notify);
    return () => listeners.delete(notify);
  }

  return {
    get: () => current,
    set: (value) => {
      current = value;
      window.localStorage.setItem(storageKey, value);
      listeners.forEach((notify) => notify());
    },
    useValue: () => useSyncExternalStore(subscribe, () => current, () => fallback),
  };
}
