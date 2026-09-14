"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/common/States";
import { DeviceList } from "@/components/users/DeviceList";
import { UserTicketList } from "@/components/users/UserTicketList";
import { getUser, getUserDevices, getUserTickets } from "@/lib/api/users";
import type { Device, Ticket, UserWithTicketCount } from "@/types";

export default function UserDetailPage() {
  const params = useParams<{ id: string }>();
  const userId = params.id;

  const [user, setUser] = useState<UserWithTicketCount | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getUser(userId), getUserTickets(userId), getUserDevices(userId)])
      .then(([userResult, ticketsPage, devicesResult]) => {
        if (cancelled) return;
        setUser(userResult);
        setTickets(ticketsPage.items);
        setDevices(devicesResult);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (loading) {
    return (
      <div className="page">
        <LoadingState label="Loading user..." />
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="page">
        <ErrorState error={error ?? new Error("User not found")} />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">{user.name ?? user.email}</h1>
          <div className="page-subtitle">
            {/* phase3.md #7: make it easy to see who this person is and what
                IT problems they've had before. */}
            Who is this person and what IT problems have they had before?
          </div>
        </div>
      </div>

      <div className="ticket-detail">
        <div>
          <div className="card">
            <h2 className="section-title">Ticket History</h2>
            <UserTicketList tickets={tickets} />
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <h2 className="section-title">Devices</h2>
            <DeviceList devices={devices} />
          </div>
        </div>

        <div className="card">
          <h2 className="section-title">User Information</h2>
          <dl className="detail-list">
            <dt>Name</dt>
            <dd>{user.name ?? "—"}</dd>
            <dt>Email</dt>
            <dd>{user.email}</dd>
            <dt>Department</dt>
            <dd>{user.department ?? "—"}</dd>
            <dt>Student/Employee ID</dt>
            <dd>{user.employee_or_student_id ?? "—"}</dd>
            <dt>Role</dt>
            <dd>{user.role}</dd>
            <dt>Account status</dt>
            <dd>{user.account_status}</dd>
            <dt>Created</dt>
            <dd>{new Date(user.created_at).toLocaleDateString()}</dd>
          </dl>
        </div>
      </div>
    </div>
  );
}
