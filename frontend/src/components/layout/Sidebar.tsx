"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/tickets", label: "Tickets" },
  { href: "/users", label: "Users" },
  { href: "/knowledge-base", label: "Knowledge Base" },
  { href: "/analytics", label: "Analytics" },
];

interface SidebarProps {
  /** Only meaningful below the mobile breakpoint -- see the
   * `.sidebar` / `.sidebar--open` rules in globals.css. Ignored (sidebar
   * always visible) on a desktop-width screen. */
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname();

  return (
    <nav className={`sidebar${open ? " sidebar--open" : ""}`} aria-label="Primary">
      <div className="sidebar__header">
        <div className="sidebar__logo">IT Helpdesk Admin</div>
        <button
          type="button"
          className="sidebar__close"
          onClick={onClose}
          aria-label="Close navigation"
        >
          ✕
        </button>
      </div>
      <div className="sidebar__nav">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`sidebar__link${isActive ? " sidebar__link--active" : ""}`}
              onClick={onClose}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
