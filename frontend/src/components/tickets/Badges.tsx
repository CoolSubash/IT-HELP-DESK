import type { TicketPriority, TicketStatus } from "@/types";

/**
 * `data-status`/`data-priority` (not a dynamically-built className) drive
 * the color per value -- see the `.badge[data-status="..."]` rules in
 * app/globals.css. One place defines what each value looks like.
 */
export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className="badge" data-status={status}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className="badge" data-priority={priority}>
      {priority}
    </span>
  );
}
