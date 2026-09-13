import json
import os
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone
from urllib.parse import quote_plus

from bson import ObjectId
from dotenv import load_dotenv
from pymongo.errors import PyMongoError
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "chat_with_docs")
LOCAL_STORE_PATH = Path(os.getenv("LOCAL_STORE_PATH", "data/store.json"))

_client: MongoClient | None = None
_use_local_store = False
_store_lock = RLock()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(_normalize_mongo_uri(MONGO_URI), serverSelectionTimeoutMS=5000)
    return _client


def _normalize_mongo_uri(uri: str) -> str:
    scheme_separator = "://"
    if scheme_separator not in uri:
        return uri

    scheme, rest = uri.split(scheme_separator, 1)
    auth_and_host, separator, path_and_query = rest.partition("/")
    if "@" not in auth_and_host or ":" not in auth_and_host.rsplit("@", 1)[0]:
        return uri

    userinfo, host = auth_and_host.rsplit("@", 1)
    username, password = userinfo.split(":", 1)
    escaped_userinfo = f"{quote_plus(username)}:{quote_plus(password)}"
    suffix = f"{separator}{path_and_query}" if separator else ""
    return f"{scheme}{scheme_separator}{escaped_userinfo}@{host}{suffix}"


def get_collection(name: str) -> Collection:
    return get_client()[MONGO_DB_NAME][name]


def init_indexes() -> None:
    if _use_local_store:
        _ensure_local_store()
        return

    documents_collection = get_collection("documents")
    chunks_collection = get_collection("chunks")
    chats_collection = get_collection("chats")
    documents_collection.create_index("document_id", unique=True)
    chunks_collection.create_index([("document_id", ASCENDING), ("chunk_index", ASCENDING)])
    chats_collection.create_index([("document_id", ASCENDING), ("created_at", ASCENDING)])


def ping_database() -> None:
    global _use_local_store
    try:
        get_client().admin.command("ping")
        _use_local_store = False
    except PyMongoError:
        _use_local_store = True
        _ensure_local_store()


def create_document(document: dict) -> None:
    if _use_local_store:
        _append_local_record(
            "documents",
            {
                **document,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return

    # Metadata, chunks, and chat turns are separated so the UI can list documents
    # quickly while retrieval reads only the embeddings needed for the active doc.
    get_collection("documents").insert_one(
        {
            **document,
            "uploaded_at": datetime.now(timezone.utc),
        }
    )


def insert_chunks(chunks: list[dict]) -> None:
    if _use_local_store:
        _extend_local_records("chunks", chunks)
        return

    if chunks:
        get_collection("chunks").insert_many(chunks)


def list_documents() -> list[dict]:
    if _use_local_store:
        documents = _read_local_store()["documents"]
        return sorted(documents, key=lambda document: document["uploaded_at"], reverse=True)

    documents = get_collection("documents").find({}, {"_id": 0}).sort("uploaded_at", -1)
    return list(documents)


def get_document(document_id: str) -> dict | None:
    if _use_local_store:
        for document in _read_local_store()["documents"]:
            if document["document_id"] == document_id:
                return document
        return None

    return get_collection("documents").find_one({"document_id": document_id}, {"_id": 0})


def get_chunks_for_document(document_id: str) -> list[dict]:
    if _use_local_store:
        chunks = [
            chunk
            for chunk in _read_local_store()["chunks"]
            if chunk["document_id"] == document_id
        ]
        return sorted(chunks, key=lambda chunk: chunk["chunk_index"])

    chunks = get_collection("chunks").find({"document_id": document_id}).sort("chunk_index", 1)
    return [_strip_mongo_id(chunk) for chunk in chunks]


def add_chat_turn(document_id: str, question: str, answer: str, sources: list[dict]) -> None:
    if _use_local_store:
        _append_local_record(
            "chats",
            {
                "document_id": document_id,
                "question": question,
                "answer": answer,
                "sources": sources,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return

    get_collection("chats").insert_one(
        {
            "document_id": document_id,
            "question": question,
            "answer": answer,
            "sources": sources,
            "created_at": datetime.now(timezone.utc),
        }
    )


def get_chat_history(document_id: str) -> list[dict]:
    if _use_local_store:
        history = [
            item
            for item in _read_local_store()["chats"]
            if item["document_id"] == document_id
        ]
        return sorted(history, key=lambda item: item["created_at"])

    history = get_collection("chats").find({"document_id": document_id}).sort("created_at", 1)
    return [_strip_mongo_id(item) for item in history]


def _strip_mongo_id(record: dict) -> dict:
    cleaned = dict(record)
    value = cleaned.pop("_id", None)
    if isinstance(value, ObjectId):
        cleaned["mongo_id"] = str(value)
    return cleaned


def _ensure_local_store() -> None:
    LOCAL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_STORE_PATH.exists():
        _write_local_store({"documents": [], "chunks": [], "chats": []})


def _read_local_store() -> dict:
    _ensure_local_store()
    with _store_lock:
        with LOCAL_STORE_PATH.open("r", encoding="utf-8") as store_file:
            return json.load(store_file)


def _write_local_store(data: dict) -> None:
    with _store_lock:
        with LOCAL_STORE_PATH.open("w", encoding="utf-8") as store_file:
            json.dump(data, store_file)


def _append_local_record(collection: str, record: dict) -> None:
    data = _read_local_store()
    data[collection].append(record)
    _write_local_store(data)


def _extend_local_records(collection: str, records: list[dict]) -> None:
    if not records:
        return
    data = _read_local_store()
    data[collection].extend(records)
    _write_local_store(data)


def delete_document(document_id: str) -> None:
    """Delete document metadata, its chunks, and chat history.

    Works with both local-store fallback and MongoDB.
    """
    if _use_local_store:
        data = _read_local_store()
        data["documents"] = [d for d in data["documents"] if d.get("document_id") != document_id]
        data["chunks"] = [c for c in data["chunks"] if c.get("document_id") != document_id]
        data["chats"] = [h for h in data["chats"] if h.get("document_id") != document_id]
        _write_local_store(data)
        return

    get_collection("documents").delete_one({"document_id": document_id})
    get_collection("chunks").delete_many({"document_id": document_id})
    get_collection("chats").delete_many({"document_id": document_id})
