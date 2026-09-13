import { useEffect, useMemo, useRef, useState } from "react";
import { jsPDF } from "jspdf";
import { askQuestion, regenerateAnswer, deleteDocument, fetchDocuments, fetchHistory, uploadDocument } from "./api";
import { ChatWindow } from "./components/ChatWindow";
import { Sidebar } from "./components/Sidebar";
import { UploadZone } from "./components/UploadZone";
import "./App.css";

const starterPrompts = [
  { label: "Brief it", prompt: "Summarize the document in five concise bullets.", icon: "✦" },
  { label: "Key requirements", prompt: "What are the most important requirements?", icon: "⌘" },
  { label: "Find risks", prompt: "List risks, assumptions, and open questions.", icon: "⚑" },
  { label: "Make a plan", prompt: "Create an action plan from this document.", icon: "→" },
];

function historyToMessages(history) {
  return history.flatMap((item) => [
    {
      id: `${item.created_at}-question`,
      role: "user",
      text: item.question,
      created_at: item.created_at,
    },
    {
      id: `${item.created_at}-answer`,
      role: "assistant",
      text: item.answer,
      sources: item.sources || [],
      created_at: item.created_at,
    },
  ]);
}

function formatFileSize(sizeBytes = 0) {
  if (!sizeBytes) return "—";
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [error, setError] = useState("");
  const [answerMode, setAnswerMode] = useState("bullets");
  const [theme, setTheme] = useState(() => localStorage.getItem("chat-docs-theme") || "light");
  const [userName, setUserName] = useState(() => localStorage.getItem("chat-docs-user-name") || "Mike Taylor");
  const [activeNav, setActiveNav] = useState("Home");
  const [searchQuery, setSearchQuery] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [knowledgeWidth, setKnowledgeWidth] = useState(() => Number(localStorage.getItem("chat-docs-knowledge-width")) || 326);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [enterToSend, setEnterToSend] = useState(() => localStorage.getItem("chat-docs-enter-to-send") !== "false");
  const [showSources, setShowSources] = useState(() => localStorage.getItem("chat-docs-show-sources") !== "false");
  const [compactMode, setCompactMode] = useState(() => localStorage.getItem("chat-docs-compact-mode") === "true");
  const [settingsName, setSettingsName] = useState(userName);
  const [boards, setBoards] = useState(() => JSON.parse(localStorage.getItem("chat-docs-research-boards") || "[]"));
  const [privacyMode, setPrivacyMode] = useState(() => localStorage.getItem("chat-docs-privacy-mode") === "true");
  const [isListening, setIsListening] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState(null);
  const resizingRef = useRef(false);

  useEffect(() => {
    localStorage.setItem("chat-docs-theme", theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("chat-docs-user-name", userName.trim() || "Mike Taylor");
  }, [userName]);

  useEffect(() => {
    localStorage.setItem("chat-docs-knowledge-width", String(knowledgeWidth));
  }, [knowledgeWidth]);

  useEffect(() => {
    localStorage.setItem("chat-docs-enter-to-send", String(enterToSend));
    localStorage.setItem("chat-docs-show-sources", String(showSources));
    localStorage.setItem("chat-docs-compact-mode", String(compactMode));
    localStorage.setItem("chat-docs-privacy-mode", String(privacyMode));
  }, [enterToSend, showSources, compactMode, privacyMode]);

  useEffect(() => {
    if (!privacyMode) localStorage.setItem("chat-docs-research-boards", JSON.stringify(boards));
  }, [boards, privacyMode]);

  useEffect(() => {
    const stopResize = () => {
      resizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    const moveResize = (event) => {
      if (!resizingRef.current) return;
      setKnowledgeWidth(Math.min(520, Math.max(280, event.clientX - (sidebarCollapsed ? 0 : 185))));
    };
    window.addEventListener("pointermove", moveResize);
    window.addEventListener("pointerup", stopResize);
    return () => {
      window.removeEventListener("pointermove", moveResize);
      window.removeEventListener("pointerup", stopResize);
    };
  }, [sidebarCollapsed]);

  const selectedStats = useMemo(
    () => ({
      chunks: selectedDocument?.chunks_stored || 0,
      answers: messages.filter((message) => message.role === "assistant").length,
      sources: messages.reduce((count, message) => count + (message.sources?.length || 0), 0),
    }),
    [messages, selectedDocument],
  );
  const visibleDocuments = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) return documents;
    return documents.filter((document) => document.filename.toLowerCase().includes(normalizedQuery));
  }, [documents, searchQuery]);
  const totalChunks = documents.reduce((sum, document) => sum + (document.chunks_stored || 0), 0);
  const totalAnswers = messages.filter((message) => message.role === "assistant").length;
  const followUps = selectedDocument && messages.length
    ? ["What are the key risks?", "Create an action plan", "Summarize the evidence"]
    : [];
  const actionItems = messages
    .filter((message) => message.role === "assistant")
    .flatMap((message) => (message.text || "").split(/\n/))
    .map((line) => line.replace(/^\s*[-*•]\s*/, "").trim())
    .filter((line) => /^(action|next step|todo|follow up|implement|review|create|prepare|complete|ensure|consider)\b/i.test(line))
    .slice(0, 8);

  useEffect(() => {
    loadDocuments();
  }, []);

  async function loadDocuments(nextSelectedId) {
    setLoadingDocuments(true);
    try {
      const docs = await fetchDocuments();
      setDocuments(docs);
      const nextDocument =
        docs.find((document) => document.document_id === nextSelectedId) ||
        docs.find((document) => document.document_id === selectedDocument?.document_id) ||
        docs[0] ||
        null;
      setSelectedDocument(nextDocument);
      if (nextDocument) {
        await loadHistory(nextDocument.document_id);
      } else {
        setMessages([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingDocuments(false);
    }
  }

  async function loadHistory(documentId) {
    try {
      const history = await fetchHistory(documentId);
      setMessages(historyToMessages(history));
    } catch (err) {
      setError(err.message);
      setMessages([]);
    }
  }

  async function handleSelectDocument(document) {
    setSelectedDocument(document);
    setError("");
    await loadHistory(document.document_id);
  }

  async function handleDeleteDocument(documentId) {
    try {
      await deleteDocument(documentId);
      await loadDocuments();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleUpload(file) {
    setUploading(true);
    setError("");

    try {
      const uploaded = await uploadDocument(file);
      await loadDocuments(uploaded.document_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  useEffect(() => () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, []);

  function stopSpeech() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeakingMessageId(null);
  }

  function speakAnswer(messageId, answer) {
    if (!("speechSynthesis" in window) || !answer) {
      setError("Response reading is not supported in this browser.");
      return;
    }
    if (speakingMessageId === messageId) {
      stopSpeech();
      return;
    }

    const spokenText = answer
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/\((?:source|sources?|reference|references?|page|pages?|slide|slides?|chunk|chunks?)[^)]*\)/gi, " ")
      .replace(/[`*_#>`~-]/g, " ")
      .replace(/\r?\n+/g, ". ")
      .replace(/\s+/g, " ")
      .trim();
    if (!spokenText) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(spokenText);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => setSpeakingMessageId(messageId);
    utterance.onend = () => setSpeakingMessageId((current) => current === messageId ? null : current);
    utterance.onerror = () => setSpeakingMessageId((current) => current === messageId ? null : current);
    setSpeakingMessageId(messageId);
    window.speechSynthesis.speak(utterance);
  }

  async function handleAsk(prompt = question, fromVoice = false) {
    const cleanQuestion = prompt.trim();
    if (!cleanQuestion || !selectedDocument || thinking) return;

    stopSpeech();
    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: cleanQuestion,
      created_at: new Date().toISOString(),
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setThinking(true);
    setError("");

    try {
      const response = await askQuestion(selectedDocument.document_id, cleanQuestion, answerMode);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.answer,
          sources: response.sources,
          created_at: new Date().toISOString(),
        },
      ]);
      if (fromVoice) speakAnswer(crypto.randomUUID(), response.answer);
    } catch (err) {
      setError(err.message);
    } finally {
      setThinking(false);
    }
  }

  async function handleRegenerate(previousQuestion, style = null) {
    if (!previousQuestion || !selectedDocument || thinking) return;

    stopSpeech();
    setThinking(true);
    setError("");
    try {
      const response = await regenerateAnswer(selectedDocument.document_id, previousQuestion, style);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.answer,
          sources: response.sources,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setThinking(false);
    }
  }

  function startVoiceInput() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        setError("Voice input is not supported in this browser.");
        return;
  }
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => { setIsListening(false); setError("Voice input could not be started."); };
      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript.trim();
        setQuestion(transcript);
        if (transcript && selectedDocument) handleAsk(transcript, true);
      };
      recognition.start();
    }

  function saveResearchBoard() {
      if (privacyMode) {
        setError("Privacy mode is on. Turn it off in Settings to save research boards.");
        return;
  }
      if (!selectedDocument || !messages.length) {
        setError("Ask a question before saving a research board.");
        return;
      }
      const board = {
        id: crypto.randomUUID(),
        title: selectedDocument.filename,
        document: selectedDocument.filename,
        messages,
        createdAt: new Date().toISOString(),
      };
      setBoards((current) => [board, ...current].slice(0, 20));
      setError("Research board saved locally.");
    }

  function exportReport() {
    if (!messages.length) {
      setError("Ask a question before exporting a report.");
      return;
    }
    const report = [
      `# Research report: ${selectedDocument?.filename || "Knowledge workspace"}`,
      `Generated ${new Date().toLocaleString()}`,
      "",
      ...messages.map((message) => `## ${message.role === "user" ? "Question" : "Answer"}\n\n${message.text}\n\n${message.sources?.length ? `References: ${message.sources.map((source) => source.location).join(", ")}` : ""}`),
    ].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([report], { type: "text/markdown" }));
    link.download = "chat-with-docs-report.md";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function exportPdfReport() {
        if (!messages.length) {
          setError("Ask a question before exporting a PDF report.");
          return;
        }

        const pdf = new jsPDF({ unit: "pt", format: "a4" });
        const margin = 42;
        const pageWidth = pdf.internal.pageSize.getWidth();
        const pageHeight = pdf.internal.pageSize.getHeight();
        const contentWidth = pageWidth - margin * 2;
        let y = 52;

        const ensureSpace = (height) => {
          if (y + height > pageHeight - margin) {
            pdf.addPage();
            y = margin;
          }
        };
        const writeWrapped = (text, size, options = {}) => {
          const lines = pdf.splitTextToSize(text, contentWidth - (options.indent || 0));
          pdf.setFontSize(size);
          pdf.setFont("helvetica", options.bold ? "bold" : "normal");
          ensureSpace(lines.length * (size + 5));
          pdf.text(lines, margin + (options.indent || 0), y);
          y += lines.length * (size + 5) + (options.gap ?? 5);
        };

        pdf.setTextColor(24, 32, 44);
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(19);
        pdf.text("Chat With Your Docs", margin, y);
        y += 27;
        writeWrapped(`Research report: ${selectedDocument?.filename || "Knowledge workspace"}`, 11, { bold: true, gap: 3 });
        writeWrapped(`Generated ${new Date().toLocaleString()}`, 9, { gap: 18 });

        messages.forEach((message) => {
          const isQuestion = message.role === "user";
          ensureSpace(32);
          pdf.setDrawColor(225, 230, 238);
          pdf.line(margin, y - 3, pageWidth - margin, y - 3);
          writeWrapped(isQuestion ? "QUESTION" : "ANSWER", 8, { bold: true, gap: 6 });

          const parts = (message.text || "").split(/\n+/).map((part) => part.trim()).filter(Boolean);
          parts.forEach((part) => {
            const bullet = /^[-*•]\s+/.test(part);
            const cleanPart = part.replace(/^[-*•]\s+/, "");
            writeWrapped(`${bullet ? "• " : ""}${cleanPart}`, 10, { indent: bullet ? 12 : 0, gap: 4 });
          });

          if (!isQuestion && message.sources?.length) {
            writeWrapped("DOCUMENT REFERENCES", 8, { bold: true, gap: 5 });
            message.sources.forEach((source) => {
              writeWrapped(`• ${source.location}: ${source.text}`, 8.5, { indent: 12, gap: 3 });
            });
          }
          y += 9;
        });

        pdf.save("chat-with-docs-report.pdf");
  }

  return (
    <main className={`app-shell theme-${theme} ${sidebarCollapsed ? "is-sidebar-collapsed" : ""} ${compactMode ? "is-compact" : ""}`}>
      <Sidebar
        documents={documents}
        selectedDocumentId={selectedDocument?.document_id}
        onSelectDocument={handleSelectDocument}
        loadingDocuments={loadingDocuments}
        onDeleteDocument={handleDeleteDocument}
        theme={theme}
        onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")}
        userName={userName}
        onUserNameChange={setUserName}
        activeNav={activeNav}
        onNavigate={setActiveNav}
        collapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((current) => !current)}
        onOpenSettings={() => { setActiveNav("Settings"); setSettingsOpen(true); }}
      />
      {sidebarCollapsed && <button className="sidebar-expand" type="button" onClick={() => setSidebarCollapsed(false)} aria-label="Expand sidebar">›</button>}

      <section className={`workspace ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${activeNav === "Home" ? "home-workspace" : "insights-workspace"}`} style={{ "--knowledge-width": `${knowledgeWidth}px` }}>
        {activeNav === "Dashboard" && (
          <section className="insights-view">
            <div className="insights-heading"><div><p className="eyebrow">Workspace overview</p><h2>Dashboard</h2><p className="document-subtitle">A quick view of your knowledge workspace.</p></div><button className="refresh-button" type="button" onClick={() => loadDocuments()}>↻ Refresh</button></div>
            <div className="metric-cards">
              <article><span>Documents</span><strong>{documents.length}</strong><small>Indexed files</small></article>
              <article><span>Knowledge chunks</span><strong>{totalChunks}</strong><small>Searchable sections</small></article>
              <article><span>Questions answered</span><strong>{totalAnswers}</strong><small>In this conversation</small></article>
            </div>
            <div className="chart-grid">
              <article className="chart-card"><div className="chart-title"><b>Knowledge coverage</b><span>By file</span></div><div className="bar-chart">{documents.slice(0, 6).map((document) => <div className="bar-item" key={document.document_id}><i style={{ height: `${Math.max(10, Math.min(100, (document.chunks_stored || 1) * 8))}%` }} /><span>{document.filename.slice(0, 10)}</span></div>)}</div></article>
              <article className="chart-card"><div className="chart-title"><b>Workspace health</b><span>Live</span></div><div className="donut-chart"><div><strong>{documents.length ? "100%" : "0%"}</strong><span>ready</span></div></div><p className="chart-note">Files are available for grounded questions and source-backed answers.</p></article>
            </div>
          </section>
        )}
        {activeNav === "Analysis" && (
          <section className="insights-view analysis-view">
            <div className="insights-heading"><div><p className="eyebrow">Document intelligence</p><h2>Analysis</h2><p className="document-subtitle">Inspect every indexed file and its searchable content.</p></div></div>
            <div className="analysis-summary"><span><b>{documents.length}</b> files</span><span><b>{totalChunks}</b> chunks</span><span><b>{selectedDocument ? selectedDocument.filename : "No file selected"}</b> selected</span></div>
            <div className="analysis-list">{documents.map((document) => <article className="analysis-card" key={document.document_id}><div className="analysis-file"><span className="file-badge">{document.file_type?.toUpperCase() || "DOC"}</span><div><b>{document.filename}</b><small>Indexed searchable content</small></div></div><dl><div><dt>Chunks</dt><dd>{document.chunks_stored || 0}</dd></div><div><dt>Type</dt><dd>{document.file_type?.toUpperCase() || "DOC"}</dd></div><div><dt>Status</dt><dd className="ready-text">Ready</dd></div></dl><button type="button" onClick={() => { handleSelectDocument(document); setActiveNav("Home"); }}>Open in chat →</button></article>)}</div>
            {!documents.length && <div className="empty-library"><strong>Upload a document to begin analysis</strong><p>Once indexed, file metadata and chunk coverage will appear here.</p></div>}
          </section>
        )}
        <section className="knowledge-panel">
          <h2>Upload Knowledge</h2>
          <UploadZone onUpload={handleUpload} uploading={uploading} error={error} inputId="document-upload" />
          <div className="knowledge-heading">
            <span>Home&nbsp; › &nbsp;<b>Knowledge Base</b></span>
            <label className="add-new" htmlFor="document-upload">＋ Add New</label>
          </div>
          <label className="document-search">
            <span>⌕</span>
            <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search documents" aria-label="Search documents" />
            {searchQuery && <button type="button" onClick={() => setSearchQuery("")} aria-label="Clear document search">×</button>}
          </label>
          <div className="file-table">
            <div className="file-row file-head"><span>FILE NAME⌄</span><span>CHUNKS</span><span>SIZE</span><span>DELETE</span></div>
            {loadingDocuments && <p className="muted">Loading documents...</p>}
            {!loadingDocuments && documents.length === 0 && <div className="empty-library"><strong>No documents yet</strong><p>Upload a file to create a searchable workspace.</p></div>}
            {!loadingDocuments && documents.length > 0 && visibleDocuments.length === 0 && <p className="muted">No documents match “{searchQuery}”.</p>}
            {visibleDocuments.map((document) => (
              <div className={`file-row ${selectedDocument?.document_id === document.document_id ? "is-selected" : ""}`} key={document.document_id}>
                <button className="file-name" type="button" onClick={() => handleSelectDocument(document)}><span className="file-badge">{document.file_type?.toUpperCase() || "DOC"}</span><b>{document.filename}</b></button>
                <span className="chunk-count">{document.chunks_stored || 0}</span>
                <span className="file-size">{formatFileSize(document.size_bytes)}</span>
                <button
                  className="delete-document"
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete ${document.filename} and its chat history?`)) {
                      handleDeleteDocument(document.document_id);
                    }
                  }}
                  aria-label={`Delete ${document.filename}`}
                  title="Delete document and chat history"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </section>
        <div
          className="panel-resizer"
          role="separator"
          aria-label="Resize knowledge base panel"
          aria-valuemin="280"
          aria-valuemax="520"
          aria-valuenow={knowledgeWidth}
          tabIndex={0}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            resizingRef.current = true;
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault();
              setKnowledgeWidth((current) => Math.min(520, Math.max(280, current + (event.key === "ArrowRight" ? 16 : -16))));
            }
          }}
        />

        <section className="chat-panel">
          <header className="chat-header">
            <div className="assistant-title"><span className="assistant-avatar">✦</span><div><h2>AI Assistant</h2><p><span className="live-dot" /> RAG Active</p></div></div>
            <div className="chat-tools">
              <button type="button" onClick={saveResearchBoard} title="Save research board">▣ Board</button>
              <button type="button" onClick={exportReport} title="Export Markdown report">⇩ Export</button>
              <button type="button" onClick={exportPdfReport} title="Export PDF report">PDF</button>
              <button className="chat-add" type="button" onClick={() => { setMessages([]); setQuestion(""); setError(""); }} aria-label="Start a new chat">＋</button>
            </div>
          </header>
          <ChatWindow
            document={selectedDocument}
            messages={messages}
            thinking={thinking}
            onRegenerate={handleRegenerate}
            showSources={showSources}
            followUps={followUps}
            onAskSuggested={handleAsk}
            actionItems={actionItems}
            onSpeak={speakAnswer}
            speakingMessageId={speakingMessageId}
          />
          <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            handleAsk();
          }}
        >
          <div className="composer-field">
            <textarea
            value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (enterToSend && event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleAsk();
                }
              }}
            placeholder={
              selectedDocument
                ? "Ask a question grounded in the selected document..."
                : "Upload or select a document first"
            }
            disabled={!selectedDocument || thinking}
              rows={2}
            />
            <div className="composer-hint">Enter to send · Shift + Enter for new line</div>
            <button type="button" className={`voice-button ${isListening ? "is-listening" : ""}`} onClick={startVoiceInput} disabled={!selectedDocument || thinking} aria-label={isListening ? "Listening" : "Ask by voice"} title="Ask by voice">
              {isListening ? <span className="voice-pulse" /> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 14.5a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 0 0-7 0v5a3.5 3.5 0 0 0 3.5 3.5Z" /><path d="M18.5 11a6.5 6.5 0 0 1-13 0M12 17.5V21M8.5 21h7" /></svg>}
            </button>
          </div>
          <label className="mode-select">
            <span>Answer mode</span>
            <select value={answerMode} onChange={(event) => setAnswerMode(event.target.value)} disabled={!selectedDocument || thinking}>
              <option value="strict">Evidence only</option>
              <option value="short">Quick answer</option>
              <option value="brief">Brief</option>
              <option value="bullets">Bullet points</option>
            </select>
          </label>
          <button className="composer-send" type="submit" disabled={!selectedDocument || thinking || !question.trim()} aria-label="Send question">
            <span>Send</span> <b>↑</b>
          </button>
          </form>
        </section>
      </section>
      {settingsOpen && (
        <div className="settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) { setSettingsOpen(false); setActiveNav("Home"); } }}>
          <section className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <div className="settings-panel-header">
              <div><p className="eyebrow">Workspace preferences</p><h2 id="settings-title">Settings</h2><p>Personalize your experience, Mike.</p></div>
              <button
                type="button"
                className="settings-close"
                onClick={() => { setSettingsOpen(false); setActiveNav("Home"); }}
                aria-label="Close settings"
              >
                ×
              </button>
            </div>
            <div className="settings-profile">
              <span className="settings-avatar">{(userName || "Mike Taylor").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
              <div className="settings-profile-copy"><strong>{userName || "Mike Taylor"}</strong><small>Personal workspace</small></div>
              <button type="button" className="profile-edit-button" onClick={() => setSettingsName(userName)} aria-label="Edit user name">Edit</button>
            </div>
            <div className="settings-name-editor">
              <label htmlFor="settings-user-name">Display name</label>
              <div className="settings-name-input">
                <input id="settings-user-name" value={settingsName} onChange={(event) => setSettingsName(event.target.value)} placeholder="Mike Taylor" />
                <button type="button" onClick={() => { const nextName = settingsName.trim() || "Mike Taylor"; setUserName(nextName); setSettingsName(nextName); }}>Save</button>
              </div>
            </div>
            <div className="settings-section">
              <h3>Appearance</h3>
              <div className="theme-options">
                <button type="button" className={theme === "light" ? "selected" : ""} onClick={() => setTheme("light")}><span>☼</span> Light</button>
                <button type="button" className={theme === "dark" ? "selected" : ""} onClick={() => setTheme("dark")}><span>◐</span> Dark</button>
              </div>
              <label className="setting-row"><span><b>Compact layout</b><small>Use tighter spacing for more content.</small></span><input type="checkbox" checked={compactMode} onChange={(event) => setCompactMode(event.target.checked)} /></label>
            </div>
            <div className="settings-section">
              <h3>Chat preferences</h3>
              <label className="setting-row"><span><b>Enter to send</b><small>Press Enter to send; Shift + Enter adds a line.</small></span><input type="checkbox" checked={enterToSend} onChange={(event) => setEnterToSend(event.target.checked)} /></label>
              <label className="setting-row"><span><b>Show sources</b><small>Display citations below grounded answers.</small></span><input type="checkbox" checked={showSources} onChange={(event) => setShowSources(event.target.checked)} /></label>
              <label className="setting-row"><span><b>Privacy mode</b><small>Keep research boards and preferences out of saved local activity.</small></span><input type="checkbox" checked={privacyMode} onChange={(event) => setPrivacyMode(event.target.checked)} /></label>
              {boards.length > 0 && <div className="saved-boards"><b>Saved research boards</b>{boards.slice(0, 3).map((board) => <span key={board.id}>▣ {board.title}</span>)}</div>}
            </div>
            <button type="button" className="settings-done" onClick={() => setSettingsOpen(false)}>Done</button>
          </section>
        </div>
      )}
    </main>
  );
}

export default App;
