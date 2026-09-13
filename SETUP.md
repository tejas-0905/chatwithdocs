# Setup Guide

## 1. Backend Environment

Open a terminal in `backend/`.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Fill in `backend/.env`:

```text
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=chat_with_docs
GEMINI_API_KEY=your_real_key_here
GEMINI_MODEL=gemini-2.5-flash
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://chatwithdocs-front-chi.vercel.app
```

## 2. Gemini API Key

1. Go to Google AI Studio.
2. Create an API key.
3. Paste it into `backend/.env` as `GEMINI_API_KEY`.

Do not commit `.env` or share the key.

## 3. MongoDB

Local MongoDB:

1. Install MongoDB Community Server.
2. Start the MongoDB service.
3. Use `MONGO_URI=mongodb://localhost:27017`.

MongoDB Atlas:

1. Create a free Atlas cluster.
2. Create a database user.
3. Add your IP address to Network Access.
4. Copy the connection string into `MONGO_URI`.

## 4. Run the Backend

From `backend/` with the virtual environment active:

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8020
```

Check:

```text
http://127.0.0.1:8020/docs
```

## 5. Frontend Environment

Open a second terminal in `frontend/`.

```powershell
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Optional frontend env file:

```text
VITE_API_BASE_URL=http://127.0.0.1:8020
```

## 6. Manual Steps Still Required

- Install Python dependencies with `pip install -r requirements.txt`.
- Install frontend dependencies with `npm install`.
- Create `backend/.env` from `.env.example`.
- Add your own Gemini API key.
- Run MongoDB locally or configure MongoDB Atlas.
- Start the backend before using uploads or chat from the frontend.
- On Render, set `CORS_ORIGINS` to include the exact Vercel frontend URL, then redeploy the backend. Browser origins must match exactly (scheme and hostname).
- Verify the deployed backend after a redeploy at `https://chat-with-docs-api.onrender.com/health`; it should return `{"status":"ok"}`.

## 7. Quick API Reference

```text
POST /upload
multipart/form-data: file
returns: { document_id, filename, file_type, chunks_stored }

POST /ask
json: { document_id, question }
returns: { answer, sources: [{ text, location, score }] }

GET /documents
returns: [{ document_id, filename, file_type, chunks_stored, uploaded_at }]

GET /documents/{document_id}/history
returns: [{ question, answer, sources, created_at }]
```
