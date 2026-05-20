"""
Live ChromaDB integration tests — real embeddings, ephemeral in-memory collection.

Uses an isolated collection (deleted after the module) so no production data is
touched. Depends on test_live_openai passing (embeddings must work).
"""
import pytest
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

_SEED_DOCS = [
    Document(
        page_content=(
            "Acme Corp remote work policy: employees may work from home up to "
            "3 days per week with manager approval."
        ),
        metadata={"source": "remote_work_policy.txt"},
    ),
    Document(
        page_content=(
            "Annual leave entitlement is 20 days per year for full-time employees. "
            "Requests must be submitted at least 2 weeks in advance."
        ),
        metadata={"source": "hr_handbook.txt"},
    ),
    Document(
        page_content=(
            "Expense claims must be submitted within 30 days of the purchase date "
            "using the online expense portal."
        ),
        metadata={"source": "finance_policy.txt"},
    ),
]


@pytest.fixture(scope="module")
def live_store(openai_api_key):
    """Ephemeral in-memory Chroma collection, deleted after all module tests."""
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=openai_api_key,
    )
    store = Chroma(
        collection_name="live_chroma_test",
        embedding_function=embeddings,
    )
    yield store
    store.delete_collection()


@pytest.mark.timeout(90)
def test_add_documents(live_store, stage_gate):
    """Add seed documents to the ephemeral store and verify IDs are returned."""
    stage_gate(
        "ChromaDB: Add Documents",
        f"Embeds and indexes {len(_SEED_DOCS)} documents into an in-memory Chroma store.",
    )
    ids = live_store.add_documents(_SEED_DOCS)
    print(f"\n  Indexed IDs: {ids}", flush=True)
    assert len(ids) == len(_SEED_DOCS), f"Expected {len(_SEED_DOCS)} IDs, got {len(ids)}"


@pytest.mark.timeout(90)
def test_similarity_search_returns_relevant_chunk(live_store, stage_gate):
    """Semantic search should surface the remote-work document for a matching query."""
    stage_gate(
        "ChromaDB: Similarity Search",
        "Queries 'remote work' and expects the policy document in the top results.",
    )
    results = live_store.similarity_search("remote work from home", k=2)
    print(f"\n  Top results: {[r.metadata.get('source') for r in results]}", flush=True)
    assert len(results) >= 1
    texts = " ".join(r.page_content.lower() for r in results)
    assert "remote" in texts or "home" in texts, (
        "Expected remote-work content in results, got: "
        + "; ".join(r.page_content[:60] for r in results)
    )


@pytest.mark.timeout(90)
def test_similarity_search_metadata_filtering(live_store, stage_gate):
    """Expense-related query should return the finance policy document."""
    stage_gate(
        "ChromaDB: Metadata Check",
        "Queries 'expense claims' and verifies the finance_policy source is returned.",
    )
    results = live_store.similarity_search("expense claims portal", k=1)
    sources = [r.metadata.get("source") for r in results]
    print(f"\n  Sources returned: {sources}", flush=True)
    assert "finance_policy.txt" in sources, (
        f"finance_policy.txt not in top result. Got: {sources}"
    )


@pytest.mark.timeout(90)
def test_collection_count_after_add(live_store, stage_gate):
    """Collection should contain exactly the number of seeded documents."""
    stage_gate(
        "ChromaDB: Collection Count",
        "Reads the raw collection and verifies document count matches seed data.",
    )
    data = live_store._collection.get(include=["metadatas"])
    count = len(data.get("metadatas") or [])
    print(f"\n  Documents in collection: {count}", flush=True)
    assert count == len(_SEED_DOCS), f"Expected {len(_SEED_DOCS)}, found {count}"


@pytest.mark.timeout(90)
def test_delete_document_by_source(live_store, stage_gate):
    """Delete a document by source metadata filter and confirm it is removed."""
    stage_gate(
        "ChromaDB: Delete Document",
        "Deletes 'finance_policy.txt' by metadata filter and re-queries to confirm removal.",
    )
    collection = live_store._collection
    results = collection.get(where={"source": "finance_policy.txt"}, include=["metadatas"])
    ids = results.get("ids") or []
    assert ids, "finance_policy.txt not found before delete"
    collection.delete(ids=ids)

    after = collection.get(where={"source": "finance_policy.txt"}, include=["metadatas"])
    remaining = after.get("ids") or []
    print(f"\n  Remaining IDs for finance_policy.txt: {remaining}", flush=True)
    assert not remaining, f"Document not deleted — IDs still present: {remaining}"
