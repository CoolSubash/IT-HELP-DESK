import { apiGet } from "./client";
import type { Admin } from "@/types";

export function getAdmins(): Promise<Admin[]> {
  return apiGet<Admin[]>("/admins");
}
