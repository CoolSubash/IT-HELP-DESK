import type { KnowledgeDocumentStatus } from "@/types";

/** Mirrors components/tickets/Badges.tsx's pattern -- `data-doc-status`
 * drives the color via the `.badge[data-doc-status="..."]` rules in
 * app/globals.css. A separate data attribute from tickets' `data-status`
 * so the two badge families' color rules never collide (READY and
 * RESOLVED, for instance, would otherwise both need the same attribute
 * value to mean different things). */
export function DocumentStatusBadge({ status }: { status: KnowledgeDocumentStatus }) {
  return (
    <span className="badge" data-doc-status={status}>
      {status}
    </span>
  );
}
