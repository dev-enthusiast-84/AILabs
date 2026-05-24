"""
Live OpenAI connectivity tests — no mocks, real API calls.

Validates that the configured API key works, embeddings are generated correctly,
and the LLM responds as expected before running heavier agent tests.
"""
import pytest
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


@pytest.mark.timeout(60)
def test_openai_api_key_accepted(openai_api_key, stage_gate):
    """Verify the key is accepted by OpenAI and the account has model access."""
    stage_gate(
        "OpenAI Connectivity",
        "Lists available models via the OpenAI API to verify the key works.",
    )
    import openai
    client = openai.OpenAI(api_key=openai_api_key)
    models = client.models.list()
    ids = [m.id for m in models.data]
    assert any(m.startswith("gpt") for m in ids), (
        f"No GPT models visible — check API key permissions. Got: {ids[:5]}"
    )


@pytest.mark.timeout(60)
def test_embedding_generation(openai_api_key, stage_gate):
    """Generate a real embedding vector and verify its shape."""
    stage_gate(
        "Embedding Generation",
        "Calls text-embedding-3-small and checks the returned vector is non-empty.",
    )
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=openai_api_key,
    )
    vector = embeddings.embed_query("remote work policy")
    assert len(vector) > 100, f"Embedding too short: {len(vector)} dims"
    assert all(isinstance(v, float) for v in vector[:5]), "Embedding values are not floats"


@pytest.mark.timeout(60)
def test_llm_completion(openai_api_key, stage_gate):
    """Issue a minimal chat completion and verify the model responds."""
    stage_gate(
        "LLM Completion",
        "Sends a single-turn prompt to gpt-4o-mini and checks the response.",
    )
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
        openai_api_key=openai_api_key,
        max_tokens=20,
    )
    response = llm.invoke("Reply with exactly the word PONG and nothing else.")
    content = response.content.strip()
    print(f"\n  LLM replied: {content!r}", flush=True)
    assert "PONG" in content.upper(), f"Unexpected LLM response: {content!r}"


@pytest.mark.timeout(60)
def test_token_callback_tracks_usage(openai_api_key, stage_gate):
    """Confirm that get_usage_metadata_callback captures real token counts."""
    stage_gate(
        "Token Tracking",
        "Wraps an LLM call in get_usage_metadata_callback and asserts tokens > 0.",
    )
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_key=openai_api_key,
        max_tokens=10,
    )
    with get_usage_metadata_callback() as cb:
        llm.invoke("Reply: hello")
    total_tokens = sum(v.get("total_tokens", 0) for v in cb.usage_metadata.values())
    print(f"\n  Tokens tracked: {total_tokens}", flush=True)
    assert total_tokens > 0, "Token callback returned zero — check LangChain version"
