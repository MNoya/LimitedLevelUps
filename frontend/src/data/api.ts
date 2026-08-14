// Selects the data backend at module-load time via `useSupabase` (driven by
// VITE_DATA_MODE in supabase.ts): real Supabase fetchers, or the fixture-backed
// mock API in mock mode. The hook layer imports from here so it never knows
// which one is live.

import { useSupabase } from "./supabase";

import * as mock from "./mockApi";
import * as real from "./realApi";

const impl = useSupabase ? real : mock;

export const fetchSets = impl.fetchSets;
export const fetchCubeSeasons = impl.fetchCubeSeasons;
export const fetchDbEpisodes = impl.fetchDbEpisodes;
export const fetchRecentDbEpisodes = impl.fetchRecentDbEpisodes;
export const fetchLeaderboard = impl.fetchLeaderboard;
export const fetchTrophyLeaderboard = impl.fetchTrophyLeaderboard;
export const fetchFormatLeaderboard = impl.fetchFormatLeaderboard;
export const fetchColorsLeaderboard = impl.fetchColorsLeaderboard;
export const fetchOtherColorsLeaderboard = impl.fetchOtherColorsLeaderboard;
export const fetchColorsSummary = impl.fetchColorsSummary;
export const fetchPlayerProfile = impl.fetchPlayerProfile;
export const fetchPlayerIdentity = impl.fetchPlayerIdentity;
export const fetchPlayerSlugByDiscordId = impl.fetchPlayerSlugByDiscordId;
export const fetchAvailableFormats = impl.fetchAvailableFormats;
export const fetchFormatColorsLeaderboard = impl.fetchFormatColorsLeaderboard;
export const fetchPlayerDraftEvents = impl.fetchPlayerDraftEvents;
export const fetchRecentTrophies = impl.fetchRecentTrophies;
export const fetchFormatRecentTrophies = impl.fetchFormatRecentTrophies;
export const fetchAllRecentTrophies = impl.fetchAllRecentTrophies;
export const fetchPodEvents = impl.fetchPodEvents;
export const fetchPodSeasonEvents = impl.fetchPodSeasonEvents;
export const fetchPodSeasonResults = impl.fetchPodSeasonResults;
export const fetchPodResultsForSet = impl.fetchPodResultsForSet;
export const fetchPodEventBySlug = impl.fetchPodEventBySlug;
export const fetchPodEventParticipants = impl.fetchPodEventParticipants;
export const fetchPodDraftArtifact = impl.fetchPodDraftArtifact;
export const fetchPodEventMatches = impl.fetchPodEventMatches;
export const fetchPodEventReplays = impl.fetchPodEventReplays;
export const fetchPodLeaderboard = impl.fetchPodLeaderboard;
export const fetchPodSetCodes = impl.fetchPodSetCodes;
export const fetchPodEventDates = impl.fetchPodEventDates;
export const fetchP0P1Cards = impl.fetchP0P1Cards;
export const fetchP0P1Picks = impl.fetchP0P1Picks;
export const upsertP0P1Pick = impl.upsertP0P1Pick;
export const deleteAllP0P1Picks = impl.deleteAllP0P1Picks;
export const fetchP0P1PickStats = impl.fetchP0P1PickStats;
export const fetchP0P1Ballots = impl.fetchP0P1Ballots;
export const fetchP0P1Ratings = impl.fetchP0P1Ratings;
export const initialAuthUser = impl.initialAuthUser;
