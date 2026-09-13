import { useState } from "react";

const acceptedFormats = ".pdf,.pptx,.txt,.md,.csv";

export function UploadZone({ onUpload, uploading, error, inputId = "document-upload" }) {
  const [dragActive, setDragActive] = useState(false);

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onUpload(file);
  };

  return (
    <section
      className={`upload-zone ${dragActive ? "is-active" : ""} ${error ? "has-error" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
    >
      <div className="upload-icon" aria-hidden="true">
        {uploading ? <span className="spinner" /> : "↑"}
      </div>
      <div>
        <p className="upload-kicker">Knowledge source</p>
        <h2>{uploading ? "Indexing your document" : "Click to upload or drag and drop"}</h2>
        <p>PDF, TXT, MD or DOCX (max. 10MB)</p>
        {error && <p className="error-text">{error}</p>}
      </div>
      <label className="upload-button">
        Browse
        <input
          type="file"
          id={inputId}
          accept={acceptedFormats}
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onUpload(file);
            event.target.value = "";
          }}
          hidden
        />
      </label>
    </section>
  );
}
