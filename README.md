# Chat With Your Docs v2

Chat With Your Docs is a full-stack Retrieval-Augmented Generation portfolio project. Users upload documents, the backend extracts and chunks their text, embeddings are stored in MongoDB, and Gemini answers questions using only retrieved document context.

## Stack

- Backend: Python, FastAPI, Pydantic, PyMongo
- Parsing: pypdf, python-pptx, pandas
- RAG: sentence-transformers `all-MiniLM-L6-v2`, cosine similarity retrieval
- LLM: Google Gemini API through the current Google Gen AI SDK
- Frontend: React, Vite, JavaScript ES6+, HTML5, CSS3
- Storage: MongoDB

## Architecture

```text
Upload PDF/PPTX/TXT/MD/CSV
        |
        v
React UploadZone -> POST /upload -> FastAPI route
        |                         -> parsers.py extracts text + locations
        |                         -> rag.py chunks and embeds text
        |                         -> database.py stores metadata + chunks
        v
Sidebar lists docs <- GET /documents

User asks question
        |
        v
React ChatWindow -> POST /ask -> FastAPI route
        |                    -> database.py loads chunks
        |                    -> rag.py embeds question + retrieves top chunks
        |                    -> llm.py builds grounded Gemini prompt
        |                    -> database.py stores chat history
        v
Answer + source snippets with page/slide/row metadata
```

## Features

- Multi-format upload: `.pdf`, `.pptx`, `.txt`, `.md`, `.csv`
- Format-aware parsing with source metadata such as `page 2`, `slide 3`, and `row 12`
- CSV rows are converted into readable key-value blocks before embedding
- Chunking around 500 characters with overlap, while preserving CSV rows
- Local embeddings with `sentence-transformers`
- MongoDB collections for document metadata, chunks, and chat history
- Grounded Gemini prompt that refuses answers not found in the document
- REST API endpoints for upload, ask, document list, and document history
- Professional React UI with sidebar, drag-and-drop upload, chat history, thinking state, and expandable sources

## Project Structure

```text
chat-with-docs/
  backend/
    main.py          # FastAPI routes
    models.py        # Pydantic request/response schemas
    database.py      # MongoDB connection and collection helpers
    parsers.py       # PDF/PPTX/TXT/MD/CSV extraction
    rag.py           # Chunking, embeddings, cosine retrieval
    llm.py           # Gemini prompt construction and API call
    requirements.txt
    .env.example
  frontend/
    src/
      App.jsx
      api.js
      App.css
      components/
        Sidebar.jsx
        UploadZone.jsx
        ChatWindow.jsx
        MessageBubble.jsx
    package.json
    vite.config.js
  README.md
  SETUP.md
```

## Skill-to-Code Alignment

| Skill | Demonstrated in |
|---|---|
| Python | `backend/main.py`, `parsers.py`, `rag.py`, `database.py`, `llm.py` |
| JavaScript ES6+ | `frontend/src/api.js`, `frontend/src/App.jsx`, component files |
| React.js | Functional components and hooks in `frontend/src/` |
| HTML5 | Semantic JSX structure and `frontend/index.html` |
| CSS3 | Grid/flex layouts and responsive styling in `frontend/src/App.css` |
| RESTful APIs, HTTP, JSON | FastAPI routes in `backend/main.py` |
| AI fundamentals, LLMs | Gemini integration in `backend/llm.py` |
| Prompt Engineering | Grounded prompt template and comment in `backend/llm.py` |
| RAG | Parse -> chunk -> embed -> store -> retrieve -> generate flow |
| MongoDB | Collection design and helpers in `backend/database.py` |
| AI application lifecycle | Clear separation between ingestion, processing, storage, retrieval, generation, and UI |

See [SETUP.md](SETUP.md) for run instructions.
