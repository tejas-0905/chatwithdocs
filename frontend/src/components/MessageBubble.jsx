import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MessageBubble({
  message,
  previousQuestion = null,
  onRegenerate = null,
  showSources = true,
  onSpeak = null,
  isSpeaking = false,
}) {
  const isAssistant = message.role === 'assistant';
  const [entered, setEntered] = useState(false);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => setEntered(true), 10);
    return () => clearTimeout(t);
  }, []);

  const text = message.text || message.answer || message.question || '';

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setFeedback('copied');
      setTimeout(() => setFeedback(null), 1400);
    } catch (e) {
      setFeedback('copy-failed');
      setTimeout(() => setFeedback(null), 1400);
    }
  };

  const sendFeedback = (value) => {
    setFeedback(value);
    setTimeout(() => setFeedback(null), 1200);
  };

  return (
    <article className={`message ${message.role} ${entered ? 'enter' : ''}`}>
      <div className="message-meta">
        <span>{message.role === 'user' ? 'You' : 'Assistant'}</span>
        {message.created_at && <time>{new Date(message.created_at).toLocaleTimeString()}</time>}
      </div>

      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>

      <div className="message-actions">
        <button type="button" className="action copy" onClick={copyText} aria-label="Copy message">
          {feedback === 'copied' ? 'Copied' : 'Copy'}
        </button>
        {isAssistant && (
          <>
            {onSpeak && (
              <button
                type="button"
                className={`speak-response ${isSpeaking ? 'is-speaking' : ''}`}
                onClick={() => onSpeak(message.id, text)}
                aria-label={isSpeaking ? 'Stop reading response' : 'Read response aloud'}
                title={isSpeaking ? 'Stop reading response' : 'Read response aloud'}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 10v4h4l5 4V6l-5 4H4Z" />
                  <path d="M16 9.5a4 4 0 0 1 0 5M18.5 7a7.5 7.5 0 0 1 0 10" />
                </svg>
              </button>
            )}
            <button
              type="button"
              className={`action feedback ${feedback === 'up' ? 'active' : ''}`}
              onClick={() => sendFeedback('up')}
              aria-label="Thumbs up"
            >
              👍
            </button>
            <button
              type="button"
              className={`action feedback ${feedback === 'down' ? 'active' : ''}`}
              onClick={() => sendFeedback('down')}
              aria-label="Thumbs down"
            >
              👎
            </button>
            {previousQuestion && onRegenerate && (
              <>
                <select
                  className="regen-select"
                  aria-label="Regenerate style"
                  defaultValue="short"
                  onChange={(e) => onRegenerate(previousQuestion, e.target.value)}
                >
                  <option value="short">Short</option>
                  <option value="brief">Brief</option>
                  <option value="bullets">Bullets</option>
                  <option value="strict">Strict</option>
                </select>
                <button
                  type="button"
                  className="action regen"
                  onClick={() => onRegenerate(previousQuestion, 'short')}
                  aria-label="Regenerate answer"
                >
                  Regenerate
                </button>
              </>
            )}
          </>
        )}
      </div>

      {showSources && isAssistant && message.sources?.length > 0 && (
        <details className="sources" open>
          <summary>Document references ({message.sources.length})</summary>
          <div className="source-list">
            {message.sources.map((source, index) => (
              <div className="source-card" key={`${source.location}-${index}`}>
                <strong>{source.location}</strong>
                {typeof source.score === 'number' && <span>Score {source.score}</span>}
                <p>{source.text}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </article>
  );
}
