import { useLayoutEffect, useState, type RefObject } from "react";

export const useWidth = (ref: RefObject<HTMLElement | null>) => useMeasured(ref, (element) => element.clientWidth);

export const useHeight = (ref: RefObject<HTMLElement | null>) => useMeasured(ref, (element) => element.offsetHeight);

const useMeasured = (ref: RefObject<HTMLElement | null>, read: (element: HTMLElement) => number) => {
  const [size, setSize] = useState(0);
  const [element, setElement] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (ref.current !== element) {
      setElement(ref.current);
    }
  });
  useLayoutEffect(() => {
    if (!element) {
      return;
    }
    setSize(read(element));
    const observer = new ResizeObserver(() => setSize(read(element)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return size;
};
