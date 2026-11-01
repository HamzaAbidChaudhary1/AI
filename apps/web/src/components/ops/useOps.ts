"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Fetch an ops endpoint; exposes 401/403 so pages can show the 2FA/role notice. */
export function useOps<T>(path: string | null) {
  const { token, ready } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const reload = useCallback(() => {
    if (!token || !path) return;
    api<T>(path, { token }).then((d) => { setData(d); setError(null); }).catch((e: ApiError) => setError({ status: e.status, message: e.message }));
  }, [path, token]);
  useEffect(reload, [reload]);
  const call = useCallback(async (p: string, body?: unknown, method = "POST") => {
    const r = await api(p, { token, body, method });
    reload();
    return r;
  }, [token, reload]);
  return { data, error, reload, call, token, ready };
}
