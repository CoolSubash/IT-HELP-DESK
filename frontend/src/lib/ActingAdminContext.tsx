"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { UUID } from "@/types";

const STORAGE_KEY = "helpdesk.actingAdminId";

/**
 * Phase 3 has no login. This context is the stand-in for "who is using the
 * dashboard right now" -- an admin id picked from a dropdown (see
 * components/layout/Topbar.tsx), kept in React state (shared across every
 * page via the provider in app/layout.tsx) and mirrored into localStorage
 * so the choice survives a page reload. It's never sent anywhere as a
 * credential -- it's just what "Tickets Assigned to Me" and status-change
 * attribution use as "me".
 */
interface ActingAdminContextValue {
  actingAdminId: UUID | null;
  setActingAdminId: (id: UUID | null) => void;
}

const ActingAdminContext = createContext<ActingAdminContextValue | null>(null);

export function ActingAdminProvider({ children }: { children: React.ReactNode }) {
  const [actingAdminId, setActingAdminIdState] = useState<UUID | null>(null);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setActingAdminIdState(stored);
    } catch {
      // localStorage can throw in private browsing / restricted contexts --
      // falling back to "no acting admin" just disables the "assigned to
      // me" convenience, nothing breaks.
    }
  }, []);

  const setActingAdminId = useCallback((id: UUID | null) => {
    setActingAdminIdState(id);
    try {
      if (id) {
        window.localStorage.setItem(STORAGE_KEY, id);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Ignore -- see above.
    }
  }, []);

  const value = useMemo(
    () => ({ actingAdminId, setActingAdminId }),
    [actingAdminId, setActingAdminId]
  );

  return <ActingAdminContext.Provider value={value}>{children}</ActingAdminContext.Provider>;
}

export function useActingAdmin(): ActingAdminContextValue {
  const context = useContext(ActingAdminContext);
  if (!context) {
    throw new Error("useActingAdmin must be used within an ActingAdminProvider");
  }
  return context;
}
