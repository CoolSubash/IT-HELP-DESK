import { EmptyState } from "@/components/common/States";
import type { Device } from "@/types";

export function DeviceList({ devices }: { devices: Device[] }) {
  if (devices.length === 0) {
    return <EmptyState message="No devices on file for this user." />;
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Device</th>
            <th>Type</th>
            <th>Operating System</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((device) => (
            <tr key={device.id}>
              <td>
                {device.manufacturer} {device.model}
              </td>
              <td>{device.device_type ?? "—"}</td>
              <td>
                {device.operating_system}
                {device.os_version ? ` ${device.os_version}` : ""}
              </td>
              <td>{device.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
