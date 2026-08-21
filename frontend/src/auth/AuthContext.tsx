import { createContext, useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { initialAuthUser } from "../data/api";
import { DEV_AUTH_USER } from "../data/devAuth";
import { supabase } from "../data/supabase";

export interface AuthUser {
  id: string;
  discordId: string;
  username: string;
  avatarUrl: string | null;
}

export interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signIn: () => void;
  signOut: () => void;
}

const noop = () => {};

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signIn: noop,
  signOut: noop,
});

function mapSessionUser(session: Session | null): AuthUser | null {
  if (!session?.user) return null;
  const meta = session.user.user_metadata;
  const discordId = meta.provider_id ?? meta.sub ?? "";
  if (!discordId) return null;
  return {
    id: session.user.id,
    discordId,
    username: meta.custom_claims?.global_name ?? meta.full_name ?? meta.name ?? "Unknown",
    avatarUrl: meta.avatar_url ?? null,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(DEV_AUTH_USER ?? initialAuthUser);
  const [loading, setLoading] = useState(!(DEV_AUTH_USER ?? initialAuthUser));

  useEffect(() => {
    if (DEV_AUTH_USER || !supabase) return;

    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(mapSessionUser(session));
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(mapSessionUser(session));
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = () => {
    if (!supabase) {
      setUser(initialAuthUser);
      return;
    }
    supabase.auth.signInWithOAuth({
      provider: "discord",
      options: { redirectTo: window.location.href },
    });
  };

  const signOut = () => {
    if (!supabase) {
      setUser(null);
      return;
    }
    supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
