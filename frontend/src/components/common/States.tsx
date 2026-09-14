/**
 * Three tiny, deliberately boring components covering the three non-happy
 * paths every data-fetching page needs to handle (phase3.md #10, #15):
 * still loading, nothing to show, and something went wrong. Kept together
 * in one file since none of them is more than a few lines.
 */
import { ApiError } from "@/lib/api/client";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="state-block">{label}</div>;
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-block">{message}</div>;
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : "Something went wrong.";
  return <div className="state-block state-block--error">{message}</div>;
}
