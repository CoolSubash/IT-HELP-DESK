"use client";

import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/common/States";
import type { UserWithTicketCount } from "@/types";

export function UserTable({ users }: { users: UserWithTicketCount[] }) {
  const router = useRouter();

  if (users.length === 0) {
    return <EmptyState message="No users to show." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Department</th>
            <th>Role</th>
            <th>Account Status</th>
            <th>Number of Tickets</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr
              key={user.id}
              className="table__row--clickable"
              onClick={() => router.push(`/users/${user.id}`)}
            >
              <td>{user.name ?? "—"}</td>
              <td>{user.email}</td>
              <td>{user.department ?? "—"}</td>
              <td>{user.role}</td>
              <td>{user.account_status}</td>
              <td>{user.ticket_count}</td>
              <td>{new Date(user.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
