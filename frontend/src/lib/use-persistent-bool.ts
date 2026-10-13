import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

export function usePersistentBool(key: string, fallback: boolean): [boolean, Dispatch<SetStateAction<boolean>>] {
  const [value, setValue] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return fallback;
    }
    const stored = window.localStorage.getItem(key);
    return stored == null ? fallback : stored === "1";
  });
  useEffect(() => {
    window.localStorage.setItem(key, value ? "1" : "0");
  }, [key, value]);
  return [value, setValue];
}
