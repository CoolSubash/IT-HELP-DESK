"use client";

import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * On a small screen the sidebar becomes an off-canvas drawer instead of a
 * permanent column -- Topbar's hamburger button and Sidebar's open/close
 * state need to be driven by the same piece of state, so it lives here,
 * one level above both of them, rather than in either component alone.
 * On a desktop-width screen this state is simply never used (the CSS media
 * query in globals.css keeps the sidebar permanently visible there
 * regardless of `open`).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      {mobileNavOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}
      <div className="app-main">
        <Topbar onMenuClick={() => setMobileNavOpen((open) => !open)} />
        <main>{children}</main>
      </div>
    </div>
  );
}
