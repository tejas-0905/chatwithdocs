import { MessageBubble } from "./MessageBubble";
import { useEffect, useRef } from "react";

export function ChatWindow({
  document,
  messages,
  thinking,
  onRegenerate,
  showSources = true,
  followUps = [],
  onAskSuggested,
  actionItems = [],
  onSpeak,
  speakingMessageId,
}) {
  const containerRef = useRef(null);

  useEffect(() => {
    // Smooth scroll to bottom when messages change or while thinking
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages.length, thinking]);

  if (!document) {
    return (
      <section className="chat-window">
        <div className="empty-state">
          <h2>Select or upload a document</h2>
          <p>Your grounded answers, citations, and chat history will appear here.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="chat-window" aria-live="polite" ref={containerRef}>
      {messages.length === 0 && (
        <div className="empty-state">
          <h2>No questions yet</h2>
          <p>Ask for a summary, risks, requirements, or decisions from this document.</p>
        </div>
      )}

      {messages.map((message, idx) => {
        const prev = idx > 0 ? messages[idx - 1] : null;
        const previousQuestion = prev && prev.role === 'user' ? prev.text : null;
        return (
          <MessageBubble
            key={message.id}
            message={message}
            previousQuestion={previousQuestion}
            onRegenerate={onRegenerate}
            showSources={showSources}
            onSpeak={onSpeak}
            isSpeaking={speakingMessageId === message.id}
          />
        );
      })}

      {thinking && (
        <article className="message assistant">
          <div className="message-meta">
            <span>Assistant</span>
            <time>now</time>
          </div>
          <div className="thinking">
            <span />
            <span />
            <span />
          </div>
        </article>
      )}
      {document && !thinking && followUps.length > 0 && (
        <div className="followup-strip">
          <span>Continue exploring</span>
          {followUps.map((followUp) => (
            <button type="button" key={followUp} onClick={() => onAskSuggested(followUp)}>{followUp}</button>
          ))}
        </div>
      )}
      {actionItems.length > 0 && (
        <section className="action-items-card">
          <strong>Action items found</strong>
          {actionItems.map((item) => <label key={item}><input type="checkbox" /> <span>{item}</span></label>)}
        </section>
      )}
    </section>
  );
}
