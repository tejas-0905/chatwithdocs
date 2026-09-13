import hashlib
import os
import re
from typing import Any

import numpy as np

from parsers import ParsedSection

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
FALLBACK_EMBEDDING_DIMENSIONS = 384
STOP_WORDS = {
    "and",
    "are",
    "about",
    "answer",
    "any",
    "based",
    "brief",
    "bullet",
    "bullets",
    "document",
    "five",
    "four",
    "give",
    "how",
    "for",
    "from",
    "important",
    "into",
    "main",
    "most",
    "the",
    "this",
    "that",
    "point",
    "points",
    "question",
    "summarise",
    "summarize",
    "summary",
    "tell",
    "three",
    "what",
    "with",
    "you",
    "your",
}
SUMMARY_WORDS = {"summarize", "summarise", "summary", "overview", "brief", "gist"}
USE_TRANSFORMER_EMBEDDINGS = os.getenv("USE_TRANSFORMER_EMBEDDINGS", "").lower() in {
    "1",
    "true",
    "yes",
}

_model: Any | None | bool = None


def get_model() -> Any | None:
    if not USE_TRANSFORMER_EMBEDDINGS:
        return None

    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
        except Exception:
            _model = False
    return _model or None


def chunk_sections(
    sections: list[ParsedSection],
    file_type: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[dict]:
    chunks = []

    for section in sections:
        if file_type == "csv":
            chunks.append({"text": section.text, "location": section.location})
            continue

        section_chunks = _chunk_text(section.text, chunk_size, overlap)
        for index, text in enumerate(section_chunks, start=1):
            location = (
                section.location
                if len(section_chunks) == 1
                else f"{section.location}, chunk {index}"
            )
            chunks.append({"text": text, "location": location})

    return chunks


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = " ".join(text.split())
    if len(cleaned) <= chunk_size:
        return [cleaned] if cleaned else []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            natural_break = max(
                cleaned.rfind(". ", start, end),
                cleaned.rfind("\n", start, end),
                cleaned.rfind(" ", start, end),
            )
            if natural_break > start + chunk_size * 0.6:
                end = natural_break + 1

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)

    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    if model is not None:
        embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.tolist()
    return [_hash_embedding(text) for text in texts]


def _hash_embedding(text: str) -> list[float]:
    vector = np.zeros(FALLBACK_EMBEDDING_DIMENSIONS, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % FALLBACK_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector.tolist()
    return (vector / norm).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    vector_a = np.array(a)
    vector_b = np.array(b)
    denominator = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)
    if denominator == 0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / denominator)


def is_summary_question(question: str) -> bool:
    terms = _content_terms(question)
    raw_terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    return bool(raw_terms & SUMMARY_WORDS) and not terms


def _content_terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 2 and term not in STOP_WORDS
    }


def _keyword_overlap_score(question_terms: set[str], text: str) -> float:
    if not question_terms:
        return 0.0

    text_terms = _content_terms(text)
    if not text_terms:
        return 0.0

    return len(question_terms & text_terms) / len(question_terms)


def retrieve_overview_chunks(chunks: list[dict], max_chunks: int = 12) -> list[dict]:
    if len(chunks) <= max_chunks:
        return [{**chunk, "score": None} for chunk in chunks]

    selected_indexes = {0}
    heading_candidates = []
    for index, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        heading_score = 0
        if "#" in text:
            heading_score += 2
        if re.search(r"\b(requirement|setup|step|object|workflow|security|report|dashboard)\b", text, re.I):
            heading_score += 1
        if heading_score:
            heading_candidates.append((heading_score, index))

    heading_candidates.sort(key=lambda item: (-item[0], item[1]))
    for _, index in heading_candidates[: max_chunks - 1]:
        selected_indexes.add(index)

    step = max(1, len(chunks) // max_chunks)
    index = 0
    while len(selected_indexes) < max_chunks and index < len(chunks):
        selected_indexes.add(index)
        index += step

    ordered_indexes = sorted(selected_indexes)[:max_chunks]
    return [{**chunks[index], "score": None} for index in ordered_indexes]


def retrieve_top_chunks(question: str, chunks: list[dict], top_k: int = 4) -> list[dict]:
    if is_summary_question(question):
        return retrieve_overview_chunks(chunks, max_chunks=max(top_k, 10))

    question_embedding = embed_texts([question])[0]
    question_terms = _content_terms(question)

    scored = []
    identity_question = bool(
        re.search(r"\b(name|names|author|authors|person|people|made|created|prepared|submitted|title)\b", question, re.I)
    )
    for chunk in chunks:
        semantic_score = cosine_similarity(question_embedding, chunk["embedding"])
        keyword_score = _keyword_overlap_score(question_terms, chunk.get("text", ""))
        text = chunk.get("text", "")
        # Cover/title slides often contain the answer to authorship/title questions
        # but do not share the person's name with the user's wording.
        identity_bonus = 0.35 if identity_question and re.search(
            r"\b(submitted by|prepared by|author|authors|presented by|project synopsis|title)\b",
            text,
            re.I,
        ) else 0.0
        score = (semantic_score * 0.75) + (keyword_score * 0.25) + identity_bonus
        scored.append({**chunk, "score": score})

    scored.sort(key=lambda chunk: chunk["score"], reverse=True)
    return scored[:top_k]
