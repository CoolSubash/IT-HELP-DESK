import type { Message } from "@/types";

export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className="message-bubble" data-sender={message.sender_type}>
      <div className="message-bubble__meta">
        <span className="message-bubble__sender-tag">{message.sender_type}</span>
        <span>{new Date(message.created_at).toLocaleString()}</span>
      </div>
      <div>{message.body}</div>
    </div>
  );
}
