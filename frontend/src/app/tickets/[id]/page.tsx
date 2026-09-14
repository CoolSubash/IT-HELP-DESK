"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AIActivity } from "@/components/tickets/AIActivity";
import { PriorityBadge, StatusBadge } from "@/components/tickets/Badges";
import { TicketConversation } from "@/components/tickets/TicketConversation";
import { TicketHistory } from "@/components/tickets/TicketHistory";
import { ErrorState, LoadingState } from "@/components/common/States";
import { DeviceList } from "@/components/users/DeviceList";
import { getAdmins } from "@/lib/api/admins";
import {
  assignTicket,
  getAgentActions,
  getRelatedTickets,
  getTicketEvents,
  getTicketMessages,
  getTicket,
  updateTicketStatus,
} from "@/lib/api/tickets";
import { getUser, getUserDevices } from "@/lib/api/users";
import { useActingAdmin } from "@/lib/ActingAdminContext";
import {
  TICKET_STATUSES,
  type Admin,
  type AgentAction,
  type Device,
  type Message,
  type Ticket,
  type TicketEvent,
  type TicketRelated,
  type TicketStatus,
  type UserWithTicketCount,
} from "@/types";

export default function TicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = params.id;
  const router = useRouter();
  const { actingAdminId } = useActingAdmin();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [user, setUser] = useState<UserWithTicketCount | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [related, setRelated] = useState<TicketRelated | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const [statusDraft, setStatusDraft] = useState<TicketStatus | "">("");
  const [statusSaving, setStatusSaving] = useState(false);
  const [statusError, setStatusError] = useState<unknown>(null);

  const [assignDraft, setAssignDraft] = useState("");
  const [assignSaving, setAssignSaving] = useState(false);
  const [assignError, setAssignError] = useState<unknown>(null);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const ticketResult = await getTicket(ticketId);
      const [userResult, messagesPage, eventsPage, actionsPage, relatedResult, devicesResult, adminsResult] =
        await Promise.all([
          getUser(ticketResult.user_id),
          getTicketMessages(ticketId),
          getTicketEvents(ticketId),
          getAgentActions(ticketId),
          getRelatedTickets(ticketId),
          getUserDevices(ticketResult.user_id),
          getAdmins(),
        ]);
      setTicket(ticketResult);
      setUser(userResult);
      setMessages(messagesPage.items);
      setEvents(eventsPage.items);
      setActions(actionsPage.items);
      setRelated(relatedResult);
      setDevices(devicesResult);
      setAdmins(adminsResult);
      setStatusDraft(ticketResult.status);
      setAssignDraft(ticketResult.assigned_admin_id ?? "");
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  async function handleStatusSave() {
    if (!statusDraft || !ticket) return;
    setStatusSaving(true);
    setStatusError(null);
    try {
      const updated = await updateTicketStatus(ticket.id, statusDraft, actingAdminId);
      setTicket(updated);
      const eventsPage = await getTicketEvents(ticket.id);
      setEvents(eventsPage.items);
    } catch (err) {
      setStatusError(err);
    } finally {
      setStatusSaving(false);
    }
  }

  async function handleAssignSave() {
    if (!assignDraft || !ticket) return;
    setAssignSaving(true);
    setAssignError(null);
    try {
      const updated = await assignTicket(ticket.id, assignDraft);
      setTicket(updated);
      const eventsPage = await getTicketEvents(ticket.id);
      setEvents(eventsPage.items);
    } catch (err) {
      setAssignError(err);
    } finally {
      setAssignSaving(false);
    }
  }

  const adminsById = new Map(admins.map((admin) => [admin.id, admin]));

  if (loading) {
    return (
      <div className="page">
        <LoadingState label="Loading ticket..." />
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="page">
        <ErrorState error={error ?? new Error("Ticket not found")} />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            #T-{ticket.ticket_number} — {ticket.subject}
          </h1>
          <div className="page-subtitle">
            <StatusBadge status={ticket.status} /> <PriorityBadge priority={ticket.priority} />
          </div>
        </div>
      </div>

      <div className="ticket-detail">
        <div>
          <TicketConversation
            ticketId={ticket.id}
            messages={messages}
            onMessageSent={(message) => setMessages((prev) => [...prev, message])}
          />

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">History</h2>
            <TicketHistory events={events} />
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">AI Activity</h2>
            <AIActivity actions={actions} />
          </div>
        </div>

        <div>
          <div className="card">
            <h2 className="section-title">Ticket Information</h2>
            <dl className="detail-list">
              <dt>Ticket ID</dt>
              <dd>{ticket.id}</dd>
              <dt>User</dt>
              <dd>
                {user ? (
                  <Link href={`/users/${user.id}`}>{user.name ?? user.email}</Link>
                ) : (
                  ticket.user_id
                )}
              </dd>
              <dt>User email</dt>
              <dd>{user?.email}</dd>
              <dt>Category</dt>
              <dd>{ticket.category}</dd>
              <dt>Priority</dt>
              <dd>
                <PriorityBadge priority={ticket.priority} />
              </dd>
              <dt>Status</dt>
              <dd>
                <StatusBadge status={ticket.status} />
              </dd>
              <dt>Assigned admin</dt>
              <dd>
                {ticket.assigned_admin_id
                  ? adminsById.get(ticket.assigned_admin_id)?.name ?? ticket.assigned_admin_id
                  : "Unassigned"}
              </dd>
              <dt>Created at</dt>
              <dd>{new Date(ticket.created_at).toLocaleString()}</dd>
              <dt>Updated at</dt>
              <dd>{new Date(ticket.updated_at).toLocaleString()}</dd>
              <dt>Resolved at</dt>
              <dd>{ticket.resolved_at ? new Date(ticket.resolved_at).toLocaleString() : "—"}</dd>
              <dt>Closed at</dt>
              <dd>{ticket.closed_at ? new Date(ticket.closed_at).toLocaleString() : "—"}</dd>
              <dt>Resolution</dt>
              <dd>{ticket.resolution ?? "—"}</dd>
              <dt>Resolution source</dt>
              <dd>{ticket.resolution_source ?? "—"}</dd>
              <dt>Resolution confirmed</dt>
              <dd>{ticket.resolution_confirmed ? "Yes" : "No"}</dd>
              <dt>Closed reason</dt>
              <dd>{ticket.closed_reason ?? "—"}</dd>
            </dl>
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">Change Status</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <select
                className="control"
                value={statusDraft}
                onChange={(e) => setStatusDraft(e.target.value as TicketStatus)}
              >
                {TICKET_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
              <button
                className="btn btn--primary"
                disabled={statusSaving || statusDraft === ticket.status}
                onClick={handleStatusSave}
              >
                {statusSaving ? "Saving..." : "Update"}
              </button>
            </div>
            {Boolean(statusError) && <ErrorState error={statusError} />}
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">Assign Ticket</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <select
                className="control"
                value={assignDraft}
                onChange={(e) => setAssignDraft(e.target.value)}
              >
                <option value="">Unassigned</option>
                {admins.map((admin) => (
                  <option key={admin.id} value={admin.id}>
                    {admin.name}
                  </option>
                ))}
              </select>
              <button
                className="btn btn--primary"
                disabled={assignSaving || !assignDraft || assignDraft === ticket.assigned_admin_id}
                onClick={handleAssignSave}
              >
                {assignSaving ? "Saving..." : "Assign"}
              </button>
            </div>
            {Boolean(assignError) && <ErrorState error={assignError} />}
          </div>

          {related && (related.parent || related.children.length > 0) && (
            <div className="card" style={{ marginTop: 20 }}>
              <h2 className="section-title">Related Ticket</h2>
              {related.parent && (
                <div style={{ marginBottom: 8 }}>
                  Parent:{" "}
                  <a onClick={() => router.push(`/tickets/${related.parent!.id}`)} style={{ cursor: "pointer", color: "var(--color-primary)" }}>
                    #T-{related.parent.ticket_number} — {related.parent.subject}
                  </a>
                </div>
              )}
              {related.children.map((child) => (
                <div key={child.id}>
                  Related:{" "}
                  <a onClick={() => router.push(`/tickets/${child.id}`)} style={{ cursor: "pointer", color: "var(--color-primary)" }}>
                    #T-{child.ticket_number} — {child.subject}
                  </a>
                </div>
              ))}
            </div>
          )}

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">User&apos;s Devices</h2>
            <DeviceList devices={devices} />
          </div>
        </div>
      </div>
    </div>
  );
}
