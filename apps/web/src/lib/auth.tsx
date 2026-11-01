"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { supabaseBrowser } from "./supabase/client";
import { DEV_AUTH } from "./config";

type AuthState = { token: string | null; userId: string | null; email: string | null; ready: boolean; signOut: () => Promise<void> };
const Ctx = createContext<AuthState>({ token: null, userId: null, email: null, ready: false, signOut: async () => {} });
const DEV_KEY = "rahbar.devToken";

export function setDevToken(token: string | null) {
  try {
    if (token) localStorage.setItem(DEV_KEY, token);
    else localStorage.removeItem(DEV_KEY);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event("rahbar-auth"));
}

function decodeSub(token: string): { sub: string | null; email: string | null } {
  try {
    const part = token.split(".")[1] ?? "";
    const json = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    return { sub: json.sub ?? null, email: json.email ?? null };
  } catch {
    return { sub: null, email: null };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sb = supabaseBrowser();
    if (sb) {
      sb.auth.getSession().then(({ data }) => {
        setToken(data.session?.access_token ?? null);
        setReady(true);
      });
      const { data } = sb.auth.onAuthStateChange((_e, session) => setToken(session?.access_token ?? null));
      return () => data.subscription.unsubscribe();
    }
    const readDev = () => {
      try {
        setToken(DEV_AUTH ? localStorage.getItem(DEV_KEY) : null);
      } catch {
        setToken(null);
      }
      setReady(true);
    };
    readDev();
    window.addEventListener("rahbar-auth", readDev);
    return () => window.removeEventListener("rahbar-auth", readDev);
  }, []);

  const signOut = useCallback(async () => {
    const sb = supabaseBrowser();
    if (sb) await sb.auth.signOut();
    setDevToken(null);
    setToken(null);
  }, []);

  const value = useMemo(() => {
    const { sub, email } = token ? decodeSub(token) : { sub: null, email: null };
    return { token, userId: sub, email, ready, signOut };
  }, [token, ready, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
