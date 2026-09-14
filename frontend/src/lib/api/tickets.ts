import { apiGet, apiPatch, apiPost, toQueryString } from "./client";
import type {
  AgentAction,
  Message,
  Page,
  SenderType,
  Ticket,
  TicketCategory,
  TicketEvent,
  TicketPriority,
  TicketRelated,
  TicketStatus,
  UUID,
} from "@/types";

export interface TicketHistoryEntry {
  type: "message" | "event" | "agent_action";
  created_at: string;
  data: Record<string, unknown>;
}

export interface TicketListFilters {
  limit?: number;
  offset?: number;
  status?: TicketStatus;
  priority?: TicketPriority;
  category?: TicketCategory;
  assigned_admin_id?: UUID;
  search?: string;
}

export function getTickets(filters: TicketListFilters = {}): Promise<Page<Ticket>> {
  return apiGet<Page<Ticket>>(`/tickets${toQueryString(filters)}`);
}

export function getTicket(id: UUID): Promise<Ticket> {
  return apiGet<Ticket>(`/tickets/${id}`);
}

export function createTicket(payload: {
  user_id: UUID;
  subject: string;
  description: string;
  category: TicketCategory;
  priority?: TicketPriority;
  parent_ticket_id?: UUID;
}): Promise<Ticket> {
  return apiPost<Ticket>("/tickets", payload);
}

export function updateTicketStatus(
  id: UUID,
  status: TicketStatus,
  changedByAdminId?: UUID | null
): Promise<Ticket> {
  return apiPatch<Ticket>(`/tickets/${id}/status`, {
    status,
    changed_by_admin_id: changedByAdminId ?? undefined,
  });
}

export function assignTicket(id: UUID, assignedAdminId: UUID): Promise<Ticket> {
  return apiPatch<Ticket>(`/tickets/${id}/assign`, { assigned_admin_id: assignedAdminId });
}

export function getRelatedTickets(id: UUID): Promise<TicketRelated> {
  return apiGet<TicketRelated>(`/tickets/${id}/related`);
}

export function getTicketHistory(id: UUID): Promise<TicketHistoryEntry[]> {
  return apiGet<TicketHistoryEntry[]>(`/tickets/${id}/history`);
}

export function getTicketMessages(
  id: UUID,
  limit = 100,
  offset = 0
): Promise<Page<Message>> {
  return apiGet<Page<Message>>(`/tickets/${id}/messages${toQueryString({ limit, offset })}`);
}

export interface SendMessageResult {
  message: Message;
  email_sent: boolean;
  email_error: string | null;
}

export function sendAdminMessage(
  ticketId: UUID,
  body: string,
  senderId?: UUID | null,
  sendEmail = true
): Promise<SendMessageResult> {
  // A message can be created successfully even when the email it was
  // supposed to trigger fails to send -- see
  // backend/app/schemas/message.py:SendMessageResult -- so the caller
  // (TicketConversation) gets both facts back, not just the message.
  const payload: { sender_type: SenderType; body: string; sender_id?: UUID; send_email: boolean } = {
    sender_type: "ADMIN",
    body,
    send_email: sendEmail,
  };
  if (senderId) payload.sender_id = senderId;
  return apiPost<SendMessageResult>(`/tickets/${ticketId}/messages`, payload);
}

export function getTicketEvents(id: UUID, limit = 100, offset = 0): Promise<Page<TicketEvent>> {
  return apiGet<Page<TicketEvent>>(`/tickets/${id}/events${toQueryString({ limit, offset })}`);
}

export function getAgentActions(
  id: UUID,
  limit = 100,
  offset = 0
): Promise<Page<AgentAction>> {
  return apiGet<Page<AgentAction>>(
    `/tickets/${id}/agent-actions${toQueryString({ limit, offset })}`
  );
}
