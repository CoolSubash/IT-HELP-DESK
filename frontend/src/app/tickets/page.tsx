"use client";

import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/common/States";
import { TicketTable } from "@/components/tickets/TicketTable";
import { getAdmins } from "@/lib/api/admins";
import { getTickets } from "@/lib/api/tickets";
import { getUsers } from "@/lib/api/users";
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  type Admin,
  type Page,
  type Ticket,
  type TicketCategory,
  type TicketPriority,
  type TicketStatus,
  type UserWithTicketCount,
} from "@/types";

const PAGE_SIZE = 20;

export default function TicketsPage() {
  const [status, setStatus] = useState<TicketStatus | "">("");
  const [priority, setPriority] = useState<TicketPriority | "">("");
  const [category, setCategory] = useState<TicketCategory | "">("");
  const [assignedAdminId, setAssignedAdminId] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const [page, setPage] = useState<Page<Ticket> | null>(null);
  const [users, setUsers] = useState<UserWithTicketCount[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  // Debounce the free-text search so we don't fire a request on every
  // keystroke -- only once typing pauses for 350ms.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setOffset(0);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    getAdmins()
      .then(setAdmins)
      .catch(() => setAdmins([]));
    getUsers()
      .then(setUsers)
      .catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTickets({
      limit: PAGE_SIZE,
      offset,
      status: status || undefined,
      priority: priority || undefined,
      category: category || undefined,
      assigned_admin_id: assignedAdminId || undefined,
      search: search || undefined,
    })
      .then((result) => {
        if (!cancelled) setPage(result);
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
  }, [status, priority, category, assignedAdminId, search, offset]);

  const usersById = new Map(users.map((user) => [user.id, user]));
  const adminsById = new Map(admins.map((admin) => [admin.id, admin]));

  function resetToFirstPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setOffset(0);
    };
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tickets</h1>
          <div className="page-subtitle">Search, filter, and manage every support ticket</div>
        </div>
      </div>

      <div className="filters-bar">
        <input
          className="control search-input"
          placeholder="Search subject or description..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select
          className="control"
          value={status}
          onChange={(e) => resetToFirstPage(setStatus)(e.target.value as TicketStatus | "")}
        >
          <option value="">All statuses</option>
          {TICKET_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <select
          className="control"
          value={priority}
          onChange={(e) => resetToFirstPage(setPriority)(e.target.value as TicketPriority | "")}
        >
          <option value="">All priorities</option>
          {TICKET_PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          className="control"
          value={category}
          onChange={(e) => resetToFirstPage(setCategory)(e.target.value as TicketCategory | "")}
        >
          <option value="">All categories</option>
          {TICKET_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          className="control"
          value={assignedAdminId}
          onChange={(e) => resetToFirstPage(setAssignedAdminId)(e.target.value)}
        >
          <option value="">All admins</option>
          {admins.map((admin) => (
            <option key={admin.id} value={admin.id}>
              {admin.name}
            </option>
          ))}
        </select>
      </div>

      {loading && <LoadingState label="Loading tickets..." />}
      {!loading && Boolean(error) && <ErrorState error={error} />}

      {!loading && !error && page && (
        <>
          <TicketTable tickets={page.items} usersById={usersById} adminsById={adminsById} />
          <div className="pagination">
            <span>
              Showing {page.items.length === 0 ? 0 : offset + 1}–{offset + page.items.length} of{" "}
              {page.total}
            </span>
            <button
              className="btn"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </button>
            <button
              className="btn"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
