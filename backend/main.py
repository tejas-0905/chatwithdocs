import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from database import (
    add_chat_turn,
    create_document,
    get_chat_history,
    get_chunks_for_document,
    get_document,
    init_indexes,
    insert_chunks,
    list_documents,
    ping_database,
    delete_document,
)
from llm import generate_answer, generate_structured_answer
from models import AskRequest, AskResponse, DocumentSummary, HistoryItem, Source, UploadResponse
from parsers import ACCEPTED_EXTENSIONS, parse_document
from rag import chunk_sections, embed_texts, is_summary_question, retrieve_top_chunks

app = FastAPI(title="Chat With Your Docs API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    try:
        ping_database()
        init_indexes()
    except Exception as exc:
        raise RuntimeError("MongoDB is not reachable. Check MONGO_URI.") from exc


@app.get("/")
def root() -> dict:
    return {"status": "ok", "message": "Chat With Your Docs API v2 is running"}


@app.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"description": "Bad input"}, 500: {"description": "Upload failed"}},
)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    try:
        raw_bytes = await file.read()
        file_type, sections = parse_document(file.filename, raw_bytes)
        chunks = chunk_sections(sections, file_type)
        if not chunks:
            raise HTTPException(status_code=400, detail="No searchable text chunks were found.")

        embeddings = embed_texts([chunk["text"] for chunk in chunks])
        document_id = str(uuid.uuid4())
        chunk_records = [
            {
                "document_id": document_id,
                "chunk_index": index,
                "text": chunk["text"],
                "location": chunk["location"],
                "embedding": embeddings[index],
            }
            for index, chunk in enumerate(chunks)
        ]

        create_document(
            {
                "document_id": document_id,
                "filename": file.filename,
                "file_type": file_type,
                "chunks_stored": len(chunk_records),
                "size_bytes": len(raw_bytes),
            }
        )
        insert_chunks(chunk_records)

        return UploadResponse(
            document_id=document_id,
            filename=file.filename,
            file_type=file_type,
            chunks_stored=len(chunk_records),
        )
    except ValueError as exc:
        accepted = ", ".join(sorted(ACCEPTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"{exc} Accepted formats: {accepted}") from exc
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not save the document.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Upload failed. Please try again.") from exc


@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        document = get_document(request.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")

        chunks = get_chunks_for_document(request.document_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for this document.")

        is_document_summary = is_summary_question(question)
        top_k = 12 if is_document_summary else 6
        source_chunks = retrieve_top_chunks(question, chunks, top_k=top_k)
        # Summaries need document-wide coverage; focused questions still use
        # semantic retrieval to keep the prompt small and precise.
        top_chunks = (
            [{**chunk, "score": None} for chunk in chunks]
            if is_document_summary
            else source_chunks
        )
        # default sources derived from retrieval
        default_sources = [
            Source(
                text=chunk["text"],
                location=chunk["location"],
                score=round(float(chunk["score"]), 4) if chunk.get("score") is not None else None,
            )
            for chunk in source_chunks
        ]

        if not top_chunks:
            answer_text = "I don't have enough information in the document to answer that."
            sources = []
            confidence = 0.0
            raw_output = None
            add_chat_turn(
                document_id=request.document_id,
                question=question,
                answer=answer_text,
                sources=[],
            )
            return AskResponse(answer=answer_text, sources=[], confidence=confidence, raw_model_output=raw_output)

        # Use structured generation when possible to get parsed sources/confidence.
        try:
            # Keep the default response scannable and evidence-oriented.
            structured = generate_structured_answer(question, top_chunks, style="bullets")
            answer_text = structured.get("answer", "")
            model_sources_raw = structured.get("sources", []) or []
            confidence = structured.get("confidence")
            raw_output = structured.get("raw")

            allowed_locations = {chunk["location"] for chunk in top_chunks}
            if model_sources_raw:
                # map model-returned sources to Source objects
                sources = [
                    Source(text=s.get("text"), location=s.get("location"), score=s.get("score"))
                    for s in model_sources_raw
                    if s.get("location") in allowed_locations and s.get("text")
                ]
            else:
                sources = default_sources
        except Exception:
            # on any error, fall back to original generation
            answer_text = generate_answer(question, top_chunks)
            sources = default_sources
            confidence = None
            raw_output = None

        add_chat_turn(
            document_id=request.document_id,
            question=question,
            answer=answer_text,
            sources=[source.model_dump() for source in sources],
        )

        return AskResponse(answer=answer_text, sources=sources, confidence=confidence, raw_model_output=raw_output)
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not read document data.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate an answer: {exc}") from exc


@app.post("/ask/regenerate", response_model=AskResponse)
def regenerate_question(request: AskRequest, style: str | None = None) -> AskResponse:
    """Regenerate an answer for the given question using a stricter or alternative style.

    Query param `style` can be 'short', 'bullets', or 'strict' to adjust generation.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        document = get_document(request.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")

        chunks = get_chunks_for_document(request.document_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="No chunks found for this document.")

        is_document_summary = is_summary_question(question)
        top_k = 12 if is_document_summary else 6
        source_chunks = retrieve_top_chunks(question, chunks, top_k=top_k)
        top_chunks = (
            [{**chunk, "score": None} for chunk in chunks]
            if is_document_summary
            else source_chunks
        )

        if not top_chunks:
            answer_text = "I don't have enough information in the document to answer that."
            add_chat_turn(request.document_id, question, answer_text, [])
            return AskResponse(answer=answer_text, sources=[], confidence=0.0, raw_model_output=None)

        structured = generate_structured_answer(question, top_chunks, style=style)
        answer_text = structured.get("answer", "")
        model_sources_raw = structured.get("sources", []) or []
        confidence = structured.get("confidence")
        raw_output = structured.get("raw")

        allowed_locations = {chunk["location"] for chunk in top_chunks}
        if model_sources_raw:
            sources = [
                Source(text=s.get("text"), location=s.get("location"), score=s.get("score"))
                for s in model_sources_raw
                if s.get("location") in allowed_locations and s.get("text")
            ]
        else:
            sources = [
                Source(
                    text=chunk["text"],
                    location=chunk["location"],
                    score=round(float(chunk["score"]), 4) if chunk.get("score") is not None else None,
                )
                for chunk in source_chunks
            ]

        add_chat_turn(
            document_id=request.document_id,
            question=question,
            answer=answer_text,
            sources=[source.model_dump() for source in sources],
        )

        return AskResponse(answer=answer_text, sources=sources, confidence=confidence, raw_model_output=raw_output)
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not read document data.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate an answer: {exc}") from exc


@app.delete("/documents/{document_id}")
def delete_document_route(document_id: str) -> dict:
    try:
        # Verify existence
        if not get_document(document_id):
            raise HTTPException(status_code=404, detail="Document not found.")
        delete_document(document_id)
        return {"status": "deleted", "document_id": document_id}
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not delete document.") from exc


@app.get("/documents", response_model=list[DocumentSummary])
def documents() -> list[dict]:
    try:
        return list_documents()
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not load documents.") from exc


@app.get("/documents/{document_id}/history", response_model=list[HistoryItem])
def document_history(document_id: str) -> list[dict]:
    try:
        if not get_document(document_id):
            raise HTTPException(status_code=404, detail="Document not found.")
        return get_chat_history(document_id)
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Could not load chat history.") from exc
