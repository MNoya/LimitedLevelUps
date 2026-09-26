import { useSearchParams, type To } from "react-router-dom";

export const useSearchParamHref = (allValue: string) => {
  const [searchParams] = useSearchParams();
  return (key: string, value: string): To => {
    const next = new URLSearchParams(searchParams);
    if (value === allValue) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    return { search: next.toString() };
  };
};
