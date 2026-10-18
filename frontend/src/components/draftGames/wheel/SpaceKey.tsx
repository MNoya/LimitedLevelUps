import { cn } from "../../../lib/utils";

export function SpaceKey() {
  const spaceBar = cn(
    "hidden w-24 place-items-center border-2 border-b-[5px] border-[#1a120b] bg-[#fff8e6] pt-1.5 pb-1",
    "font-num text-sm font-bold leading-none text-[#1a120b] shadow-[inset_0_-3px_0_#d9a441] lg:grid",
  );
  return <kbd className={spaceBar}>Space</kbd>;
}
