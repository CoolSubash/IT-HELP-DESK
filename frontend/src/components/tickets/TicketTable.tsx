"use client";

import { useRouter } from "next/navigation";
import { PriorityBadge, StatusBadge } from "./Badges";
import { EmptyState } from "@/components/common/States";
import type { Admin, Ticket, UserWithTicketCount } from "@/types";

/**
 * `tickets` only carries `user_id`/`assigned_admin_id` -- the raw FK
 * values (see backend/app/schemas/ticket.py). This component resolves
 * them to a name via the lookup maps the page building it fetched
 * separately (GET /users, GET /admins), rather than the backend joining
 * them in -- both lists are small and unpaginated, so a client-side join
 * is simpler than adding a new backend response shape just for display.
 */
interface TicketTableProps {
  tickets: Ticket[];
  usersById: Map<string, UserWithTicketCount>;
  adminsById: Map<string, Admin>;
  showUpdatedColumn?: boolean;
}

export function TicketTable({
  tickets,
  usersById,
  adminsById,
  showUpdatedColumn = true,
}: TicketTableProps) {
  const router = useRouter();

  if (tickets.length === 0) {
    return <EmptyState message="No tickets to show." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Subject</th>
            <th>User</th>
            <th>Category</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Assigned Admin</th>
            <th>Created</th>
            {showUpdatedColumn && <th>Updated</th>}
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => {
            const user = usersById.get(ticket.user_id);
            const admin = ticket.assigned_admin_id ? adminsById.get(ticket.assigned_admin_id) : null;
            return (
              <tr
                key={ticket.id}
                className="table__row--clickable"
                onClick={() => router.push(`/tickets/${ticket.id}`)}
              >
                <td>#T-{ticket.ticket_number}</td>
                <td>{ticket.subject}</td>
                <td>{user ? user.name ?? user.email : ticket.user_id.slice(0, 8)}</td>
                <td>{ticket.category}</td>
                <td>
                  <PriorityBadge priority={ticket.priority} />
                </td>
                <td>
                  <StatusBadge status={ticket.status} />
                </td>
                <td>{admin ? admin.name : "Unassigned"}</td>
                <td>{new Date(ticket.created_at).toLocaleString()}</td>
                {showUpdatedColumn && <td>{new Date(ticket.updated_at).toLocaleString()}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
