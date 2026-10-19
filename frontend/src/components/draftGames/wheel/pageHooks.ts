import { useEffect, useLayoutEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export function useNoScrollGutter() {
  useLayoutEffect(() => {
    const html = document.documentElement;
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = "";
    };
  }, []);
}

export function useGuideHash(hash: string): [boolean, () => void, () => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const open = location.hash === `#${hash}`;
  const openGuide = () => navigate({ search: location.search, hash });
  const closeGuide = () => navigate({ search: location.search, hash: "" }, { replace: true });
  return [open, openGuide, closeGuide];
}

export function useTouchVerb(): string {
  const [verb] = useState(() => (window.matchMedia("(pointer: coarse)").matches ? "Tap" : "Click"));
  return verb;
}

export function releaseFocus() {
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }
}
