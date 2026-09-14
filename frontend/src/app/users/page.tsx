"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/States";
import { UserTable } from "@/components/users/UserTable";
import { getUsers } from "@/lib/api/users";
import type { UserWithTicketCount } from "@/types";

export default function UsersPage() {
  const [users, setUsers] = useState<UserWithTicketCount[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    getUsers()
      .then((result) => {
        if (!cancelled) setUsers(result);
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
  }, []);

  // The list is small and already fully loaded (GET /users isn't
  // paginated), so filtering client-side avoids adding a backend search
  // param for a dataset this size -- see app/tickets/page.tsx for the
  // server-side version, used there because ticket lists can actually grow
  // large.
  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return users;
    return users.filter(
      (user) =>
        user.id.toLowerCase().includes(term) ||
        (user.name ?? "").toLowerCase().includes(term) ||
        user.email.toLowerCase().includes(term)
    );
  }, [users, search]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Users</h1>
          <div className="page-subtitle">Students and employees who have contacted IT support</div>
        </div>
      </div>

      <div className="filters-bar">
        <input
          className="control search-input"
          placeholder="Search by name, email, or user ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading && <LoadingState label="Loading users..." />}
      {!loading && Boolean(error) && <ErrorState error={error} />}
      {!loading && !error && filteredUsers.length === 0 && (
        <EmptyState message="No users match that search." />
      )}
      {!loading && !error && filteredUsers.length > 0 && <UserTable users={filteredUsers} />}
    </div>
  );
}
