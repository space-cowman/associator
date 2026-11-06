"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, endSession, refreshSession } from "@/lib/api";
import { clearToken, readSession, saveToken, type Session } from "@/lib/session";
import type { Draft, Group } from "@/lib/types";
import { TermsPrompt } from "./TermsPrompt";

type Toast = { id: number; text: string; error?: boolean };

type AppState = {
  session: Session | null;
  ready: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
  groups: Group[];
  reloadGroups: () => Promise<void>;
  pendingDrafts: number;
  reloadDrafts: () => Promise<void>;
  toast: (text: string, error?: boolean) => void;
};

const AppContext = createContext<AppState | null>(null);

/** The shared app state. */
export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside Providers");
  return ctx;
}

/** Holds the session, clusters and toasts. */
export function Providers({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [groups, setGroups] = useState<Group[]>([]);
  const [pendingDrafts, setPendingDrafts] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((text: string, error = false) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, error }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  const reloadGroups = useCallback(async () => {
    try {
      setGroups(await api<Group[]>("/groups"));
    } catch {
    }
  }, []);

  const reloadDrafts = useCallback(async () => {
    if (!readSession()) return setPendingDrafts(0);
    try {
      setPendingDrafts((await api<Draft[]>("/drafts?status=pending")).length);
    } catch {
    }
  }, []);

  const signIn = useCallback(async (token: string) => {
    saveToken(token.trim());
    const s = readSession();
    if (!s) {
      clearToken();
      throw new Error("That token is not valid or has expired.");
    }
    try {
      await api("/me");
    } catch {
      clearToken();
      throw new Error("The api did not accept that token.");
    }
    setSession(s);
  }, []);

  const signOut = useCallback(() => {
    void endSession();
    clearToken();
    setSession(null);
    setPendingDrafts(0);
  }, []);

  useEffect(() => {
    const existing = readSession();
    if (existing) {
      setSession(existing);
      setReady(true);
    } else {
      void refreshSession().then(() => {
        setSession(readSession());
        setReady(true);
      });
    }
    void reloadGroups();
  }, [reloadGroups]);

  useEffect(() => {
    if (!session) return;
    const wait = Math.max(session.expiresAt - Date.now() - 60_000, 5_000);
    const timer = setTimeout(() => {
      void refreshSession().then((t) => setSession(t ? readSession() : session.expiresAt > Date.now() ? session : null));
    }, wait);
    return () => clearTimeout(timer);
  }, [session]);

  useEffect(() => {
    if (!session) return;
    void reloadDrafts();
    const timer = setInterval(() => void reloadDrafts(), 60_000);
    return () => clearInterval(timer);
  }, [session, reloadDrafts]);

  const value = useMemo(
    () => ({ session, ready, signIn, signOut, groups, reloadGroups, pendingDrafts, reloadDrafts, toast }),
    [session, ready, signIn, signOut, groups, reloadGroups, pendingDrafts, reloadDrafts, toast],
  );

  return (
    <AppContext.Provider value={value}>
      {children}
      <TermsPrompt />
      <div className="toast-wrap" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast${t.error ? " err" : ""}`}>
            {t.text}
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
}
