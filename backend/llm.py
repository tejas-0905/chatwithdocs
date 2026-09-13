import json
import os
import re

from dotenv import load_dotenv

from rag import is_summary_question

try:
    from google import genai as google_genai
except ImportError:
    google_genai = None

try:
    import google.generativeai as legacy_google_genai
except ImportError:
    legacy_google_genai = None

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
USE_GEMINI = os.getenv("USE_GEMINI", "true").lower() not in {"0", "false", "no"}


def build_grounded_prompt(question: str, context_chunks: list[dict], structured: bool = False, style: str | None = None) -> str:
    context = "\n\n".join(
        f"[Source: {chunk['location']}]\n{chunk['text']}" for chunk in context_chunks
    )

    structured_instructions = ""
    if structured:
        structured_instructions = (
            "Return a single valid JSON object with keys: answer (string), sources (array of {location, text, score?}), confidence (number between 0 and 1). "
            "Do not add any extra text outside the JSON object."
        )

    style_instructions = ""
    if style == 'short':
        style_instructions = "Provide a very concise answer: 1-2 short sentences."
    elif style == 'brief':
        style_instructions = (
            "Provide a concise but complete answer in 2-3 sentences or up to 3 focused Markdown bullets. "
            "Include the central point and the most important supporting result; do not omit the answer's subject."
        )
    elif style == 'bullets':
        style_instructions = (
            "Return a proper brief summary as 4-6 separate Markdown bullets in the answer field. "
            "Cover the document's purpose or research question, approach or data, main findings, "
            "important results, and conclusion or limitations when the context supports them. "
            "Put exactly one complete, grammatically finished point on each new line. "
            "Never combine multiple labeled categories into one bullet or one paragraph."
        )
    elif style == 'strict':
        style_instructions = "Be concise and strictly grounded in the provided context; avoid any information not present in the context."

    # The prompt narrows the model's behavior to retrieval-grounded synthesis, which
    # reduces hallucination risk and makes missing evidence an explicit valid answer.
    return f"""You are an AI document analyst for a retrieval-augmented generation app.
Answer the user's question using ONLY the retrieved document context below.

{structured_instructions} {style_instructions}

Rules:
- If the answer is not present in the context, say: "I don't have enough information in the document to answer that."
- Do not use outside knowledge.
- Cite source locations inline when useful, for example: (page 2) or (slide 4).
- Synthesize the context into a clear answer. Do not copy long raw fragments.
- For document-wide summary requests, inspect all provided chunks before answering.
  Cover the document's major sections, recurring themes, important entities, datasets,
  methods, metrics, findings, and limitations. Do not base the summary on only the first
  or most similar passage.
- Use Markdown bold for the most important names, methods, datasets, metrics, results, and conclusions
  (for example, **VGG16**, **APTOS**, or **99% accuracy**). Do not bold entire sentences.
- Start every new bullet, heading, and sentence with a capital letter.
- Every bullet must be a complete sentence with a clear subject and ending punctuation.
- Never end a sentence or bullet mid-word. Do not include incomplete fragments or model commentary.
- If the user asks for bullets, return exactly that many bullets when a number is given.
- If the user requests a word limit (e.g., 'in 30 words'), put the concise answer first and keep within that limit.
- Keep each bullet focused on one complete idea.
- Ignore irrelevant or low-value fragments, broken words, repeated overlap, and source labels.
- Be concise, specific, and faithful to the document.

Retrieved context:
{context}

Question:
{question}

Grounded answer or JSON:"""


def _call_model(prompt: str) -> str:
    """Call the configured model and return raw text. Returns empty string on failure or when model not configured."""
    if not USE_GEMINI or not GEMINI_API_KEY:
        return ""

    try:
        if google_genai is not None:
            client = google_genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return getattr(response, "text", "") or ""
        elif legacy_google_genai is not None:
            legacy_google_genai.configure(api_key=GEMINI_API_KEY)
            response = legacy_google_genai.GenerativeModel(GEMINI_MODEL).generate_content(prompt)
            return getattr(response, "text", "") or ""
    except Exception:
        return ""

    return ""


def generate_structured_answer(question: str, context_chunks: list[dict], style: str | None = None) -> dict:
    """Request structured JSON from the model and parse it. Falls back to text/local generation.

    Returns a dict: {answer: str, sources: list[dict], confidence: float|None, raw: str}
    """
    prompt = build_grounded_prompt(question, context_chunks, structured=True, style=style)
    raw = _call_model(prompt).strip()

    parsed = None
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            # extract first JSON object substring if present
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    parsed = None

    if parsed:
        answer = str(parsed.get("answer", "") or "").strip()
        sources_raw = parsed.get("sources", []) or []
        confidence = parsed.get("confidence")

        normalized_sources = []
        for s in sources_raw:
            if isinstance(s, dict) and s.get("location") and s.get("text"):
                normalized_sources.append({
                    "location": s.get("location"),
                    "text": s.get("text"),
                    "score": s.get("score"),
                })

        try:
            answer = _postprocess_answer(answer, context_chunks, question, style=style)
        except Exception:
            pass

        return {"answer": answer, "sources": normalized_sources, "confidence": confidence, "raw": raw}

    # fallback: try free-text model prompt
    text_prompt = build_grounded_prompt(question, context_chunks, structured=False, style=style)
    model_text = _call_model(text_prompt).strip()
    if model_text:
        processed = model_text
        try:
            processed = _postprocess_answer(model_text, context_chunks, question, style=style)
        except Exception:
            pass
        return {"answer": processed, "sources": [], "confidence": None, "raw": model_text}

    # final fallback: local evidence-based generator
    local = generate_local_answer(question, context_chunks, style=style)
    return {"answer": local, "sources": [], "confidence": None, "raw": ""}


def generate_answer(question: str, context_chunks: list[dict]) -> str:
    # Backwards-compatible simple string interface — prefer structured generation when possible
    structured = generate_structured_answer(question, context_chunks)
    return structured.get("answer", "")


def generate_local_answer(question: str, context_chunks: list[dict], style: str | None = None) -> str:
    """Create a concise, evidence-grounded answer from retrieved chunks.

    Behavior:
    - If the question is a summary-style request, delegate to generate_local_summary.
    - Otherwise pick the top scoring sentences and synthesize a short paragraph.
    - Honor explicit requests like "in N words" or "in N bullets" when possible.
    - If the user explicitly asked for a list (bullet/list/points), return bullets with inline citations.
    """
    if not context_chunks:
        return "I don't have enough information in the document to answer that."

    if is_summary_question(question):
        return generate_local_summary(question, context_chunks, style=style)

    # detect requested word limit (e.g., "in 30 words")
    word_limit = _requested_word_count(question)

    question_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", question.lower())
        if len(term) > 2 and term not in {"document", "question", "answer", "tell", "about"}
    }
    identity_question = bool(
        re.search(r"\b(name|names|author|authors|person|people|made|created|prepared|submitted|title)\b", question, re.I)
    )

    scored_sentences = []
    for chunk in context_chunks:
        sentences = re.split(r"(?<=[.!?])\s+", chunk.get("text", "").strip())
        for sentence in sentences:
            cleaned = sentence.strip()
            if not cleaned:
                continue
            sentence_terms = set(re.findall(r"[a-z0-9]+", cleaned.lower()))
            score = len(question_terms & sentence_terms)
            if identity_question and re.search(
                r"\b(submitted by|prepared by|author|authors|presented by|project synopsis|title)\b",
                cleaned,
                re.I,
            ):
                score += 10
            scored_sentences.append((score, cleaned, chunk.get("location", "document")))

    scored_sentences.sort(key=lambda item: item[0], reverse=True)
    selected = [item for item in scored_sentences if item[0] > 0][:4]
    if not selected:
        return "I don't have enough information in the document to answer that."

    # If user explicitly asked for bullets or a list, return bullets with citations
    if style == "bullets" or re.search(r"\b(bullet|bullets|list|points)\b", question.lower()):
        return "\n".join(f"- {sentence} ({location})" for _, sentence, location in selected)

    # Otherwise synthesize into a short paragraph
    paragraph = " ".join(sentence for _, sentence, _ in selected)

    # If a word limit was requested, trim to that many words
    if word_limit is not None:
        words = re.findall(r"\S+", paragraph)
        if len(words) > word_limit:
            paragraph = " ".join(words[:word_limit]).rstrip(' ,.;:!') + "..."

    # If paragraph is still just citation-like fragments (e.g., starts with '- '), clean it
    paragraph = re.sub(r"\s*-\s*", "", paragraph).strip()

    # final simple length guard
    if len(paragraph) > 1400:
        paragraph = paragraph[:1400].rsplit(".", 1)[0] + "."

    return paragraph


def _requested_word_count(question: str) -> int | None:
    """Parse phrases like 'in 30 words' or 'explain in 20 words' and return the number."""
    match = re.search(r"\b(\d{1,3})\s+words?\b", question.lower())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def generate_local_summary(question: str, context_chunks: list[dict], style: str | None = None) -> str:
    bullet_count = _requested_bullet_count(question) or (3 if style == "brief" else 5)
    candidates = _summary_candidates(context_chunks)
    if not candidates:
        return "I don't have enough information in the document to answer that."

    selected = _dedupe_candidates(candidates)[:bullet_count]
    return _capitalize_line_start(
        "\n".join(f"- {_emphasize_key_terms(candidate)}" for candidate in selected)
    )


def _requested_bullet_count(question: str) -> int | None:
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    numeric_match = re.search(r"\b([1-9]|10)\b", question)
    if numeric_match:
        return int(numeric_match.group(1))

    question_words = set(re.findall(r"[a-z]+", question.lower()))
    for word, value in number_words.items():
        if word in question_words:
            return value
    return None


def _summary_candidates(context_chunks: list[dict]) -> list[str]:
    candidates = []
    for chunk in context_chunks:
        text = _clean_context_text(chunk.get("text", ""))
        if not text:
            continue

        markdown_items = re.findall(r"(?:^|\s)-\s+([^-\n#][^-#]{30,220})", text)
        for item in markdown_items:
            candidates.append(_clean_sentence(item))

        heading_items = re.findall(r"#+\s*([^#]{8,140})", text)
        for heading in heading_items:
            candidates.append(_clean_sentence(heading))

        has_markdown_lines = bool(re.search(r"(?:^|\s)[-*•]\s+", text))
        sentences = (
            [line.strip() for line in text.splitlines() if line.strip()]
            if has_markdown_lines
            else re.split(r"(?<=[.!?])\s+", text)
        )
        for sentence in sentences:
            cleaned = _clean_sentence(sentence)
            if 45 <= len(cleaned) <= 240:
                candidates.append(cleaned)

    return [candidate for candidate in candidates if _looks_useful(candidate)]


def _clean_context_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\*\*|`|_{2,}", "", text)
    return text


def _clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -–—*#:\t")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def _capitalize_line_start(text: str) -> str:
    """Capitalize the first alphabetic character after each response line."""
    return re.sub(
        r"(^[ \t]*[-*•]?[ \t]*|(?<=[.!?])\s+)([a-z])",
        lambda match: f"{match.group(1)}{match.group(2).upper()}",
        text,
        flags=re.MULTILINE,
    )


def _emphasize_key_terms(text: str) -> str:
    """Add restrained Markdown emphasis to salient technical terms in local answers."""
    protected = []

    def protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    text = re.sub(r"\*\*[^*]+\*\*", protect, text)
    text = re.sub(
        r"\b(?:[A-Z]{2,}[A-Z0-9]*(?:[-/][A-Za-z0-9]+)*|[A-Z][A-Za-z]+\d+)\b",
        lambda match: f"**{match.group(0)}**",
        text,
    )
    text = re.sub(r"\b\d+(?:\.\d+)?%", lambda match: f"**{match.group(0)}**", text)

    for index, value in enumerate(protected):
        text = text.replace(f"\x00{index}\x00", value)
    return text


def _looks_useful(text: str) -> bool:
    if len(text.split()) < 5:
        return False
    if re.fullmatch(r"[\W\d_]+", text):
        return False
    broken_prefix = re.match(r"^[a-z]{1,2}\s", text)
    return broken_prefix is None


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    selected = []
    seen = set()
    for candidate in candidates:
        key_terms = tuple(re.findall(r"[a-z0-9]+", candidate.lower())[:10])
        if key_terms in seen:
            continue
        seen.add(key_terms)
        selected.append(candidate)
    return selected


# Post-process model answers to reduce repetition and prefer grounded content.
def _postprocess_answer(
    answer: str,
    context_chunks: list[dict],
    question: str,
    style: str | None = None,
) -> str:
    """Clean and optionally fallback to the local evidence-based answer when the model
    answer appears ungrounded or highly repetitive.

    Heuristics used:
    - Remove exact repeated consecutive sentences.
    - Remove duplicate sentences while preserving order.
    - If overlap between answer terms and context terms is very low, prefer the
      local evidence-based generator (generate_local_answer).
    - Trim extremely long answers.
    """
    bullet_requested = style == "bullets" or bool(
        re.search(r"\b(bullet|bullets|list|points)\b", question, re.I)
    )
    bullet_lines = _extract_bullet_lines(answer) if bullet_requested else []
    bullet_format = bullet_requested and len(bullet_lines) >= 1
    if bullet_format:
        deduped_bullets = list(dict.fromkeys(line for line in bullet_lines if line))
        text = "\n".join(f"- {line}" for line in deduped_bullets)
    else:
        # normalize whitespace
        text = re.sub(r"\s+", " ", answer).strip()

    # split into sentences (simple heuristic)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned_sentences = []
    seen = set()
    prev = None
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        # skip exact consecutive duplicate
        if prev and s_clean == prev:
            continue
        prev = s_clean
        # dedupe across the whole answer by first 40 characters of normalized terms
        key = tuple(re.findall(r"[a-z0-9]+", s_clean.lower())[:12])
        if key in seen:
            continue
        seen.add(key)
        cleaned_sentences.append(s_clean)

    processed = " ".join(cleaned_sentences).strip()

    # quick grounding check: count overlap between answer terms and context terms
    answer_terms = set(re.findall(r"[a-z0-9]+", processed.lower()))
    context_terms = set()
    for chunk in context_chunks:
        context_terms.update(re.findall(r"[a-z0-9]+", chunk.get("text", "").lower()))

    overlap = len(answer_terms & context_terms)
    answer_term_count = max(1, len(answer_terms))
    overlap_ratio = overlap / answer_term_count

    # If overlap is very small, prefer the local evidence-based answer to avoid hallucination.
    # Thresholds chosen conservatively: require at least 3 overlapping terms or 12% overlap.
    if overlap < 3 or overlap_ratio < 0.12:
        # Ask local generator for an evidence-based response (it may still produce short evidence list)
        local = generate_local_answer(question, context_chunks)
        # If local answer looks substantive (not the generic fallback), prefer it.
        if local and "I don't have enough information" not in local:
            return local
        # otherwise, keep the processed model answer but prepend a short disclaimer
        processed = (
            "I may not have enough document evidence for a confident answer; here is the model's best attempt: "
            + processed
        )

    # limit answer size to avoid extremely long responses
    if len(processed) > 2000:
        processed = processed[:2000].rsplit(".", 1)[0] + "."

    if bullet_format:
        return _capitalize_line_start(
            "\n".join(f"- {sentence.lstrip('- ').strip()}" for sentence in cleaned_sentences)
        )
    return _capitalize_line_start(processed)


def _extract_bullet_lines(answer: str) -> list[str]:
    """Normalize model bullet output, including several labeled points on one line."""
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    candidates = []
    for line in lines:
        line = re.sub(r"^\s*[-*•]\s+", "", line).strip()
        if not line:
            continue
        # Models sometimes return: "- **A:** ... - **B:** ...". Split only
        # before a new labeled heading, not hyphens inside normal prose.
        parts = re.split(
            r"\s+-\s+(?=(?:\*{0,2})[A-Z][^:\n]{1,60}(?:\*{0,2}):)",
            line,
        )
        candidates.extend(part.strip(" -") for part in parts if part.strip(" -"))
    return candidates
