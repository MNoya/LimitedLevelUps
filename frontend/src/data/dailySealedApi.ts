import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DEV_AUTH_USER } from "./devAuth";
import { supabase } from "./supabase";
import { MOCK_POOL } from "./fixtures/daily-sealed-trk";
import { servingDay, type Basics, type DailySealedBuild, type DailySealedPool, type PoolCard } from "./dailySealed";

export interface DailySealedDay {
  day: string;
  setCode: string;
  poolNumber: number;
  buildCount: number;
}

export interface OwnBuildInput {
  main: number[];
  basics: Basics;
  colors: string;
}

interface PoolRow {
  day: string;
  set_code: string;
  pool_number: number;
  format: string;
  cards: PoolCard[];
  original_main: number[];
  original_basics?: Basics | null;
  colors: string | null;
  wins: number;
  losses: number;
  build_count: number;
}

interface BuildRow {
  build_key: string;
  main: number[];
  basics: Basics;
  colors: string;
}


export const useDailySealedPool = (day: string | undefined) =>
  useQuery({
    queryKey: ["daily-sealed-pool", day ?? "today"],
    queryFn: () => fetchPool(day),
    staleTime: 60_000,
  });

export const useDailySealedDays = () =>
  useQuery({ queryKey: ["daily-sealed-days"], queryFn: fetchDays, staleTime: 60_000 });

export const useDailySealedBuilds = (day: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: ["daily-sealed-builds", day],
    queryFn: () => fetchBuilds(day!),
    enabled: enabled && !!day,
    staleTime: 30_000,
  });

export const useOwnDailySealedBuild = (day: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: ["daily-sealed-own-build", day],
    queryFn: () => fetchOwnBuild(day!),
    enabled: enabled && !!day,
    staleTime: 0,
  });

export const useSaveDailySealedBuild = (day: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (build: OwnBuildInput) => saveBuild(day!, build),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["daily-sealed-own-build", day] });
      queryClient.invalidateQueries({ queryKey: ["daily-sealed-builds", day] });
      queryClient.invalidateQueries({ queryKey: ["daily-sealed-pool"] });
    },
  });
};

const fetchPool = async (day: string | undefined): Promise<DailySealedPool | null> => {
  if (!supabase) {
    return mockPool();
  }
  let query = supabase.from("public_daily_sealed_pools").select("*");
  query = day ? query.eq("day", day) : query.order("day", { ascending: false }).limit(1);
  const { data, error } = await query;
  if (error) throw error;
  const row = (data as PoolRow[] | null)?.[0];
  return row ? toPool(row) : null;
};

const fetchDays = async (): Promise<DailySealedDay[]> => {
  if (!supabase) {
    const pool = mockPool();
    return [{ day: pool.day, setCode: pool.setCode, poolNumber: pool.poolNumber, buildCount: pool.buildCount }];
  }
  const { data, error } = await supabase
    .from("public_daily_sealed_pools")
    .select("day,set_code,pool_number,build_count")
    .order("day", { ascending: false });
  if (error) throw error;
  return ((data ?? []) as Pick<PoolRow, "day" | "set_code" | "pool_number" | "build_count">[]).map((row) => ({
    day: row.day,
    setCode: row.set_code,
    poolNumber: row.pool_number,
    buildCount: row.build_count,
  }));
};

const fetchBuilds = async (day: string): Promise<DailySealedBuild[]> => {
  if (!supabase) {
    return mockBuilds;
  }
  const { data, error } = await supabase
    .from("public_daily_sealed_builds")
    .select("build_key,main,basics,colors")
    .eq("day", day);
  if (error) throw error;
  return ((data ?? []) as BuildRow[]).map((row) => ({
    buildKey: row.build_key,
    main: row.main,
    basics: row.basics,
    colors: row.colors,
  }));
};

const fetchOwnBuild = async (day: string): Promise<OwnBuildInput | null> => {
  if (!supabase) {
    return mockOwnBuild;
  }
  const { data, error } = await supabase
    .from("daily_sealed_builds")
    .select("main,basics,colors")
    .eq("day", day)
    .limit(1);
  if (error) throw error;
  return ((data ?? []) as OwnBuildInput[])[0] ?? null;
};

const saveBuild = async (day: string, build: OwnBuildInput): Promise<void> => {
  if (!supabase) {
    mockOwnBuild = build;
    mockBuilds = [...mockBuilds.filter((row) => row.buildKey !== "you"), { buildKey: "you", ...build }];
    return;
  }
  const userId = await signedInUserId();
  const { error } = await supabase
    .from("daily_sealed_builds")
    .upsert({ user_id: userId, day, ...build }, { onConflict: "user_id,day" });
  if (error) throw error;
};

const signedInUserId = async (): Promise<string> => {
  const userId = DEV_AUTH_USER?.id ?? (await supabase!.auth.getSession()).data.session?.user.id;
  if (!userId) throw new Error("Not authenticated");
  return userId;
};

const toPool = (row: PoolRow): DailySealedPool => ({
  day: row.day,
  setCode: row.set_code,
  poolNumber: row.pool_number,
  format: row.format,
  cards: row.cards,
  originalMain: row.original_main ?? [],
  originalBasics: row.original_basics ?? null,
  colors: row.colors,
  wins: row.wins,
  losses: row.losses,
  buildCount: row.build_count,
});

const mockPool = (): DailySealedPool => ({
  day: servingDay(),
  setCode: "TRK",
  poolNumber: 24,
  format: "Sealed",
  cards: MOCK_POOL.map(({ main: _main, ...card }) => card),
  originalMain: MOCK_POOL.flatMap((card, index) => (card.main ? [index] : [])),
  originalBasics: null,
  colors: "UBrg",
  wins: 2,
  losses: 3,
  buildCount: mockBuilds.length,
});

let mockOwnBuild: OwnBuildInput | null = null;
let mockBuilds: DailySealedBuild[] = [
  { buildKey: "a1", main: [], basics: { W: 0, U: 8, B: 9, R: 0, G: 0 }, colors: "UB" },
  { buildKey: "b2", main: [], basics: { W: 8, U: 9, B: 0, R: 0, G: 0 }, colors: "WU" },
  { buildKey: "c3", main: [], basics: { W: 0, U: 0, B: 9, R: 8, G: 0 }, colors: "BRu" },
];
