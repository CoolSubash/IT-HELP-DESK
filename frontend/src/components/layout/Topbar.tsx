"use client";

import { useEffect, useState } from "react";
import { getAdmins } from "@/lib/api/admins";
import { useActingAdmin } from "@/lib/ActingAdminContext";
import { useTheme } from "@/lib/ThemeContext";
import type { Admin } from "@/types";

/**
 * The "Acting as" picker is Phase 3's stand-in for a logged-in identity --
 * there's no auth yet (see root README). Picking a name here just sets
 * which admin id gets sent along as "me" for the dashboard's "assigned to
 * me" stat and for attributing status changes -- it doesn't gate access to
 * anything.
 */
export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { actingAdminId, setActingAdminId } = useActingAdmin();
  const { theme, toggleTheme } = useTheme();
  const [admins, setAdmins] = useState<Admin[]>([]);

  useEffect(() => {
    getAdmins()
      .then(setAdmins)
      .catch(() => setAdmins([]));
  }, []);

  return (
    <header className="topbar">
      <div className="topbar__left">
        <button
          type="button"
          className="menu-toggle"
          onClick={onMenuClick}
          aria-label="Toggle navigation"
        >
          ☰
        </button>
        <div className="topbar__title">IT Support Operations</div>
      </div>
      <div className="topbar__right">
        <div className="topbar__acting-as">
          <label htmlFor="acting-as-select">Acting as:</label>
          <select
            id="acting-as-select"
            className="control"
            value={actingAdminId ?? ""}
            onChange={(e) => setActingAdminId(e.target.value || null)}
          >
            <option value="">(none)</option>
            {admins.map((admin) => (
              <option key={admin.id} value={admin.id}>
                {admin.name}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
      </div>
    </header>
  );
}
