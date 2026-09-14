"use client";

import { useState } from "react";
import { MessageBubble } from "./MessageBubble";
import { EmptyState, ErrorState } from "@/components/common/States";
import { sendAdminMessage } from "@/lib/api/tickets";
import { useActingAdmin } from "@/lib/ActingAdminContext";
import type { Message, UUID } from "@/types";

/**
 * The reply box always creates an ADMIN message through the backend
 * (POST /tickets/{id}/messages); the "Also send this as an email" checkbox
 * controls whether that call also asks the backend to email the student
 * (Phase 4's send_email option). A message can be saved successfully even
 * when the email attempt fails -- that's a separate, non-fatal warning
 * (`emailWarning`), not the same `error` state used when the message
 * itself couldn't be created at all.
 */
export function TicketConversation({
  ticketId,
  messages,
  onMessageSent,
}: {
  ticketId: UUID;
  messages: Message[];
  onMessageSent: (message: Message) => void;
}) {
  const { actingAdminId } = useActingAdmin();
  const [draft, setDraft] = useState("");
  const [sendEmail, setSendEmail] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [emailWarning, setEmailWarning] = useState<string | null>(null);

  const sorted = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  async function handleSend() {
    if (!draft.trim()) return;
    setSending(true);
    setError(null);
    setEmailWarning(null);
    try {
      const result = await sendAdminMessage(ticketId, draft.trim(), actingAdminId, sendEmail);
      onMessageSent(result.message);
      setDraft("");
      if (sendEmail && !result.email_sent) {
        setEmailWarning(
          `Message saved, but the email could not be sent${result.email_error ? `: ${result.email_error}` : "."}`
        );
      }
    } catch (err) {
      setError(err);
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <h2 className="section-title">Conversation</h2>
      {sorted.length === 0 ? (
        <EmptyState message="No messages on this ticket yet." />
      ) : (
        <div className="conversation">
          {sorted.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
      )}

      <div className="reply-box">
        <textarea
          className="control"
          placeholder="Write a response..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={sending}
        />
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={sendEmail}
            onChange={(e) => setSendEmail(e.target.checked)}
            disabled={sending}
          />
          Also send this as an email to the student
        </label>
        {Boolean(error) && <ErrorState error={error} />}
        {emailWarning && <div className="state-block state-block--error">{emailWarning}</div>}
        <div>
          <button className="btn btn--primary" onClick={handleSend} disabled={sending || !draft.trim()}>
            {sending ? "Sending..." : "Send Reply"}
          </button>
        </div>
      </div>
    </div>
  );
}
