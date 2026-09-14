import { apiGet, toQueryString } from "./client";
import type { DashboardStats, UUID } from "@/types";

export function getDashboardStats(adminId?: UUID | null): Promise<DashboardStats> {
  return apiGet<DashboardStats>(`/dashboard/stats${toQueryString({ admin_id: adminId })}`);
}
