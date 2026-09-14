import { EmptyState } from "@/components/common/States";
import type { TicketEvent } from "@/types";

/** phase3.md #8: this must read as an audit/history timeline, distinct
 * from the email conversation -- plain rows of "what changed," not chat
 * bubbles. Renders `ticket_events` directly, not the merged
 * messages+events+agent_actions feed GET /tickets/{id}/history returns --
 * this section is specifically the audit trail. */
export function TicketHistory({ events }: { events: TicketEvent[] }) {
  if (events.length === 0) {
    return <EmptyState message="No history recorded yet." />;
  }

  const sorted = [...events].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return (
    <div className="timeline">
      {sorted.map((event) => (
        <div key={event.id} className="timeline__item">
          <div className="timeline__time">{new Date(event.created_at).toLocaleString()}</div>
          <div className="timeline__body">
            <div>{describeEvent(event)}</div>
            <div className="timeline__actor">Actor: {event.actor_type}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function describeEvent(event: TicketEvent): string {
  if (event.event_type === "STATUS_CHANGED") {
    return `Status changed: ${event.old_value ?? "(none)"} → ${event.new_value}`;
  }
  if (event.event_type === "TICKET_CREATED") {
    return "Ticket created";
  }
  if (event.event_type === "ASSIGNED") {
    return event.old_value ? "Ticket reassigned" : "Ticket assigned";
  }
  return event.event_type.replaceAll("_", " ").toLowerCase();
}
