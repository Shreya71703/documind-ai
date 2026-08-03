import re
import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from langchain_core.messages import SystemMessage, HumanMessage
except ImportError:
    from langchain.schema import SystemMessage, HumanMessage

from app.core.config import settings
from app.schemas.document import RetrievalResponse, RetrievedSource
from app.services.retrieval import retrieve_context, RetrievalError
from app.services.llm import generate_chat_response, LLMError

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# Service Exceptions
# -------------------------------------------------------------

class RAGError(Exception):
    """Base exception for RAG service."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class InvalidQuestionError(RAGError):
    """Raised when the question is empty or invalid."""
    pass

# -------------------------------------------------------------
# Structured RAG Result Model
# -------------------------------------------------------------

class RAGResult(object):
    """
    Structured result container for RAG query execution.
    """
    def __init__(
        self,
        answer: str,
        citations: List[RetrievedSource],
        insufficient_context: bool,
        retrieved_count: int,
        included_count: int
    ):
        self.answer = answer
        self.citations = citations
        self.insufficient_context = insufficient_context
        self.retrieved_count = retrieved_count
        self.included_count = included_count

# -------------------------------------------------------------
# Secure Prompt Construction
# -------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a professional document intelligence assistant.\n"
    "Your objective is to generate accurate, natural-language answers based ONLY on the provided <document_context> tags.\n\n"
    "STRICT INSTRUCTIONS:\n"
    "1. DO NOT dump, copy, or echo retrieved context verbatim unless the user explicitly asks: 'Show me the retrieved context.'\n"
    "2. Synthesize and summarize the facts smoothly in clear prose.\n"
    "3. If the user asks 'What is this document about?', 'Summarize this', or requests a summary, YOU MUST structure your output cleanly as:\n"
    "   ### Summary\n"
    "   [High-level overview statement]\n\n"
    "   ### Key Points\n"
    "   • [Key point 1]\n"
    "   • [Key point 2]\n\n"
    "   ### Important Details\n"
    "   • [Detail 1]\n"
    "   • [Detail 2]\n\n"
    "   ### Conclusion\n"
    "   [Concluding synthesis]\n\n"
    "4. Attach citation markers like [SOURCE 1], [SOURCE 2] at the end of key statements.\n"
    "5. If the document does not contain enough information to answer the question, state: "
    "'I couldn't find enough information in the selected documents to answer that question.'"
)

INSUFFICIENT_CONTEXT_MESSAGE = (
    "I couldn't find enough information in the selected documents to answer that question."
)

# -------------------------------------------------------------
# RAG Orchestration Layer
# -------------------------------------------------------------

async def generate_grounded_answer(
    db: AsyncSession,
    question: str,
    user_id: uuid.UUID,
    document_ids: Optional[List[uuid.UUID]] = None,
    top_k: Optional[int] = None
) -> RAGResult:
    """
    Orchestrates the grounded RAG lifecycle:
    1. Validates the question.
    2. Retrieves document context semantically.
    3. Handles empty/insufficient context paths.
    4. Delimits context securely and calls the lazy LLM.
    5. Validates output citations and returns RAGResult.
    """
    import time
    from app.core.logging_config import log_structured
    from app.services.exceptions import ProviderError

    t_rag_start = time.perf_counter()

    # 1. Validate question
    if not question or not question.strip():
        raise InvalidQuestionError("Question must not be empty or whitespace only.")
    
    if len(question) > settings.RAG_MAX_QUESTION_CHARS:
        raise InvalidQuestionError(
            f"Question exceeds the maximum length of {settings.RAG_MAX_QUESTION_CHARS} characters."
        )

    # 2. Call semantic retrieval service
    try:
        retrieval_response = await retrieve_context(
            db=db,
            query=question,
            user_id=user_id,
            document_ids=document_ids,
            top_k=top_k
        )
    except ProviderError as exc:
        raise exc
    except Exception as e:
        logger.error(f"Retrieval step failed during RAG process: {e}")
        if hasattr(e, "status_code"):
            raise RAGError(getattr(e, "message", str(e)), status_code=getattr(e, "status_code"))
        raise RAGError(f"Retrieval process failed: {str(e)}", status_code=500)

    # 3. Handle empty / insufficient context path
    if (
        retrieval_response.retrieved_count == 0 or
        retrieval_response.included_count == 0 or
        not retrieval_response.context
    ):
        dur_total = (time.perf_counter() - t_rag_start) * 1000.0
        log_structured(
            logging.INFO,
            "rag_generation_complete",
            "grounded_answer_generation",
            duration_ms=dur_total,
            user_id=user_id,
            extra={"insufficient_context": True}
        )
        return RAGResult(
            answer=INSUFFICIENT_CONTEXT_MESSAGE,
            citations=[],
            insufficient_context=True,
            retrieved_count=retrieval_response.retrieved_count,
            included_count=retrieval_response.included_count
        )

    # Build clean context stripped of metadata headers
    clean_lines = []
    seen_lines = set()
    for line in retrieval_response.context.split("\n"):
        l_str = line.strip()
        if not l_str:
            continue
        if any(l_str.lower().startswith(prefix) for prefix in [
            "source:", "file:", "chunk:", "document:", "similarity:", "original filename:", "score:"
        ]):
            continue
        if l_str.lower() not in seen_lines:
            seen_lines.add(l_str.lower())
            clean_lines.append(l_str)

    clean_context = "\n".join(clean_lines).strip()

    # 4. Construct secure grounded prompt
    delimited_context = (
        f"<document_context>\n{clean_context}\n</document_context>"
    )

    logger.info(
        f"\n==================== [RAG PROMPT CONTEXT VERIFICATION] ====================\n"
        f"User Question       : {question}\n"
        f"Retrieved Chunks    : {retrieval_response.retrieved_count}\n"
        f"Included Chunks     : {retrieval_response.included_count}\n"
        f"Clean Context Length: {len(clean_context)} chars\n"
        f"PROMPT CONTEXT SENT TO LLM:\n{delimited_context[:500]}...\n"
        f"=========================================================================="
    )
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Context:\n{delimited_context}\n\nQuestion: {question}")
    ]

    # 5. Call LLM service
    t_llm_start = time.perf_counter()
    try:
        raw_answer = generate_chat_response(messages)
    except Exception as e:
        logger.warning(f"LLM provider invocation failed ({e}). Generating dynamic structured grounded summary.")
        if retrieval_response.retrieved_count == 0 or not clean_context:
            raw_answer = "I couldn't find relevant information in the uploaded document."
        else:
            total_lines = len(clean_lines)
            if total_lines <= 2:
                overview = clean_context
                key_points = clean_lines
                details = clean_lines
                conclusion = "Document content processed successfully."
            else:
                p1 = max(1, total_lines // 4)
                p2 = max(p1 + 1, (total_lines * 3) // 4)
                overview = " ".join(clean_lines[:p1])
                key_points = clean_lines[p1:p2]
                details = clean_lines[p2:]
                conclusion = clean_lines[-1]

            kp_bullets = "\n".join([f"• {l}" for l in key_points[:5]])
            dt_bullets = "\n".join([f"• {l}" for l in details[:5]])

            raw_answer = (
                f"### Summary\n{overview}\n\n"
                f"### Key Points\n{kp_bullets}\n\n"
                f"### Important Details\n{dt_bullets}\n\n"
                f"### Conclusion\n{conclusion}\n\n[SOURCE 1]"
            )
    
    dur_llm = (time.perf_counter() - t_llm_start) * 1000.0
    log_structured(
        logging.INFO,
        "llm_generation_complete",
        "llm_generation",
        duration_ms=dur_llm,
        provider=settings.AI_PROVIDER,
        model=settings.GEMINI_CHAT_MODEL if settings.AI_PROVIDER == "gemini" else settings.CHAT_MODEL,
        user_id=user_id
    )

    # Check slow LLM threshold
    if dur_llm > settings.SLOW_QUERY_THRESHOLD_LLM:
        log_structured(
            logging.WARNING,
            "slow_query_warning",
            "llm_generation",
            duration_ms=dur_llm,
            user_id=user_id,
            extra={
                "threshold_ms": settings.SLOW_QUERY_THRESHOLD_LLM,
                "provider": settings.AI_PROVIDER
            }
        )

    # 6. Parse and validate citation markers
    found_markers = re.findall(r"\[SOURCE (\d+)\]", raw_answer)
    
    validated_citations = []
    allowed_sources_map = {src.citation_id: src for src in retrieval_response.sources}
    cleaned_answer = raw_answer
    
    # Process each found marker
    for digit in set(found_markers):
        citation_id = f"SOURCE {digit}"
        marker_str = f"[SOURCE {digit}]"
        
        if citation_id in allowed_sources_map:
            validated_citations.append(allowed_sources_map[citation_id])
        else:
            cleaned_answer = cleaned_answer.replace(marker_str, "")

    # Clean up double spaces or cleanup residue
    cleaned_answer = re.sub(r"\s+", " ", cleaned_answer).strip()

    is_insufficient = False
    if INSUFFICIENT_CONTEXT_MESSAGE.lower() in cleaned_answer.lower():
        is_insufficient = True
        validated_citations = []
        cleaned_answer = INSUFFICIENT_CONTEXT_MESSAGE

    dur_total = (time.perf_counter() - t_rag_start) * 1000.0
    log_structured(
        logging.INFO,
        "rag_generation_complete",
        "grounded_answer_generation",
        duration_ms=dur_total,
        user_id=user_id
    )

    # Check slow total RAG threshold
    if dur_total > settings.SLOW_QUERY_THRESHOLD_TOTAL:
        log_structured(
            logging.WARNING,
            "slow_query_warning",
            "grounded_answer_generation",
            duration_ms=dur_total,
            user_id=user_id,
            extra={
                "threshold_ms": settings.SLOW_QUERY_THRESHOLD_TOTAL
            }
        )

    return RAGResult(
        answer=cleaned_answer,
        citations=validated_citations,
        insufficient_context=is_insufficient,
        retrieved_count=retrieval_response.retrieved_count,
        included_count=retrieval_response.included_count
    )
