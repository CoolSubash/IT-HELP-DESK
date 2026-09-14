import { EmptyState } from "@/components/common/States";
import type { AgentAction } from "@/types";

/** phase3.md #9: only ever displays stored agent_actions -- no AI behavior
 * is implemented here or anywhere in Phase 3. */
export function AIActivity({ actions }: { actions: AgentAction[] }) {
  if (actions.length === 0) {
    return <EmptyState message="No AI activity recorded for this ticket." />;
  }

  const sorted = [...actions].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return (
    <div className="timeline">
      {sorted.map((action) => (
        <div key={action.id} className="timeline__item">
          <div className="timeline__time">{new Date(action.created_at).toLocaleString()}</div>
          <div className="timeline__body">
            <div>
              <strong>{action.action_type.replaceAll("_", " ")}</strong>
            </div>
            {action.tool_name && <div>Tool: {action.tool_name}</div>}
            {action.reason && <div>Reason: {action.reason}</div>}
            <div className="timeline__actor">Status: {action.status.toUpperCase()}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
