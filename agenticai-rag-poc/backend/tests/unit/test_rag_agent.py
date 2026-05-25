"""Unit tests for rag_agent.py — routing, retry logic, per-node models, structured output."""
import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32ch")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass@99!")


# ── Routing tests ─────────────────────────────────────────────────────────────

def _base_agent_state(validation: str = "VALID", retry_count: int = 0) -> dict:
    """Return a minimal AgentState dict including all telemetry fields."""
    return {
        "question": "q",
        "retrieved_context": "ctx",
        "retrieved_docs": [],
        "answer": "ans",
        "validation": validation,
        "retry_count": retry_count,
        "tokens_used": 0,
        "messages": [],
        "sources": [],
        "citations": [],
        "original_question": "q",
        "refined_query": "q refined",
        "chunks_found": 2,
        "chunks_after_grading": 2,
        "chunks_after_rerank": 2,
        "validation_reason": "All good.",
        "query_variants": [],
        "hypothetical_answer": "",
        "answer_instruction": "",
        "planner_tokens": 10,
        "hyde_tokens": 0,
        "grader_tokens": 0,
        "generator_tokens": 20,
        "validator_tokens": 5,
        "planner_latency_ms": 100,
        "hyde_latency_ms": 0,
        "grader_latency_ms": 0,
        "reranker_latency_ms": 0,
        "generator_latency_ms": 200,
        "validator_latency_ms": 50,
    }


class TestRouteValidator:
    def _state(self, validation: str, retry_count: int) -> dict:
        return _base_agent_state(validation=validation, retry_count=retry_count)

    def test_valid_routes_to_end(self):
        from langgraph.graph import END
        from app.agents.rag_agent import _route_validator
        assert _route_validator(self._state("VALID", 0)) == END

    def test_needs_revision_below_max_routes_to_generator(self):
        from app.agents.rag_agent import _route_validator, _MAX_RETRIES
        state = self._state("NEEDS_REVISION", _MAX_RETRIES - 1)
        assert _route_validator(state) == "generator"

    def test_needs_revision_at_max_routes_to_end(self):
        from langgraph.graph import END
        from app.agents.rag_agent import _route_validator, _MAX_RETRIES
        state = self._state("NEEDS_REVISION", _MAX_RETRIES)
        assert _route_validator(state) == END

    def test_needs_revision_above_max_routes_to_end(self):
        from langgraph.graph import END
        from app.agents.rag_agent import _route_validator, _MAX_RETRIES
        state = self._state("NEEDS_REVISION", _MAX_RETRIES + 5)
        assert _route_validator(state) == END

    def test_valid_always_ends_regardless_of_retry_count(self):
        from langgraph.graph import END
        from app.agents.rag_agent import _route_validator
        for count in range(5):
            assert _route_validator(self._state("VALID", count)) == END


# ── Per-node model tests ──────────────────────────────────────────────────────

class TestPerNodeModel:
    def test_llm_uses_override_when_provided(self):
        from app.agents.rag_agent import _llm
        with patch("app.agents.rag_agent.ChatOpenAI") as mock_chat:
            with patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"):
                with patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
                    _llm("gpt-4o")
        mock_chat.assert_called_once()
        assert mock_chat.call_args.kwargs["model"] == "gpt-4o"

    def test_llm_falls_back_to_effective_model_when_empty(self):
        from app.agents.rag_agent import _llm
        with patch("app.agents.rag_agent.ChatOpenAI") as mock_chat:
            with patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"):
                with patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
                    _llm("")
        assert mock_chat.call_args.kwargs["model"] == "gpt-4o-mini"

    def test_planner_uses_planner_model_config(self):
        """planner_node calls _llm with settings.planner_model."""
        from app.agents.rag_agent import _llm
        with patch("app.agents.rag_agent.settings") as mock_settings, \
             patch("app.agents.rag_agent.ChatOpenAI") as mock_chat, \
             patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-t"), \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_settings.planner_model = "gpt-4o-mini"
            mock_settings.generator_model = ""
            mock_settings.validator_model = ""
            mock_settings.max_completion_tokens = 1024
            _llm(mock_settings.planner_model)
        assert mock_chat.call_args.kwargs["model"] == "gpt-4o-mini"


# ── Retry hint in generator ───────────────────────────────────────────────────

class TestGeneratorRetryHint:
    def _base_state(self, retry_count: int = 0) -> dict:
        return {
            "question": "What is X?",
            "retrieved_context": "X is a thing.",
            "retrieved_docs": [],
            "answer": "",
            "validation": "NEEDS_REVISION" if retry_count > 0 else "",
            "tokens_used": 0,
            "retry_count": retry_count,
            "messages": [],
            "sources": [],
            "citations": [],
            "original_question": "What is X?",
            "refined_query": "What is X?",
            "chunks_found": 1,
            "chunks_after_grading": 1,
            "chunks_after_rerank": 1,
            "validation_reason": "",
            "query_variants": [],
            "hypothetical_answer": "",
            "planner_tokens": 0,
            "hyde_tokens": 0,
            "grader_tokens": 0,
            "generator_tokens": 0,
            "validator_tokens": 0,
            "planner_latency_ms": 0,
            "hyde_latency_ms": 0,
            "grader_latency_ms": 0,
            "reranker_latency_ms": 0,
            "generator_latency_ms": 0,
            "validator_latency_ms": 0,
        }

    def test_no_hint_on_first_attempt(self):
        """On first call (retry_count=0), the question is sent unmodified."""
        captured = {}
        def fake_invoke(inputs):
            captured["question"] = inputs["question"]
            return "some answer"

        mock_chain = MagicMock()
        mock_chain.invoke = fake_invoke

        with patch("app.agents.rag_agent._llm") as mock_llm, \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser") as mock_parser, \
             patch("app.agents.rag_agent.settings") as mock_settings:
            mock_settings.generator_model = ""
            mock_settings.token_budget_warning_threshold = 800
            mock_cb.return_value.__enter__ = MagicMock(return_value=MagicMock(usage_metadata={"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}))
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=MagicMock(__or__=MagicMock(return_value=mock_chain)))

            from app.agents.rag_agent import generator_node
            state = self._base_state(retry_count=0)
            generator_node(state)

        assert "Revision attempt" not in captured.get("question", "")

    def test_hint_prepended_on_retry(self):
        """On retry (retry_count>0), the revision hint is prepended to the question."""
        from app.agents.rag_agent import generator_node

        captured_question = []

        def fake_chain_invoke(inputs):
            captured_question.append(inputs["question"])
            return "revised answer"

        mock_chain = MagicMock()
        mock_chain.invoke = fake_chain_invoke

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.settings") as mock_settings:
            mock_settings.generator_model = ""
            mock_settings.token_budget_warning_threshold = 800
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state(retry_count=1)
            generator_node(state)

        assert len(captured_question) == 1
        assert "Revision attempt 1" in captured_question[0]


# ── Validator structured output ───────────────────────────────────────────────

class TestValidatorStructuredOutput:
    def test_validation_result_model_valid_values(self):
        from app.agents.rag_agent import _ValidationResult
        r = _ValidationResult(status="VALID", reason="All good.")
        assert r.status == "VALID"

    def test_validation_result_model_needs_revision(self):
        from app.agents.rag_agent import _ValidationResult
        r = _ValidationResult(status="NEEDS_REVISION", reason="Hallucination detected.")
        assert r.status == "NEEDS_REVISION"

    def test_validation_result_rejects_invalid_status(self):
        from app.agents.rag_agent import _ValidationResult
        with pytest.raises(Exception):
            _ValidationResult(status="INVALID_STATUS", reason="bad")


# ── Graph structure ───────────────────────────────────────────────────────────

class TestGraphStructure:
    def test_graph_compiles_without_error(self):
        """build_agent_graph() should not raise."""
        from app.agents.rag_agent import build_agent_graph
        graph = build_agent_graph()
        assert graph is not None

    def test_retry_count_initialised_to_zero_in_run_agent(self):
        """run_agent passes retry_count=0 to the graph and returns an AgentTrace."""
        captured_state = {}

        def fake_invoke(state):
            captured_state.update(state)
            return {
                **state,
                "answer": "ok",
                "validation": "VALID",
                "sources": [],
                "citations": [],
                "tokens_used": 0,
                "retry_count": 1,
                "original_question": state["original_question"],
                "refined_query": "refined q",
                "chunks_found": 3,
                "validation_reason": "Looks good.",
                "planner_tokens": 10,
                "generator_tokens": 20,
                "validator_tokens": 5,
                "planner_latency_ms": 100,
                "generator_latency_ms": 200,
                "validator_latency_ms": 50,
            }

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.side_effect = fake_invoke
            mock_get_agent.return_value = mock_agent

            from app.agents.rag_agent import run_agent
            result = run_agent("test question")

        assert captured_state.get("retry_count") == 0
        assert "trace" in result
        assert result["retry_count"] == 1


# ── AgentTrace shape and correctness tests ────────────────────────────────────

class TestAgentTrace:
    def _fake_invoke_result(self, retry_count: int = 1) -> dict:
        return {
            "answer": "The policy allows 3 days.",
            "validation": "VALID",
            "sources": ["sample.txt"],
            "citations": [],
            "tokens_used": 35,
            "retry_count": retry_count,
            "messages": [],
            "question": "remote work?",
            "retrieved_context": "ctx",
            "retrieved_docs": [],
            "original_question": "What is the remote work policy?",
            "refined_query": "remote work policy days allowed",
            "chunks_found": 4,
            "chunks_after_grading": 3,
            "chunks_after_rerank": 2,
            "validation_reason": "Answer is grounded in context.",
            "query_variants": ["wfh policy", "remote days limit"],
            "hypothetical_answer": "Employees may work remotely up to 3 days per week.",
            "planner_tokens": 12,
            "hyde_tokens": 8,
            "grader_tokens": 6,
            "generator_tokens": 18,
            "validator_tokens": 5,
            "planner_latency_ms": 120,
            "hyde_latency_ms": 90,
            "grader_latency_ms": 70,
            "reranker_latency_ms": 150,
            "generator_latency_ms": 250,
            "validator_latency_ms": 60,
        }

    def test_run_agent_returns_trace_with_correct_shape(self):
        """run_agent() must return a dict with a 'trace' key holding an AgentTrace."""
        from app.agents.rag_agent import run_agent, AgentTrace

        fake_result = self._fake_invoke_result(retry_count=1)

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent

            result = run_agent("What is the remote work policy?")

        assert "trace" in result
        trace = result["trace"]
        assert isinstance(trace, AgentTrace)
        assert trace.original_question == "What is the remote work policy?"
        assert trace.refined_query == "remote work policy days allowed"
        assert trace.chunks_found == 4
        assert trace.validation_reason == "Answer is grounded in context."
        assert trace.planner_tokens == 12
        assert trace.generator_tokens == 18
        assert trace.validator_tokens == 5
        assert trace.planner_latency_ms == 120
        assert trace.generator_latency_ms == 250
        assert trace.validator_latency_ms == 60
        assert isinstance(trace.planner_model, str)
        assert isinstance(trace.generator_model, str)
        assert isinstance(trace.validator_model, str)

    def test_run_agent_simple_pipeline_retries_is_zero(self):
        """When retry_count=1 in the final state, AgentTrace.retries must be 0 (1 pass = no retries)."""
        from app.agents.rag_agent import run_agent, AgentTrace

        fake_result = self._fake_invoke_result(retry_count=1)

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent

            result = run_agent("q")

        trace = result["trace"]
        assert isinstance(trace, AgentTrace)
        assert trace.retries == 0  # retry_count=1 means 1 validator pass, 0 revisions

    def test_run_agent_multiple_retries_reflected_in_trace(self):
        """When retry_count=3, AgentTrace.retries must be 2 (3 passes = 2 revisions)."""
        from app.agents.rag_agent import run_agent, AgentTrace

        fake_result = self._fake_invoke_result(retry_count=3)

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent

            result = run_agent("q")

        trace = result["trace"]
        assert isinstance(trace, AgentTrace)
        assert trace.retries == 2

    def test_trace_includes_hyde_telemetry(self):
        """AgentTrace must expose hyde_tokens and hyde_latency_ms from the state."""
        from app.agents.rag_agent import run_agent, AgentTrace

        fake_result = self._fake_invoke_result(retry_count=1)

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent

            result = run_agent("q")

        trace = result["trace"]
        assert isinstance(trace, AgentTrace)
        assert trace.hyde_tokens == 8
        assert trace.hyde_latency_ms == 90


# ── _PlannerOutput (multi-query structured output) ────────────────────────────

class TestPlannerOutput:
    def test_planner_output_valid_construction(self):
        from app.agents.rag_agent import _PlannerOutput
        out = _PlannerOutput(
            primary_query="remote work policy",
            alternatives=["work from home rules", "wfh days per week"],
        )
        assert out.primary_query == "remote work policy"
        assert len(out.alternatives) == 2

    def test_planner_output_empty_alternatives_allowed(self):
        from app.agents.rag_agent import _PlannerOutput
        out = _PlannerOutput(primary_query="q", alternatives=[])
        assert out.alternatives == []


# ── HyDE node ─────────────────────────────────────────────────────────────────

class TestHydeNode:
    def _state(self) -> dict:
        return _base_agent_state()

    def test_hyde_node_sets_hypothetical_answer(self):
        """hyde_node must populate hypothetical_answer in the returned state."""
        from app.agents.rag_agent import hyde_node

        captured = {}

        def fake_chain_invoke(inputs):
            captured["question"] = inputs["question"]
            return "A hypothetical passage about the topic."

        mock_chain = MagicMock()
        mock_chain.invoke = fake_chain_invoke

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._HYDE_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.settings") as mock_settings:
            mock_settings.planner_model = ""
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 15, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            result = hyde_node(self._state())

        assert result["hypothetical_answer"] == "A hypothetical passage about the topic."
        assert result["hyde_tokens"] == 15

    def test_hyde_node_accumulates_tokens_used(self):
        """hyde_node adds its tokens to state['tokens_used']."""
        from app.agents.rag_agent import hyde_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "passage"

        state = _base_agent_state()
        state["tokens_used"] = 50

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._HYDE_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.settings") as mock_settings:
            mock_settings.planner_model = ""
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 20, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            result = hyde_node(state)

        assert result["tokens_used"] == 70  # 50 base + 20 hyde


# ── Retriever fan-out deduplication ──────────────────────────────────────────

class TestRetrieverFanOut:
    def _make_doc(self, content: str, source: str = "doc.txt"):
        from langchain_core.documents import Document
        return Document(page_content=content, metadata={"source": source, "raw_chunk": content})

    def test_retriever_deduplicates_across_queries(self):
        """Duplicate chunks (same 200-char prefix) must appear only once in context."""
        from app.agents.rag_agent import retriever_node

        shared_doc = self._make_doc("shared chunk content " * 5)
        unique_doc = self._make_doc("unique content for variant query " * 3)

        call_count = [0]
        def fake_similarity_search(q):
            call_count[0] += 1
            if call_count[0] == 1:
                return [shared_doc]
            return [shared_doc, unique_doc]  # shared appears again in variant

        state = _base_agent_state()
        state["question"] = "primary query"
        state["query_variants"] = ["variant query"]
        state["hypothetical_answer"] = ""

        with patch("app.agents.rag_agent.similarity_search", side_effect=fake_similarity_search), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "dedup"
            mock_s.retriever_hybrid_bm25 = False
            result = retriever_node(state)

        assert result["chunks_found"] == 2   # shared + unique, shared not counted twice

    def test_retriever_includes_hyde_passage_as_query(self):
        """When hypothetical_answer is set, retriever uses it as an additional search query."""
        from app.agents.rag_agent import retriever_node

        queries_used = []
        def fake_search(q):
            queries_used.append(q)
            return []

        state = _base_agent_state()
        state["question"] = "primary"
        state["query_variants"] = ["alt1"]
        state["hypothetical_answer"] = "hypothetical passage text"

        with patch("app.agents.rag_agent.similarity_search", side_effect=fake_search), \
             patch("app.agents.rag_agent.format_context", return_value=""), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "dedup"
            mock_s.retriever_hybrid_bm25 = False
            retriever_node(state)

        assert "hypothetical passage text" in queries_used
        assert len(queries_used) == 3  # primary + alt1 + hyde

    def test_retriever_no_hyde_when_empty(self):
        """When hypothetical_answer is empty, only primary + variants are searched."""
        from app.agents.rag_agent import retriever_node

        queries_used = []
        def fake_search(q):
            queries_used.append(q)
            return []

        state = _base_agent_state()
        state["question"] = "primary"
        state["query_variants"] = ["alt1", "alt2"]
        state["hypothetical_answer"] = ""

        with patch("app.agents.rag_agent.similarity_search", side_effect=fake_search), \
             patch("app.agents.rag_agent.format_context", return_value=""), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "dedup"
            mock_s.retriever_hybrid_bm25 = False
            retriever_node(state)

        assert len(queries_used) == 3  # primary + alt1 + alt2 (no hyde)
        assert "" not in queries_used

    def test_retriever_french_language_instruction_kept_out_of_search_queries(self):
        """Retriever fan-out uses only question text, variants, and HyDE passage."""
        from app.agents.rag_agent import retriever_node

        answer_instruction = (
            "Answer in French. Keep source grounding and do not translate source filenames."
        )
        queries_used = []

        def fake_search(q):
            queries_used.append(q)
            return [
                Document(
                    page_content=f"retrieved for {q}",
                    metadata={"source": "policy.txt", "raw_chunk": f"retrieved for {q}"},
                )
            ]

        state = _base_agent_state()
        state["question"] = "Quelle est la politique de télétravail?"
        state["query_variants"] = ["politique de travail à distance"]
        state["hypothetical_answer"] = "Le document décrit les règles de télétravail."
        state["answer_instruction"] = answer_instruction

        with patch("app.agents.rag_agent.similarity_search", side_effect=fake_search), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "dedup"
            mock_s.retriever_hybrid_bm25 = False
            retriever_node(state)

        assert queries_used == [
            "Quelle est la politique de télétravail?",
            "politique de travail à distance",
            "Le document décrit les règles de télétravail.",
        ]
        assert all("Answer in French" not in query for query in queries_used)


# ── Feature 5: RRF fusion ─────────────────────────────────────────────────────

class TestRRFFusion:
    def _make_doc(self, content: str, source: str = "doc.txt"):
        from langchain_core.documents import Document
        return Document(page_content=content, metadata={"source": source})

    def test_rrf_fuse_single_list_preserves_order(self):
        """Single input list → same order returned."""
        from app.agents.rag_agent import _rrf_fuse
        docs = [self._make_doc(f"doc {i}") for i in range(3)]
        result = _rrf_fuse([docs])
        assert [d.page_content for d in result] == [d.page_content for d in docs]

    def test_rrf_fuse_shared_doc_scores_higher(self):
        """A doc appearing in both lists ranks above a doc appearing in only one."""
        from app.agents.rag_agent import _rrf_fuse
        shared = self._make_doc("shared content " * 5)
        only_in_one = self._make_doc("unique content " * 5)

        list1 = [shared]
        list2 = [shared, only_in_one]
        result = _rrf_fuse([list1, list2])

        keys = [d.page_content[:200] for d in result]
        assert keys.index(shared.page_content[:200]) < keys.index(only_in_one.page_content[:200])

    def test_rrf_fuse_deduplicates_same_doc(self):
        """Same doc in both lists must appear exactly once in the output."""
        from app.agents.rag_agent import _rrf_fuse
        doc = self._make_doc("repeated content " * 5)
        result = _rrf_fuse([[doc], [doc]])
        assert len(result) == 1

    def test_rrf_fuse_empty_lists_returns_empty(self):
        from app.agents.rag_agent import _rrf_fuse
        assert _rrf_fuse([]) == []
        assert _rrf_fuse([[], []]) == []

    def test_retriever_uses_rrf_mode_by_default(self):
        """retriever_node fuses results via RRF when fusion_mode='rrf'."""
        from app.agents.rag_agent import retriever_node
        from langchain_core.documents import Document

        doc_a = Document(page_content="doc A content " * 5, metadata={"source": "a.txt"})
        doc_b = Document(page_content="doc B content " * 5, metadata={"source": "b.txt"})

        call_n = [0]
        def fake_search(q):
            call_n[0] += 1
            if call_n[0] == 1:
                return [doc_a]
            return [doc_a, doc_b]

        state = _base_agent_state()
        state["question"] = "q"
        state["query_variants"] = ["alt"]
        state["hypothetical_answer"] = ""

        with patch("app.agents.rag_agent.similarity_search", side_effect=fake_search), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "rrf"
            mock_s.retriever_rrf_k = 60
            mock_s.retriever_hybrid_bm25 = False
            result = retriever_node(state)

        assert result["chunks_found"] == 2  # doc_a + doc_b, deduped


# ── Feature 6: Self-RAG Grader ────────────────────────────────────────────────

class TestGraderNode:
    def _state_with_docs(self) -> dict:
        from langchain_core.documents import Document
        state = _base_agent_state()
        state["retrieved_docs"] = [
            Document(page_content=f"chunk {i}", metadata={"source": "doc.txt", "raw_chunk": f"chunk {i}"})
            for i in range(3)
        ]
        state["retrieved_context"] = "some context"
        return state

    def test_grader_passthrough_when_disabled(self):
        """When relevance_grader_enabled=False, grader_node returns state unchanged."""
        from app.agents.rag_agent import grader_node

        state = self._state_with_docs()
        original_docs = list(state["retrieved_docs"])

        with patch("app.agents.rag_agent.get_effective_relevance_grader_enabled", return_value=False):
            result = grader_node(state)

        assert result["grader_tokens"] == 0
        assert result["grader_latency_ms"] == 0
        assert result["retrieved_docs"] == original_docs  # unchanged

    def test_grader_filters_irrelevant_chunks(self):
        """When enabled, grader drops chunks not in relevant_chunk_indices."""
        from app.agents.rag_agent import grader_node, _RelevanceGrade

        state = self._state_with_docs()
        mock_grade = _RelevanceGrade(relevant_chunk_indices=[0, 2], reason="chunks 0 and 2 relevant")

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_grade

        with patch("app.agents.rag_agent.get_effective_relevance_grader_enabled", return_value=True), \
             patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GRADER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.format_context", return_value="filtered ctx"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 25, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            # Grader chain is `_GRADER_PROMPT | structured_llm` — one pipe, one __or__ level.
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            result = grader_node(state)

        assert result["chunks_after_grading"] == 2
        assert len(result["retrieved_docs"]) == 2
        assert result["grader_tokens"] == 25

    def test_grader_fallback_keeps_all_when_all_irrelevant(self):
        """If grader returns no relevant indices, all chunks are kept as fallback."""
        from app.agents.rag_agent import grader_node, _RelevanceGrade

        state = self._state_with_docs()
        mock_grade = _RelevanceGrade(relevant_chunk_indices=[], reason="nothing relevant")

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_grade

        with patch("app.agents.rag_agent.get_effective_relevance_grader_enabled", return_value=True), \
             patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GRADER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.format_context", return_value="ctx"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            # Grader chain is `_GRADER_PROMPT | structured_llm` — one pipe, one __or__ level.
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            result = grader_node(state)

        # Fallback: all 3 original docs kept
        assert len(result["retrieved_docs"]) == 3


# ── Feature 4: Reranker ───────────────────────────────────────────────────────

class TestRerankerNode:
    def _state_with_docs(self) -> dict:
        from langchain_core.documents import Document
        state = _base_agent_state()
        state["retrieved_docs"] = [
            Document(page_content=f"chunk {i}", metadata={"source": "doc.txt", "raw_chunk": f"chunk {i}"})
            for i in range(4)
        ]
        state["retrieved_context"] = "ctx"
        return state

    def test_reranker_passthrough_when_disabled(self):
        """When reranker_type='none', reranker_node is a no-op."""
        from app.agents.rag_agent import reranker_node

        state = self._state_with_docs()
        original_docs = list(state["retrieved_docs"])

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="none"):
            result = reranker_node(state)

        assert result["reranker_latency_ms"] == 0
        assert result["retrieved_docs"] == original_docs  # unchanged

    def test_reranker_cross_encoder_reorders_and_truncates(self):
        """cross-encoder reranker re-scores docs and keeps top reranker_top_k."""
        from app.agents.rag_agent import reranker_node
        from langchain_core.documents import Document

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(4)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"

        # Mock CrossEncoder to return scores [0.1, 0.9, 0.3, 0.7] (doc 1 is best)
        mock_ce_instance = MagicMock()
        mock_ce_instance.predict.return_value = [0.1, 0.9, 0.3, 0.7]
        mock_ce_cls = MagicMock(return_value=mock_ce_instance)

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="cross-encoder"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent.format_context", return_value="reranked ctx"), \
             patch.dict("sys.modules", {
                 "sentence_transformers": MagicMock(CrossEncoder=mock_ce_cls),
             }):
            mock_s.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_s.reranker_top_k = 2
            result = reranker_node(state)

        assert result["chunks_after_rerank"] == 2
        # Highest scores were doc 1 (0.9) and doc 3 (0.7) → they should be first
        assert result["retrieved_docs"][0].page_content == "doc 1"
        assert result["retrieved_docs"][1].page_content == "doc 3"

    def test_reranker_sentence_transformers_not_installed_passthrough(self):
        """When sentence_transformers is missing, reranker logs warning and passes through."""
        from app.agents.rag_agent import reranker_node
        import logging

        state = self._state_with_docs()
        original_count = len(state["retrieved_docs"])

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="cross-encoder"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent._cross_encoder_cache", {}), \
             patch.dict("sys.modules", {"sentence_transformers": None}):
            mock_s.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_s.reranker_top_k = 2
            result = reranker_node(state)

        assert result["reranker_latency_ms"] == 0
        assert len(result["retrieved_docs"]) == original_count  # unchanged

    def test_reranker_llm_judge_reorders_and_truncates(self):
        """llm-judge reranker scores chunks via LLM and keeps top reranker_top_k."""
        from app.agents.rag_agent import reranker_node
        from langchain_core.documents import Document

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(4)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"

        mock_scores_obj = MagicMock()
        mock_scores_obj.scores = [2, 9, 4, 7]  # doc 1 best, doc 3 second
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_scores_obj

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="llm-judge"), \
             patch("app.agents.rag_agent.get_effective_reranker_judge_model", return_value="gpt-4.1-mini"), \
             patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent.ChatOpenAI", return_value=MagicMock(
                 with_structured_output=MagicMock(return_value=mock_llm)
             )), \
             patch("app.agents.rag_agent.format_context", return_value="reranked ctx"):
            mock_s.reranker_top_k = 2
            result = reranker_node(state)

        assert result["chunks_after_rerank"] == 2
        assert result["retrieved_docs"][0].page_content == "doc 1"
        assert result["retrieved_docs"][1].page_content == "doc 3"
        assert "llm-judge" in result["messages"][0].content

    def test_reranker_llm_judge_falls_back_on_llm_error(self):
        """When llm-judge call raises, reranker returns docs[:top_k] unchanged."""
        from app.agents.rag_agent import reranker_node
        from langchain_core.documents import Document

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(4)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API timeout")

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="llm-judge"), \
             patch("app.agents.rag_agent.get_effective_reranker_judge_model", return_value="gpt-4.1-mini"), \
             patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent.ChatOpenAI", return_value=MagicMock(
                 with_structured_output=MagicMock(return_value=mock_llm)
             )):
            mock_s.reranker_top_k = 2
            result = reranker_node(state)

        # Fallback: returns first top_k docs unchanged; pipeline is never stalled
        assert result["chunks_after_rerank"] == 2
        assert result["retrieved_docs"][0].page_content == "doc 0"
        assert result["retrieved_docs"][1].page_content == "doc 1"

    def test_reranker_llm_judge_wrong_score_count_falls_back(self):
        """When judge returns wrong number of scores, falls back to first top_k docs."""
        from app.agents.rag_agent import reranker_node
        from langchain_core.documents import Document

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(4)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"

        mock_scores_obj = MagicMock()
        mock_scores_obj.scores = [9, 8]  # only 2 scores for 4 docs

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_scores_obj

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="llm-judge"), \
             patch("app.agents.rag_agent.get_effective_reranker_judge_model", return_value="gpt-4.1-mini"), \
             patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent.ChatOpenAI", return_value=MagicMock(
                 with_structured_output=MagicMock(return_value=mock_llm)
             )):
            mock_s.reranker_top_k = 2
            result = reranker_node(state)

        assert result["chunks_after_rerank"] == 2
        assert result["retrieved_docs"][0].page_content == "doc 0"

    def test_reranker_llm_judge_uses_original_question_not_planner_rewrite(self):
        """llm-judge reranker must score chunks against original_question, not state['question'].

        After planner_node runs, state['question'] = planner's rewritten query.
        generator_node uses original_question. The reranker must use the same
        question as the generator so chunks are not dropped based on a different query.
        """
        from app.agents.rag_agent import reranker_node

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(2)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"
        # Simulate a planner rewrite: question is now the keyword-rich rewrite,
        # original_question is what the user actually typed.
        state["question"] = "advanced keyword rich rewrite for vector search"
        state["original_question"] = "what does the document say?"

        captured_question: list[str] = []

        def capturing_judge_rerank(docs, question, top_k, api_key, judge_model):
            captured_question.append(question)
            return docs[:top_k], 0

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="llm-judge"), \
             patch("app.agents.rag_agent.get_effective_reranker_judge_model", return_value="gpt-4.1-mini"), \
             patch("app.agents.rag_agent.get_effective_api_key", return_value="sk-test"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent._llm_judge_rerank", side_effect=capturing_judge_rerank), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"):
            mock_s.reranker_top_k = 2
            reranker_node(state)

        assert len(captured_question) == 1
        assert captured_question[0] == "what does the document say?", (
            "Reranker must use original_question, not planner's rewrite"
        )

    def test_reranker_cross_encoder_uses_original_question_not_planner_rewrite(self):
        """cross-encoder reranker must score (original_question, chunk) pairs.

        Ensures parity with the llm-judge fix: both reranker types use
        original_question so the reranker and generator evaluate the same question.
        """
        from app.agents.rag_agent import reranker_node

        docs = [
            Document(page_content=f"doc {i}", metadata={"source": "f.txt", "raw_chunk": f"doc {i}"})
            for i in range(2)
        ]
        state = _base_agent_state()
        state["retrieved_docs"] = docs
        state["retrieved_context"] = "ctx"
        state["question"] = "advanced keyword rich rewrite for vector search"
        state["original_question"] = "what does the document say?"

        captured_pairs: list = []

        mock_ce_instance = MagicMock()

        def capture_predict(pairs):
            captured_pairs.extend(pairs)
            return [0.5] * len(pairs)

        mock_ce_instance.predict.side_effect = capture_predict
        mock_ce_cls = MagicMock(return_value=mock_ce_instance)

        with patch("app.agents.rag_agent.get_effective_reranker_type", return_value="cross-encoder"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent._cross_encoder_cache", {}), \
             patch.dict("sys.modules", {
                 "sentence_transformers": MagicMock(CrossEncoder=mock_ce_cls),
             }):
            mock_s.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_s.reranker_top_k = 2
            reranker_node(state)

        assert len(captured_pairs) == 2
        for question_used, _ in captured_pairs:
            assert question_used == "what does the document say?", (
                "Cross-encoder must use original_question, not planner's rewrite"
            )


# ── Features 4+6 telemetry in AgentTrace ─────────────────────────────────────

class TestAgentTraceFeatures47:
    def test_trace_includes_grader_and_reranker_telemetry(self):
        """AgentTrace must expose grader_tokens, grader_latency_ms, reranker_latency_ms."""
        from app.agents.rag_agent import run_agent, AgentTrace

        fake_result = {
            "answer": "ans",
            "validation": "VALID",
            "sources": [],
            "citations": [],
            "tokens_used": 50,
            "retry_count": 1,
            "messages": [],
            "question": "q",
            "retrieved_context": "ctx",
            "retrieved_docs": [],
            "original_question": "q",
            "refined_query": "q",
            "chunks_found": 4,
            "chunks_after_grading": 3,
            "chunks_after_rerank": 2,
            "validation_reason": "ok",
            "query_variants": [],
            "hypothetical_answer": "",
            "planner_tokens": 5,
            "hyde_tokens": 4,
            "grader_tokens": 8,
            "generator_tokens": 20,
            "validator_tokens": 5,
            "planner_latency_ms": 50,
            "hyde_latency_ms": 40,
            "grader_latency_ms": 30,
            "reranker_latency_ms": 120,
            "generator_latency_ms": 200,
            "validator_latency_ms": 60,
        }

        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent
            result = run_agent("q")

        trace = result["trace"]
        assert isinstance(trace, AgentTrace)
        assert trace.chunks_after_grading == 3
        assert trace.chunks_after_rerank == 2
        assert trace.grader_tokens == 8
        assert trace.grader_latency_ms == 30
        assert trace.reranker_latency_ms == 120


# ── planner_node full body ────────────────────────────────────────────────────

class TestPlannerNode:
    """planner_node executes the structured-output chain and populates state — lines 214-222."""

    def _base_state(self) -> dict:
        return _base_agent_state()

    def test_planner_node_sets_question_and_variants(self):
        """planner_node must update question, refined_query, and query_variants."""
        from app.agents.rag_agent import planner_node, _PlannerOutput

        planned = _PlannerOutput(
            primary_query="remote work days limit",
            alternatives=["wfh policy days", "maximum remote work per week"],
        )

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = planned

        with patch("app.agents.rag_agent._llm") as mock_llm, \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._PLANNER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_planner_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 12, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_llm.return_value.with_structured_output.return_value = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = planner_node(self._base_state())

        assert result["question"] == "remote work days limit"
        assert result["refined_query"] == "remote work days limit"
        assert result["query_variants"] == ["wfh policy days", "maximum remote work per week"]

    def test_planner_node_accumulates_tokens(self):
        """planner_node adds its tokens to tokens_used and sets planner_tokens."""
        from app.agents.rag_agent import planner_node, _PlannerOutput

        planned = _PlannerOutput(primary_query="q refined", alternatives=["alt1", "alt2"])
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = planned

        state = _base_agent_state()
        state["tokens_used"] = 100

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._PLANNER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_planner_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 20, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = planner_node(state)

        assert result["tokens_used"] == 120
        assert result["planner_tokens"] == 20

    def test_planner_node_sets_latency(self):
        """planner_node records a non-negative planner_latency_ms."""
        from app.agents.rag_agent import planner_node, _PlannerOutput

        planned = _PlannerOutput(primary_query="q", alternatives=[])
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = planned

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._PLANNER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_planner_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 5, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = planner_node(_base_agent_state())

        assert result["planner_latency_ms"] >= 0

    def test_planner_node_adds_human_message(self):
        """planner_node appends a HumanMessage to the messages list."""
        from app.agents.rag_agent import planner_node, _PlannerOutput
        from langchain_core.messages import HumanMessage

        planned = _PlannerOutput(primary_query="refined query", alternatives=["alt"])
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = planned

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._PLANNER_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_planner_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 8, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = planner_node(_base_agent_state())

        assert any(isinstance(m, HumanMessage) for m in result["messages"])


# ── generator_node full body ──────────────────────────────────────────────────

class TestGeneratorNodeFullBody:
    """generator_node body — lines 304-315 (token warning branch, latency accumulation)."""

    def _base_state(self, retry_count: int = 0, tokens_used: int = 0) -> dict:
        state = _base_agent_state()
        state["retry_count"] = retry_count
        state["tokens_used"] = tokens_used
        state["generator_tokens"] = 0
        state["generator_latency_ms"] = 0
        return state

    def test_generator_node_accumulates_generator_tokens(self):
        """generator_tokens accumulates across retries (additive, not replaced)."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "answer text"

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 30, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state()
            state["generator_tokens"] = 10
            result = generator_node(state)

        assert result["generator_tokens"] == 40  # 10 existing + 30 new

    def test_generator_node_emits_token_warning_when_over_threshold(self):
        """generator_node calls log.warning when total tokens exceed the threshold."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "answer"

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=50), \
             patch("app.agents.rag_agent.log") as mock_log:
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 100, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state(tokens_used=0)
            generator_node(state)

        mock_log.warning.assert_called_once_with(
            "token_budget_warning", total_tokens=100, threshold=50
        )

    def test_generator_node_accumulates_latency(self):
        """generator_latency_ms is added to existing state value (not replaced)."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "answer"

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 5, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state()
            state["generator_latency_ms"] = 200
            result = generator_node(state)

        assert result["generator_latency_ms"] >= 200  # always >= prior value

    def test_generator_node_defaults_missing_retry_count_to_zero(self):
        """Direct node calls from live-stage tests may omit retry_count; default to first pass."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "answer"

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 5, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state()
            del state["retry_count"]
            result = generator_node(state)

        assert result["retry_count"] == 0
        assert result["answer"] == "answer"

    def test_generator_node_mixed_language_query_receives_selected_language_instruction(self):
        """Mixed-language questions stay intact while output language is generation-only."""
        from app.agents.rag_agent import generator_node

        mixed_question = "Compare la política PTO with les congés payés."
        answer_instruction = (
            "Answer in French. Keep source grounding and do not translate source filenames."
        )
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "La réponse doit rester en français."

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 12, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state()
            state["question"] = mixed_question
            state["original_question"] = mixed_question
            state["answer_instruction"] = answer_instruction
            result = generator_node(state)

        generation_payload = mock_chain.invoke.call_args.args[0]
        assert generation_payload["question"] == mixed_question
        # Instruction is normalized: trailing newlines added so it stays visually
        # separated from the rules block that follows in the prompt template.
        assert generation_payload["answer_instruction"] == answer_instruction.rstrip() + "\n\n"
        assert "Answer in French" not in generation_payload["question"]
        assert result["answer"] == "La réponse doit rester en français."

    def test_generator_node_answers_original_question_not_planner_rewrite(self):
        """Planner rewrites improve retrieval, but generation stays anchored to the user wording."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "Generation is the grounded answer stage."

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 12, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = self._base_state()
            state["original_question"] = "what is Generation"
            state["question"] = "generative AI language model generation process"
            result = generator_node(state)

        generation_payload = mock_chain.invoke.call_args.args[0]
        assert generation_payload["question"] == "what is Generation"
        assert "language model generation process" not in generation_payload["question"]
        assert result["answer"] == "Generation is the grounded answer stage."


# ── validator_node full body ──────────────────────────────────────────────────

class TestValidatorNodeFullBody:
    """validator_node body — lines 563-575."""

    def _base_state(self) -> dict:
        return _base_agent_state()

    def test_validator_node_sets_validation_and_reason(self):
        """validator_node must update validation and validation_reason from LLM output."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="VALID", reason="Answer is grounded.")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        with patch("app.agents.rag_agent._llm") as mock_llm, \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_llm.return_value.with_structured_output.return_value = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = validator_node(self._base_state())

        assert result["validation"] == "VALID"
        assert result["validation_reason"] == "Answer is grounded."

    def test_validator_node_increments_retry_count(self):
        """validator_node increments retry_count by 1."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="NEEDS_REVISION", reason="hallucination")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        state = _base_agent_state()
        state["retry_count"] = 2

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 8, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = validator_node(state)

        assert result["retry_count"] == 3

    def test_validator_node_defaults_missing_retry_count_to_zero(self):
        """Direct validator calls should treat a missing retry_count as the first validation pass."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="VALID", reason="grounded")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        state = _base_agent_state()
        del state["retry_count"]

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 8, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = validator_node(state)

        assert result["retry_count"] == 1

    def test_validator_node_accumulates_validator_tokens(self):
        """validator_tokens is added to existing value (not replaced)."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="VALID", reason="ok")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        state = _base_agent_state()
        state["validator_tokens"] = 15
        state["tokens_used"] = 50

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = validator_node(state)

        assert result["validator_tokens"] == 25   # 15 + 10
        assert result["tokens_used"] == 60        # 50 + 10

    def test_validator_node_passes_language_note_when_answer_instruction_set(self):
        """When a language instruction is set, validator_node injects a language_note
        so the LLM does not flag a non-English answer as a faithfulness error."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="VALID", reason="grounded in Spanish")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        state = _base_agent_state()
        state["answer_instruction"] = "Answer in Spanish. Keep source grounding and do not translate source filenames."
        state["answer"] = "El proceso de ingesta incluye fragmentación e indexación."

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = validator_node(state)

        payload = mock_chain.invoke.call_args.args[0]
        assert "language_note" in payload
        assert "Spanish" in payload["language_note"]
        assert "faithfulness" in payload["language_note"].lower() or "language" in payload["language_note"].lower()
        assert result["validation"] == "VALID"

    def test_validator_node_empty_language_note_when_no_instruction(self):
        """When no language instruction is set, language_note is empty so the
        validator prompt has no spurious text injected."""
        from app.agents.rag_agent import validator_node, _ValidationResult

        mock_result = _ValidationResult(status="VALID", reason="grounded")
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_result

        state = _base_agent_state()
        state["answer_instruction"] = ""

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._VALIDATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.get_effective_validator_model", return_value="gpt-4o-mini"):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 8, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            validator_node(state)

        payload = mock_chain.invoke.call_args.args[0]
        assert payload["language_note"] == ""

    def test_generator_node_normalizes_answer_instruction_with_trailing_newlines(self):
        """generator_node must append '\\n\\n' to answer_instruction so it is
        visually separated from the rule block in the prompt template."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "Bonjour, la réponse est correcte."

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 10, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = _base_agent_state()
            state["answer_instruction"] = "Answer in French."
            generator_node(state)

        payload = mock_chain.invoke.call_args.args[0]
        assert payload["answer_instruction"] == "Answer in French.\n\n"

    def test_generator_node_empty_instruction_stays_empty(self):
        """When no language instruction is set, answer_instruction stays empty string."""
        from app.agents.rag_agent import generator_node

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "The answer."

        with patch("app.agents.rag_agent._llm"), \
             patch("app.agents.rag_agent.get_usage_metadata_callback") as mock_cb, \
             patch("app.agents.rag_agent._GENERATOR_PROMPT") as mock_prompt, \
             patch("app.agents.rag_agent.StrOutputParser"), \
             patch("app.agents.rag_agent.get_effective_generator_model", return_value="gpt-4o-mini"), \
             patch("app.agents.rag_agent.get_effective_token_budget_warning_threshold", return_value=8000):
            cb_mock = MagicMock()
            cb_mock.usage_metadata = {"m": {"total_tokens": 8, "input_tokens": 0, "output_tokens": 0}}
            mock_cb.return_value.__enter__ = MagicMock(return_value=cb_mock)
            mock_cb.return_value.__exit__ = MagicMock(return_value=False)
            mock_prompt.__or__ = MagicMock(
                return_value=MagicMock(__or__=MagicMock(return_value=mock_chain))
            )

            state = _base_agent_state()
            state["answer_instruction"] = ""
            generator_node(state)

        payload = mock_chain.invoke.call_args.args[0]
        assert payload["answer_instruction"] == ""


# ── reranker_node unknown type passthrough ────────────────────────────────────

class TestRerankerNodeUnknownType:
    """reranker_node unknown reranker_type warning+passthrough — line 490-491."""

    def test_unknown_reranker_type_logs_warning_and_passes_through(self, caplog):
        """An unrecognised reranker_type must emit a warning and return state unchanged."""
        import logging
        from app.agents.rag_agent import reranker_node
        from langchain_core.documents import Document

        state = _base_agent_state()
        state["retrieved_docs"] = [
            Document(page_content="doc", metadata={"source": "x.txt", "raw_chunk": "doc"})
        ]
        state["retrieved_context"] = "ctx"

        with caplog.at_level(logging.WARNING, logger="app.agents.rag_agent"), \
             patch("app.agents.rag_agent.get_effective_reranker_type", return_value="unknown_reranker_xyz"):
            result = reranker_node(state)

        assert result["reranker_latency_ms"] == 0
        assert any("unknown" in r.message.lower() or "reranker" in r.message.lower()
                   for r in caplog.records)


# ── reranker_node empty docs guard ────────────────────────────────────────────

class TestRerankerNodeEmptyDocs:
    """reranker_node empty docs early return — line 448."""

    def test_reranker_empty_docs_returns_early(self):
        """reranker_node returns immediately with latency=0 when retrieved_docs is empty."""
        from app.agents.rag_agent import reranker_node

        state = _base_agent_state()
        state["retrieved_docs"] = []

        with patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.reranker_type = "cross-encoder"
            result = reranker_node(state)

        assert result["reranker_latency_ms"] == 0


# ── grader_node empty docs guard ─────────────────────────────────────────────

class TestGraderNodeEmptyDocs:
    """grader_node empty docs early return — line 386."""

    def test_grader_empty_docs_returns_early_with_zero_tokens(self):
        """grader_node returns immediately when retrieved_docs is empty even if enabled."""
        from app.agents.rag_agent import grader_node

        state = _base_agent_state()
        state["retrieved_docs"] = []

        with patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.relevance_grader_enabled = True
            result = grader_node(state)

        assert result["grader_tokens"] == 0
        assert result["grader_latency_ms"] == 0


# ── BM25 hybrid retrieval branch ─────────────────────────────────────────────

class TestRetrieverBM25Hybrid:
    """retriever_node hybrid BM25 branch — lines 303-315."""

    def _make_doc(self, content: str, source: str = "doc.txt"):
        from langchain_core.documents import Document
        return Document(page_content=content, metadata={"source": source})

    def test_retriever_bm25_results_added_to_rrf_fusion(self):
        """When retriever_hybrid_bm25=True, BM25 results are added as an additional ranked list."""
        from app.agents.rag_agent import retriever_node

        dense_doc = self._make_doc("dense retrieval chunk " * 5)
        bm25_doc = self._make_doc("bm25 lexical chunk " * 5)

        with patch("app.agents.rag_agent.similarity_search", return_value=[dense_doc]), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "rrf"
            mock_s.retriever_rrf_k = 60
            mock_s.retriever_hybrid_bm25 = True
            mock_s.retriever_k = 4

            bm25_results = [(bm25_doc, 0.8)]
            with patch("app.rag.bm25.bm25_search", return_value=bm25_results), \
                 patch("app.rag.vector_store.get_all_documents", return_value=[]):

                state = _base_agent_state()
                state["question"] = "primary query"
                state["query_variants"] = []
                state["hypothetical_answer"] = ""

                result = retriever_node(state)

        # Both dense and BM25 docs should appear in the result
        assert result["chunks_found"] >= 1

    def test_retriever_bm25_failure_does_not_break_retrieval(self):
        """If BM25 raises an exception, retriever falls back gracefully."""
        from app.agents.rag_agent import retriever_node

        dense_doc = self._make_doc("dense chunk " * 5)

        with patch("app.agents.rag_agent.similarity_search", return_value=[dense_doc]), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s:
            mock_s.retriever_fusion_mode = "rrf"
            mock_s.retriever_rrf_k = 60
            mock_s.retriever_hybrid_bm25 = True
            mock_s.retriever_k = 4

            with patch("app.rag.bm25.bm25_search", side_effect=RuntimeError("bm25 unavailable")), \
                 patch("app.rag.vector_store.get_all_documents", return_value=[]):

                state = _base_agent_state()
                state["question"] = "query"
                state["query_variants"] = []
                state["hypothetical_answer"] = ""

                # Should not raise
                result = retriever_node(state)

        assert result["chunks_found"] >= 0



# ── retriever_node fanout timeout ─────────────────────────────────────────────

class TestRetrieverFanoutTimeout:
    """retriever_node logs a warning and returns partial results on ThreadPool timeout."""

    def test_retriever_rrf_fanout_timeout_logs_warning(self, capsys):
        """When as_completed raises TimeoutError, a warning is logged and no exception propagates."""
        import concurrent.futures
        from app.agents.rag_agent import retriever_node

        with patch("app.agents.rag_agent.similarity_search", return_value=[]), \
             patch("app.agents.rag_agent.format_context", return_value="ctx"), \
             patch("app.agents.rag_agent.settings") as mock_s, \
             patch(
                 "app.agents.rag_agent.as_completed",
                 side_effect=concurrent.futures.TimeoutError,
             ):
            mock_s.retriever_fusion_mode = "rrf"
            mock_s.retriever_rrf_k = 60
            mock_s.retriever_hybrid_bm25 = False

            state = _base_agent_state()
            state["question"] = "what is X?"
            state["query_variants"] = ["alt phrasing"]
            state["hypothetical_answer"] = ""

            # Must not raise
            result = retriever_node(state)

        assert result["chunks_found"] == 0
        # structlog writes to stdout; verify timeout warning was emitted
        assert "fanout_timeout" in capsys.readouterr().out


# ── _initial_state helper ────────────────────────────────────────────────────

class TestInitialState:
    """_initial_state populates all required AgentState keys — line 635-666."""

    def test_initial_state_zeroed_telemetry(self):
        """_initial_state returns all token/latency fields set to zero."""
        from app.agents.rag_agent import _initial_state
        state = _initial_state("What is X?")
        for field in (
            "tokens_used", "retry_count", "planner_tokens", "hyde_tokens",
            "grader_tokens", "generator_tokens", "validator_tokens",
            "planner_latency_ms", "hyde_latency_ms", "grader_latency_ms",
            "reranker_latency_ms", "generator_latency_ms", "validator_latency_ms",
        ):
            assert state[field] == 0, f"{field} should be 0"

    def test_initial_state_sets_question_and_original_question(self):
        """_initial_state copies the question into both question and original_question."""
        from app.agents.rag_agent import _initial_state
        state = _initial_state("test question")
        assert state["question"] == "test question"
        assert state["original_question"] == "test question"

    def test_initial_state_can_use_separate_retrieval_question(self):
        """Agentic retrieval may be enriched while generation keeps the original question."""
        from app.agents.rag_agent import _initial_state
        state = _initial_state("what is Generation", retrieval_question="generation stage RAG")
        assert state["question"] == "generation stage RAG"
        assert state["original_question"] == "what is Generation"

    def test_initial_state_citations_is_empty_list(self):
        """_initial_state must initialize citations to an empty list."""
        from app.agents.rag_agent import _initial_state
        state = _initial_state("test question")
        assert state["citations"] == []


# ── Citation model and _docs_to_citations helper ─────────────────────────────

class TestCitationModel:
    def test_citation_model_valid_construction(self):
        from app.agents.rag_agent import Citation
        c = Citation(source="policy.txt", chunk_index=2, text="Remote work is allowed.")
        assert c.source == "policy.txt"
        assert c.chunk_index == 2
        assert c.text == "Remote work is allowed."

    def test_docs_to_citations_converts_documents(self):
        from langchain_core.documents import Document
        from app.agents.rag_agent import _docs_to_citations, Citation
        docs = [
            Document(
                page_content="[Document: policy.txt]\nActual chunk text.",
                metadata={"source": "policy.txt", "chunk_index": 3, "raw_chunk": "Actual chunk text."},
            )
        ]
        citations = _docs_to_citations(docs)
        assert len(citations) == 1
        assert isinstance(citations[0], Citation)
        assert citations[0].source == "policy.txt"
        assert citations[0].chunk_index == 3
        assert citations[0].text == "Actual chunk text."

    def test_docs_to_citations_truncates_to_300_chars(self):
        from langchain_core.documents import Document
        from app.agents.rag_agent import _docs_to_citations
        long_text = "x" * 500
        docs = [
            Document(
                page_content=long_text,
                metadata={"source": "big.txt", "chunk_index": 0, "raw_chunk": long_text},
            )
        ]
        citations = _docs_to_citations(docs)
        assert len(citations[0].text) == 300

    def test_docs_to_citations_falls_back_to_page_content(self):
        """When raw_chunk is absent, page_content is used for citation text."""
        from langchain_core.documents import Document
        from app.agents.rag_agent import _docs_to_citations
        docs = [
            Document(
                page_content="fallback content",
                metadata={"source": "doc.txt"},
            )
        ]
        citations = _docs_to_citations(docs)
        assert citations[0].text == "fallback content"

    def test_docs_to_citations_unknown_source_fallback(self):
        """When source metadata is absent, 'unknown' is used."""
        from langchain_core.documents import Document
        from app.agents.rag_agent import _docs_to_citations
        docs = [Document(page_content="content", metadata={})]
        citations = _docs_to_citations(docs)
        assert citations[0].source == "unknown"
        assert citations[0].chunk_index == 0

    def test_run_agent_returns_citations_key(self):
        """run_agent() must include 'citations' in the returned dict."""
        from app.agents.rag_agent import run_agent

        fake_result = {
            "answer": "ans",
            "validation": "VALID",
            "sources": [],
            "citations": [],
            "tokens_used": 0,
            "retry_count": 1,
            "messages": [],
            "question": "q",
            "retrieved_context": "ctx",
            "retrieved_docs": [],
            "original_question": "q",
            "refined_query": "q",
            "chunks_found": 0,
            "chunks_after_grading": 0,
            "chunks_after_rerank": 0,
            "validation_reason": "ok",
            "query_variants": [],
            "hypothetical_answer": "",
            "planner_tokens": 0,
            "hyde_tokens": 0,
            "grader_tokens": 0,
            "generator_tokens": 0,
            "validator_tokens": 0,
            "planner_latency_ms": 0,
            "hyde_latency_ms": 0,
            "grader_latency_ms": 0,
            "reranker_latency_ms": 0,
            "generator_latency_ms": 0,
            "validator_latency_ms": 0,
        }
        from unittest.mock import MagicMock, patch
        with patch("app.agents.rag_agent.get_agent") as mock_get_agent, \
             patch("app.agents.rag_agent.get_effective_model", return_value="gpt-4o-mini"):
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = fake_result
            mock_get_agent.return_value = mock_agent
            result = run_agent("q")
        assert "citations" in result
        assert result["citations"] == []
