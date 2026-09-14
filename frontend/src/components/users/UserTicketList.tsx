"use client";

import { useRouter } from "next/navigation";
import { StatusBadge } from "@/components/tickets/Badges";
import { EmptyState } from "@/components/common/States";
import type { Ticket } from "@/types";

/** phase3.md #7: "Who is this person and what IT problems have they had
 * before?" -- every ticket the user has ever filed, clickable. */
export function UserTicketList({ tickets }: { tickets: Ticket[] }) {
  const router = useRouter();

  if (tickets.length === 0) {
    return <EmptyState message="This user has no tickets yet." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr
              key={ticket.id}
              className="table__row--clickable"
              onClick={() => router.push(`/tickets/${ticket.id}`)}
            >
              <td>#T-{ticket.ticket_number}</td>
              <td>{ticket.subject}</td>
              <td>
                <StatusBadge status={ticket.status} />
              </td>
              <td>{new Date(ticket.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
