const API_BASE = (import.meta.env.VITE_API_BASE_URL || "https://chat-with-docs-api.onrender.com")
  .replace(/\/+$/, "");

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    throw new Error(
      `Cannot reach the backend at ${API_BASE}. Check that the Render service is running and that its CORS_ORIGINS setting allows this frontend.`,
    );
  }

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }

  return payload;
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  return request("/upload", {
    method: "POST",
    body: formData,
  });
}

export async function askQuestion(documentId, question, style = null) {
  const url = style ? `/ask/regenerate?style=${encodeURIComponent(style)}` : "/ask";
  return request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, question }),
  });
}

export async function regenerateAnswer(documentId, question, style = null) {
  const url = style ? `/ask/regenerate?style=${encodeURIComponent(style)}` : '/ask/regenerate';
  return request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId, question }),
  });
}

export async function fetchDocuments() {
  return request("/documents");
}

export async function deleteDocument(documentId) {
  return request(`/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  });
}

export async function fetchHistory(documentId) {
  return request(`/documents/${documentId}/history`);
}
