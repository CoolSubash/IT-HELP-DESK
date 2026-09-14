/**
 * Mirrors the backend's Pydantic read schemas (backend/app/schemas/).
 * Kept in sync by hand -- if this becomes unwieldy, generate it from
 * FastAPI's OpenAPI schema instead.
 */
export type UUID = string;

export type UserRole = "STUDENT" | "STAFF" | "FACULTY" | "ADMIN";
export type AccountStatus = "ACTIVE" | "SUSPENDED" | "DISABLED";

export type TicketCategory =
  | "VPN"
  | "WIFI"
  | "PASSWORD"
  | "SOFTWARE"
  | "HARDWARE"
  | "ACCOUNT"
  | "EMAIL"
  | "NETWORK"
  | "OTHER";

export type TicketPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export type TicketStatus =
  | "NEW"
  | "AI_INVESTIGATING"
  | "WAITING_FOR_USER"
  | "WAITING_FOR_ADMIN"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "ESCALATED"
  | "CLOSED";

export type ResolutionSource = "AI" | "ADMIN";
export type ClosedReason = "RESOLVED" | "USER_INACTIVE" | "DUPLICATE" | "WITHDRAWN" | "OTHER";
export type SenderType = "STUDENT" | "AI" | "ADMIN";
export type MessageDirection = "INBOUND" | "OUTBOUND";
export type EventActorType = "STUDENT" | "AI" | "ADMIN" | "SYSTEM";
export type DeviceStatus = "ACTIVE" | "INACTIVE" | "FLAGGED" | "RETIRED";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface User {
  id: UUID;
  email: string;
  name: string | null;
  department: string | null;
  employee_or_student_id: string | null;
  role: UserRole;
  account_status: AccountStatus;
  created_at: string;
  updated_at: string;
}

export interface UserWithTicketCount extends User {
  ticket_count: number;
}

export interface Admin {
  id: UUID;
  name: string;
  email: string;
  created_at: string;
}

export interface Ticket {
  id: UUID;
  // Human-friendly sequential number (Phase 6) -- display as `T-${ticket_number}`,
  // matching the format used in email subjects (app/email/threading.py).
  ticket_number: number;
  user_id: UUID;
  subject: string;
  description: string;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  resolution: string | null;
  resolution_source: ResolutionSource | null;
  resolution_confirmed: boolean;
  assigned_admin_id: UUID | null;
  parent_ticket_id: UUID | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  closed_at: string | null;
  waiting_since: string | null;
  follow_up_sent_at: string | null;
  auto_close_at: string | null;
  closed_reason: ClosedReason | null;
}

export interface TicketRelated {
  parent: Ticket | null;
  children: Ticket[];
}

export interface Message {
  id: UUID;
  ticket_id: UUID;
  sender_type: SenderType;
  sender_id: UUID | null;
  body: string;
  subject: string | null;
  email_message_id: string | null;
  in_reply_to: string | null;
  email_thread_id: string | null;
  direction: MessageDirection;
  created_at: string;
}

export interface TicketEvent {
  id: UUID;
  ticket_id: UUID;
  event_type: string;
  actor_type: EventActorType;
  actor_id: UUID | null;
  old_value: string | null;
  new_value: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentAction {
  id: UUID;
  ticket_id: UUID;
  action_type: string;
  tool_name: string | null;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  reason: string | null;
  confidence: number | null;
  status: string;
  created_at: string;
}

export interface Device {
  id: UUID;
  user_id: UUID;
  device_identifier: string;
  device_type: string | null;
  manufacturer: string | null;
  model: string | null;
  operating_system: string | null;
  os_version: string | null;
  status: DeviceStatus;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  open: number;
  in_progress: number;
  waiting_for_user: number;
  resolved: number;
  closed: number;
  high_priority: number;
  assigned_to_me: number | null;
}

export const TICKET_STATUSES: TicketStatus[] = [
  "NEW",
  "AI_INVESTIGATING",
  "WAITING_FOR_USER",
  "WAITING_FOR_ADMIN",
  "IN_PROGRESS",
  "RESOLVED",
  "ESCALATED",
  "CLOSED",
];

export const TICKET_PRIORITIES: TicketPriority[] = ["LOW", "MEDIUM", "HIGH", "URGENT"];

export const TICKET_CATEGORIES: TicketCategory[] = [
  "VPN",
  "WIFI",
  "PASSWORD",
  "SOFTWARE",
  "HARDWARE",
  "ACCOUNT",
  "EMAIL",
  "NETWORK",
  "OTHER",
];

// --- Knowledge base (Phase 7) ---
// Mirrors backend/app/schemas/knowledge_document.py,
// backend/app/schemas/knowledge_chunk.py, backend/app/schemas/knowledge_search.py.

export type KnowledgeDocumentStatus = "PROCESSING" | "READY" | "FAILED" | "ARCHIVED";

export interface KnowledgeDocument {
  id: UUID;
  title: string;
  description: string | null;
  category: string | null;
  file_name: string;
  file_type: string;
  storage_location: string;
  version: number;
  status: KnowledgeDocumentStatus;
  previous_version_id: UUID | null;
  error_message: string | null;
  uploaded_by: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeChunk {
  id: UUID;
  document_id: UUID;
  chunk_index: number;
  content: string;
  token_count: number;
  created_at: string;
}

export interface PresignUploadResponse {
  document: KnowledgeDocument;
  upload_url: string;
  expires_in: number;
}

export interface KnowledgeSearchResult {
  chunk_id: UUID;
  document_id: UUID;
  title: string;
  category: string | null;
  content: string;
  score: number;
}

export interface KnowledgeContextResult {
  title: string;
  content: string;
  score: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  results: KnowledgeSearchResult[];
  context: { query: string; results: KnowledgeContextResult[] };
}

// Reused for the knowledge base's category field (free text on the
// backend -- see migrations/0001_initial_schema.sql -- but seeded/used
// consistently with these same values, see seed/seed_knowledge_base.py).
export const KNOWLEDGE_CATEGORIES: TicketCategory[] = TICKET_CATEGORIES;
