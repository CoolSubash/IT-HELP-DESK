import { apiGet, toQueryString } from "./client";
import type { Device, Page, Ticket, UUID, UserWithTicketCount } from "@/types";

export function getUsers(): Promise<UserWithTicketCount[]> {
  return apiGet<UserWithTicketCount[]>("/users");
}

export function getUser(id: UUID): Promise<UserWithTicketCount> {
  return apiGet<UserWithTicketCount>(`/users/${id}`);
}

export function getUserTickets(id: UUID, limit = 100, offset = 0): Promise<Page<Ticket>> {
  return apiGet<Page<Ticket>>(`/users/${id}/tickets${toQueryString({ limit, offset })}`);
}

export function getUserDevices(id: UUID): Promise<Device[]> {
  return apiGet<Device[]>(`/users/${id}/devices`);
}
