"""
RAG pipeline helpers.

- ``format_context``: pure helper; formats a list of LangChain Documents into a
  numbered, source-annotated context string.
- ``run_simple_rag``: single retrieve → generate pass with no validator stage.
  Returns the same dict shape as ``run_agent()`` but with ``validation="N/A"``
  and ``mode="simple"`` so the endpoint can pass it through to ``QueryResponse``
  without branching.

OWASP notes (A03 / A01): ``run_simple_rag`` does not call the LLM with
unvalidated user input — the caller (``query_documents``) must apply
``sanitize_query`` and the guardrail engine *before* calling this function.
"""
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.rag.vector_store import similarity_search
from app.runtime.settings_store import get_effective_max_context_chunks

settings = get_settings()

_SIMPLE_RAG_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Answer the question using only the provided context. "
        "If the context does not contain the answer, say so clearly.\n"
        "{answer_instruction}",
    ),
    ("human", "Context:\n{context}\n\nQuestion: {question}"),
])


def format_context(docs: list[Document]) -> str:
    limited = docs[: get_effective_max_context_chunks()]
    parts = []
    for i, doc in enumerate(limited, 1):
        source = doc.metadata.get("source", "unknown")
        content = doc.metadata.get("raw_chunk", doc.page_content)
        parts.append(f"[Source {i}: {source}]\n{content}")
    return "\n\n---\n\n".join(parts)


def run_simple_rag(
    question: str,
    answer_instruction: str = "",
    retrieval_question: str | None = None,
) -> dict:
    """
    Execute a single retrieve → generate pass (no validator stage).

    Performance note: shares the ``_llm()`` factory from ``rag_agent`` to
    ensure consistent model/key resolution; avoids a second settings read.

    Returns a dict compatible with ``QueryResponse``:
      {answer, sources, validation="N/A", mode="simple", tokens_used}
    """
    # Lazy import avoids a circular dependency (rag_agent imports from here).
    from app.agents.rag_agent import _llm  # noqa: PLC0415

    docs = similarity_search(retrieval_question or question)
    if docs:
        context = format_context(docs)
        sources: list[str] = list({doc.metadata.get("source", "unknown") for doc in docs})
    else:
        context = "No relevant documents found in the knowledge base."
        sources = []

    with get_usage_metadata_callback() as cb:
        chain = _SIMPLE_RAG_PROMPT | _llm() | StrOutputParser()
        answer: str = chain.invoke({
            "context": context,
            "question": question,
            "answer_instruction": answer_instruction,
        })

    return {
        "answer": answer,
        "sources": sources,
        "validation": "N/A",
        "mode": "simple",
        "tokens_used": sum(v.get("total_tokens", 0) for v in cb.usage_metadata.values()),
        "retry_count": 0,
        "trace": None,
    }
