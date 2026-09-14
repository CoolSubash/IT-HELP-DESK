"use client";

import { useEffect, useState } from "react";
import { StatCard } from "@/components/common/StatCard";
import { ErrorState, LoadingState } from "@/components/common/States";
import { TicketTable } from "@/components/tickets/TicketTable";
import { getAdmins } from "@/lib/api/admins";
import { getDashboardStats } from "@/lib/api/dashboard";
import { getTickets } from "@/lib/api/tickets";
import { getUsers } from "@/lib/api/users";
import { useActingAdmin } from "@/lib/ActingAdminContext";
import type { Admin, DashboardStats, Ticket, UserWithTicketCount } from "@/types";

export default function DashboardPage() {
  const { actingAdminId } = useActingAdmin();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentTickets, setRecentTickets] = useState<Ticket[]>([]);
  const [users, setUsers] = useState<UserWithTicketCount[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      getDashboardStats(actingAdminId),
      getTickets({ limit: 5 }),
      getUsers(),
      getAdmins(),
    ])
      .then(([statsResult, ticketsPage, usersResult, adminsResult]) => {
        if (cancelled) return;
        setStats(statsResult);
        setRecentTickets(ticketsPage.items);
        setUsers(usersResult);
        setAdmins(adminsResult);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [actingAdminId]);

  const usersById = new Map(users.map((user) => [user.id, user]));
  const adminsById = new Map(admins.map((admin) => [admin.id, admin]));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="page-subtitle">Overview of current IT support operations</div>
        </div>
      </div>

      {loading && <LoadingState label="Loading dashboard..." />}
      {!loading && Boolean(error) && <ErrorState error={error} />}

      {!loading && !error && stats && (
        <>
          <div className="stat-grid">
            <StatCard label="Open Tickets" value={stats.open} />
            <StatCard label="In Progress" value={stats.in_progress} />
            <StatCard label="Waiting for User" value={stats.waiting_for_user} />
            <StatCard label="Resolved" value={stats.resolved} />
            <StatCard label="Closed" value={stats.closed} />
            <StatCard label="High Priority" value={stats.high_priority} />
            <StatCard
              label="Tickets Assigned to Me"
              value={stats.assigned_to_me ?? "Select an admin above"}
            />
          </div>

          <h2 className="section-title">Recent Tickets</h2>
          <TicketTable tickets={recentTickets} usersById={usersById} adminsById={adminsById} />
        </>
      )}
    </div>
  );
}
