"""
Generates sample data files for local testing or deployment seeding.

Usage:
    python sample-data/generate_samples.py
    python sample-data/generate_samples.py --topic "Generative AI and Agentic AI"
    python sample-data/generate_samples.py --topic "Healthcare Policy"

Output files (gitignored — not committed):
    sample-data/sample.txt   — Conceptual overview document
    sample-data/sample.csv   — Tabular reference data
    sample-data/sample.xlsx  — Multi-sheet data workbook
    sample-data/sample.pdf   — Structured report (requires: pip install reportlab)

Required for xlsx/pdf:
    pip install openpyxl reportlab
"""

import argparse
import csv
import pathlib

SAMPLE_DIR = pathlib.Path(__file__).parent
DEFAULT_TOPIC = "Generative AI and Agentic AI"


# ── Content banks ─────────────────────────────────────────────────────────────

def _genai_txt() -> str:
    return """\
GENERATIVE AI AND AGENTIC AI — TECHNICAL OVERVIEW
Version 1.0 | Updated: 2025

====================================================
SECTION 1: GENERATIVE AI FUNDAMENTALS
====================================================

1.1 What Is Generative AI?
Generative AI refers to machine learning models capable of producing new content —
text, images, audio, code, and structured data — that was not explicitly in their
training data. Unlike discriminative models that classify inputs, generative models
learn the underlying distribution of data and sample novel outputs from it.

The dominant paradigm as of 2025 is the Large Language Model (LLM): a transformer-
based neural network trained on vast corpora of text via self-supervised next-token
prediction. Notable families include GPT-4o (OpenAI), Claude 3.x (Anthropic),
Gemini 1.5 (Google DeepMind), Llama 3 (Meta), and Mistral (Mistral AI).

1.2 Core Capabilities
- Text generation and summarisation
- Question answering (open-domain and document-grounded)
- Code generation, review, and debugging
- Translation and multilingual reasoning
- Structured output generation (JSON, tables, lists)
- Multimodal understanding (text + images for GPT-4o, Claude 3, Gemini)

1.3 Key Architectural Concepts
Transformer Architecture: Self-attention mechanisms allow the model to relate every
token in the input to every other token, enabling long-range dependency capture.

Context Window: The maximum number of tokens (words + subwords) the model can
process in a single forward pass. As of 2025 this ranges from 8K (compact models)
to 1M+ tokens (Gemini 1.5 Pro).

Temperature & Sampling: Temperature controls output randomness. Low values (0–0.3)
produce deterministic, factual responses; high values (0.8–1.2) favour creativity.
Top-p (nucleus) sampling further constrains token selection to the most probable
cumulative mass p.

====================================================
SECTION 2: RETRIEVAL-AUGMENTED GENERATION (RAG)
====================================================

2.1 The Knowledge Cutoff Problem
LLMs encode world knowledge in their weights at training time. This creates two
limitations: (a) knowledge becomes stale after the training cutoff date, and
(b) private or proprietary knowledge is never in the model at all. RAG addresses
both by injecting retrieved text at inference time.

2.2 RAG Ingestion and Pipeline Stages
The RAG ingestion process is the foundation of a retrieval-augmented system. RAG ingestion
refers specifically to the first stage of the RAG pipeline where raw documents are
processed and stored for later retrieval.

1. RAG Ingestion (Document Processing) — During RAG ingestion, documents are parsed,
   cleaned, and split into overlapping chunks (typically 256–1024 tokens with a 10–20%
   overlap). Each chunk is embedded into a dense vector using a model such as
   text-embedding-3-small (OpenAI) or bge-m3 (BAAI). RAG ingestion supports multiple
   file formats: PDF, TXT, CSV, and Excel. This step is also called the indexing or
   ingestion pipeline.

2. Indexing — After RAG ingestion, chunk vectors are stored in a vector database
   (ChromaDB, Pinecone, Weaviate, Qdrant). The database supports approximate
   nearest-neighbour (ANN) search via algorithms such as HNSW. BM25 keyword indices
   may also be built during this stage for hybrid retrieval.

3. Retrieval — At query time the question is embedded and the top-k most similar
   chunks are fetched via cosine similarity or MMR (Maximal Marginal Relevance)
   to reduce redundancy. Hybrid retrieval combines dense vector search with BM25
   lexical search for improved recall.

4. Generation — Retrieved chunks are concatenated into a prompt context and the
   LLM generates a grounded answer. The model is instructed to cite only information
   present in the context, reducing hallucination.

2.3 Evaluation Metrics
- Faithfulness: Is the answer supported by the retrieved context?
- Answer Relevance: Does the answer address the question?
- Context Precision: Were the retrieved chunks actually useful?
- Context Recall: Were all necessary chunks retrieved?

Tools such as RAGAS and TruLens provide automated evaluation pipelines.

====================================================
SECTION 3: AGENTIC AI
====================================================

3.1 What Is an AI Agent?
An AI agent is an LLM-based system that can plan multi-step tasks, take actions
(via tools or APIs), observe results, and iterate until a goal is achieved.
Agents differ from single-pass LLM calls in that they maintain state across
multiple model invocations and can branch or loop based on intermediate outputs.

3.2 Core Agent Components
- Brain (LLM): Performs reasoning and generates action decisions.
- Memory: Short-term (context window), long-term (vector/key-value store), and
  episodic (interaction history).
- Tools: Python functions, API clients, search engines, databases, code executors
  that the agent can invoke.
- Planning: The ability to decompose a high-level goal into ordered sub-tasks.

3.3 Agent Patterns
ReAct (Reason + Act): The agent alternates between Thought, Action, and Observation
steps in a structured prompt loop, making its reasoning traceable.

Plan-and-Execute: A planner LLM generates a full task list up front; separate
executor agents carry out each step. Enables parallelism.

Multi-Agent Systems: Specialized sub-agents (researcher, coder, critic) coordinate
via a supervisor or message-passing protocol. Frameworks: LangGraph, AutoGen,
CrewAI, OpenAI Swarm.

Self-Reflection: The agent reviews its own output against evaluation criteria and
re-runs steps that fail quality checks (validator node pattern).

3.4 LangGraph Architecture
LangGraph models agent control flow as a directed graph of nodes (LLM calls or
Python functions) and edges (conditional routing). Key primitives:
- StateGraph: Typed state dict shared across all nodes.
- Nodes: Functions that receive and return partial state updates.
- Edges: Static or conditional transitions between nodes.
- Checkpointing: Built-in persistence layer (SQLite, PostgreSQL) for long-running
  or resumable agent sessions.

====================================================
SECTION 4: SAFETY, GUARDRAILS, AND EVALUATION
====================================================

4.1 Prompt Injection
Malicious content in retrieved documents or user messages may attempt to override
system instructions. Mitigations: input sanitisation (bleach, regex), role-separated
prompts, and output validation.

4.2 Hallucination Reduction
- Ground answers strictly in retrieved context (RAG).
- Use low temperature for factual tasks.
- Add a validator node that checks output faithfulness before returning to user.
- Return "I don't know" when context is insufficient.

4.3 Token Budget Control
LLM APIs charge per token. Enforce MAX_COMPLETION_TOKENS to cap spend per response.
Track cumulative tokens with LangChain callbacks and log warnings when a threshold
is exceeded. Implement per-user or per-IP rate limits.

4.4 OWASP LLM Top 10 (2025)
- LLM01 Prompt Injection — sanitise all user inputs before insertion into prompts
- LLM02 Insecure Output Handling — validate and escape LLM output before rendering
- LLM03 Training Data Poisoning — audit fine-tuning data sources
- LLM06 Sensitive Information Disclosure — never include PII in prompts or logs
- LLM09 Overreliance — communicate confidence bounds; do not use LLM as sole source

====================================================
SECTION 5: DEPLOYMENT CONSIDERATIONS
====================================================

5.1 Serverless vs. Persistent Hosting
Serverless (Vercel Functions, AWS Lambda): Fast deploy, pay-per-invocation, no ops.
Limitation: ephemeral in-memory state — vector stores must be rebuilt per instance.
Best for demos and low-traffic scenarios.

Persistent (Docker + Railway, Render, GCP Cloud Run + volume): ChromaDB persisted
across restarts. Supports larger documents (>4 MB) and higher throughput. Required
for production RAG workloads.

5.2 Model Selection Guidance
| Use Case              | Recommended Model      | Reason                         |
|-----------------------|------------------------|--------------------------------|
| Fast Q&A / chat       | gpt-4o-mini            | Low latency, low cost          |
| Complex reasoning     | gpt-4o / claude-opus   | High accuracy on hard tasks    |
| Embeddings            | text-embedding-3-small | 1536-dim, cost-effective       |
| Local / air-gapped    | Llama 3.1 (8B/70B)     | No API dependency              |

====================================================
END OF DOCUMENT
====================================================
"""


def _generic_txt(topic: str) -> str:
    return f"""\
{topic.upper()} — REFERENCE GUIDE
Version 1.0 | Generated for Agentic RAG demo

====================================================
SECTION 1: INTRODUCTION TO {topic.upper()}
====================================================

This document provides a structured overview of key concepts, practices, and
considerations related to {topic}. It is intended as a reference for question-
answering and document retrieval demonstrations.

1.1 Background
{topic} has emerged as a significant area of focus across industries due to its
broad applicability and transformative potential. Practitioners across technical
and business domains engage with {topic} to solve complex problems, improve
efficiency, and unlock new capabilities.

1.2 Core Principles
The foundational principles governing {topic} include:
- Accuracy and reliability in outputs and decisions.
- Transparency about methods, limitations, and assumptions.
- Continuous improvement through feedback and iteration.
- Security and privacy as design requirements, not afterthoughts.
- Scalability to accommodate growing data volumes and user bases.

====================================================
SECTION 2: KEY CONCEPTS AND TERMINOLOGY
====================================================

2.1 Definitions
Understanding {topic} requires familiarity with its core vocabulary. Practitioners
should be fluent in the standard terminology used across teams, vendors, and
published literature to avoid miscommunication and ensure shared understanding.

2.2 Frameworks and Standards
Several internationally recognised frameworks provide guidance on {topic}. These
frameworks are maintained by standards bodies and industry consortia, and are
updated periodically to reflect advances in practice and regulation.

2.3 Common Patterns
Successful practitioners identify and reuse proven patterns. Pattern libraries
reduce implementation time and help organisations avoid known failure modes that
have been documented by the broader community.

====================================================
SECTION 3: IMPLEMENTATION APPROACH
====================================================

3.1 Assessment and Planning
Before implementation, conduct a thorough assessment of current state, target
outcomes, and constraints. Define success metrics early so progress can be
measured objectively throughout the project lifecycle.

3.2 Phased Rollout
A phased approach reduces risk. Begin with a limited pilot covering a well-defined
scope, measure results against the success criteria defined in planning, incorporate
lessons learned, and expand incrementally.

3.3 Governance and Oversight
Establish clear ownership, escalation paths, and review cadences. Regular audits
and retrospectives ensure the implementation remains aligned with organisational
goals and compliant with applicable regulations.

====================================================
SECTION 4: COMMON CHALLENGES AND MITIGATIONS
====================================================

4.1 Data Quality
Poor data quality is the leading cause of project failure. Invest in data profiling,
cleansing, and validation pipelines early. Establish data quality SLAs and monitor
them continuously.

4.2 Change Management
Technology change often succeeds technically but fails organisationally. Allocate
dedicated effort to stakeholder communication, training, and feedback collection.
Celebrate early wins to build momentum and trust.

4.3 Security and Compliance
Identify applicable regulatory requirements at project inception. Embed security
reviews into each phase of delivery. Conduct penetration testing before production
launch and establish an ongoing vulnerability management programme.

====================================================
END OF DOCUMENT
====================================================
"""


def _genai_csv_rows() -> list:
    return [
        ["model", "provider", "release_year", "context_window_k", "modality",
         "mmlu_score", "humaneval_score", "use_case"],
        ["GPT-4o",              "OpenAI",       2024, 128,  "text+vision", 88.7, 90.2, "General-purpose, vision, agents"],
        ["GPT-4o-mini",         "OpenAI",       2024, 128,  "text+vision", 82.0, 87.2, "Cost-efficient chat and Q&A"],
        ["Claude 3.5 Sonnet",   "Anthropic",    2024, 200,  "text+vision", 88.7, 92.0, "Coding, analysis, long-context RAG"],
        ["Claude 3 Opus",       "Anthropic",    2024, 200,  "text+vision", 86.8, 84.9, "Complex reasoning, research"],
        ["Gemini 1.5 Pro",      "Google",       2024, 1000, "text+vision", 85.9, 71.9, "Million-token context, multimodal"],
        ["Gemini 1.5 Flash",    "Google",       2024, 1000, "text+vision", 78.9, 74.3, "Low-latency multimodal tasks"],
        ["Llama 3.1 70B",       "Meta",         2024, 128,  "text",        82.0, 80.5, "Open-source, self-hosted agents"],
        ["Llama 3.1 8B",        "Meta",         2024, 128,  "text",        73.0, 72.6, "Edge/local inference"],
        ["Mistral Large 2",     "Mistral AI",   2024, 128,  "text",        84.0, 92.1, "European compliance, coding"],
        ["Mistral Nemo",        "Mistral AI",   2024, 128,  "text",        68.0, 62.5, "Lightweight open-source"],
        ["Command R+",          "Cohere",       2024, 128,  "text",        75.7, 57.6, "Enterprise RAG, tool use"],
        ["Phi-3 Medium",        "Microsoft",    2024, 128,  "text",        78.0, 70.9, "Small-footprint reasoning"],
        ["Qwen2 72B",           "Alibaba",      2024, 128,  "text",        84.2, 86.0, "Multilingual, coding"],
        ["DeepSeek-V2",         "DeepSeek",     2024, 128,  "text",        78.5, 81.1, "Cost-efficient long-context"],
        ["text-embedding-3-small","OpenAI",     2024, 8,    "embedding",   None, None, "RAG indexing, semantic search"],
        ["text-embedding-3-large","OpenAI",     2024, 8,    "embedding",   None, None, "High-accuracy RAG retrieval"],
        ["bge-m3",              "BAAI",         2024, 8,    "embedding",   None, None, "Multilingual open-source embeddings"],
    ]


def _generic_csv_rows(topic: str) -> list:
    slug = topic.replace(" ", "_").lower()
    return [
        ["id", "category", "name", "description", "relevance_score", "source", "year"],
        [f"{slug}_001", "Concept",     f"{topic} — Core Definition",      f"Foundational definition of {topic}",              9.5, "Industry report", 2024],
        [f"{slug}_002", "Framework",   f"{topic} Framework v1",           f"Widely adopted framework for {topic}",            9.0, "Standards body",  2024],
        [f"{slug}_003", "Case Study",  f"{topic} in Financial Services",  f"Implementation of {topic} in banking",            8.5, "Case study",      2024],
        [f"{slug}_004", "Case Study",  f"{topic} in Healthcare",          f"Clinical application of {topic}",                 8.2, "Case study",      2024],
        [f"{slug}_005", "Regulation",  f"{topic} Compliance Guide",       f"Regulatory requirements affecting {topic}",       8.0, "Regulator",       2024],
        [f"{slug}_006", "Tool",        f"{topic} Assessment Tool",        f"Self-assessment checklist for {topic} maturity",  7.8, "Consultancy",     2024],
        [f"{slug}_007", "Research",    f"{topic} Benchmark Study 2024",   f"Annual benchmarking of {topic} performance",      9.2, "Research firm",   2024],
        [f"{slug}_008", "Best Practice",f"{topic} Security Controls",     f"Security and risk controls for {topic}",          8.7, "NIST / ISO",      2024],
        [f"{slug}_009", "Trend",       f"{topic} Market Forecast",        f"Global market size and growth projections",        7.5, "Analyst firm",    2025],
        [f"{slug}_010", "Glossary",    f"{topic} Key Terms",              f"Standardised terminology reference for {topic}",  7.0, "Industry body",   2024],
    ]


def _genai_excel_data() -> dict:
    adoption = {
        "title": "Enterprise AI Adoption",
        "headers": ["Industry", "GenAI_Adoption_Pct", "Agentic_AI_Pct", "Top_Use_Case", "Avg_ROI_Pct"],
        "rows": [
            ("Financial Services",   72, 38, "Fraud detection, report summarisation", 340),
            ("Healthcare",           58, 22, "Clinical notes, diagnostic support",     280),
            ("Retail & E-commerce",  81, 45, "Personalisation, inventory forecasting", 390),
            ("Manufacturing",        55, 30, "Predictive maintenance, QA inspection",  310),
            ("Legal Services",       48, 18, "Contract review, due diligence",         260),
            ("Education",            43, 12, "Personalised tutoring, grading assist",  195),
            ("Government",           31,  8, "Document processing, citizen Q&A",       170),
            ("Media & Entertainment",76, 40, "Content creation, personalisation",      420),
            ("Technology",           89, 62, "Copilots, automated QA, infra ops",      510),
            ("Consulting",           67, 35, "Research synthesis, proposal generation",300),
        ],
    }
    frameworks = {
        "title": "Agentic AI Frameworks",
        "headers": ["Framework", "Vendor", "Language", "Agent_Pattern", "Graph_Support",
                    "Multi_Agent", "Persistence", "Stars_K", "License"],
        "rows": [
            ("LangGraph",    "LangChain",    "Python",     "StateGraph / DAG",      True,  True,  "SQLite/Postgres", 9,    "MIT"),
            ("LangChain",    "LangChain",    "Python/JS",  "Chain / ReAct",         False, True,  "Memory",          92,   "MIT"),
            ("AutoGen",      "Microsoft",    "Python",     "Multi-agent chat",      False, True,  "SQLite",          32,   "MIT"),
            ("CrewAI",       "CrewAI",       "Python",     "Role-based crew",       False, True,  "None",            22,   "MIT"),
            ("Haystack",     "deepset",      "Python",     "Pipeline / RAG",        False, False, "Various",         17,   "Apache 2.0"),
            ("Semantic Kernel","Microsoft",  "Python/C#",  "Plugin / planner",      False, True,  "Memory",          22,   "MIT"),
            ("DSPy",         "Stanford",     "Python",     "Compiled prompts",      False, False, "None",            18,   "MIT"),
            ("Agno",         "Agno",         "Python",     "ReAct + memory",        False, True,  "SQLite/Redis",    16,   "Apache 2.0"),
            ("OpenAI Swarm", "OpenAI",       "Python",     "Handoff / multi-agent", False, True,  "None",            16,   "MIT"),
        ],
    }
    benchmarks = {
        "title": "RAG Benchmarks",
        "headers": ["Benchmark", "Metric", "Category",  "Best_Score", "Avg_Score", "Description"],
        "rows": [
            ("MMLU",         "Accuracy %", "General Knowledge", 88.7, 72.4, "57-subject multiple-choice exam"),
            ("HumanEval",    "Pass@1 %",   "Coding",            92.0, 75.8, "Python function completion from docstrings"),
            ("MATH",         "Accuracy %", "Mathematics",       76.6, 52.1, "Competition-level math problems"),
            ("RAGAS Faithful","Score 0-1", "RAG Quality",        0.91, 0.73, "LLM output faithfulness to retrieved context"),
            ("RAGAS Relevant","Score 0-1", "RAG Quality",        0.88, 0.70, "Answer relevance to question"),
            ("HotpotQA",     "F1 %",       "Multi-hop QA",      80.4, 61.2, "Multi-document reasoning and retrieval"),
            ("TriviaQA",     "Accuracy %", "Open-domain QA",    85.1, 68.5, "Web and Wikipedia trivia questions"),
            ("MTEB Retrieval","nDCG@10",   "Embeddings",         0.58, 0.43, "Multi-task embedding evaluation, retrieval split"),
        ],
    }
    return {"adoption": adoption, "frameworks": frameworks, "benchmarks": benchmarks}


def _generic_excel_data(topic: str) -> dict:
    overview = {
        "title": "Topic Overview",
        "headers": ["Category", "Sub-Topic", "Maturity", "Priority", "Key_Metric", "Notes"],
        "rows": [
            ("Foundations",   f"{topic} Basics",         "Established",  "High",   "Adoption %",   "Entry point for practitioners"),
            ("Foundations",   f"{topic} Terminology",    "Established",  "Medium", "Clarity score","Standardised definitions"),
            ("Implementation",f"{topic} Planning",       "Established",  "High",   "ROI %",        "Assessment and roadmap"),
            ("Implementation",f"{topic} Tooling",        "Growing",      "High",   "Tool count",   "Vendor and OSS ecosystem"),
            ("Implementation",f"{topic} Integration",    "Growing",      "Medium", "APIs",         "System integration patterns"),
            ("Governance",    f"{topic} Risk Framework",  "Established",  "High",   "Control count","Risk identification and mitigation"),
            ("Governance",    f"{topic} Compliance",     "Mature",       "High",   "Regs covered", "Regulatory mapping"),
            ("Governance",    f"{topic} Audit",          "Established",  "Medium", "Audit pass %", "Third-party validation"),
            ("Innovation",    f"{topic} Emerging Trends","Emerging",     "Low",    "Trend count",  "Forward-looking research"),
            ("Innovation",    f"{topic} R&D Pipeline",   "Emerging",     "Low",    "Patents",      "Active research projects"),
        ],
    }
    metrics = {
        "title": "Key Metrics",
        "headers": ["Metric_Name", "Unit", "Baseline", "Target", "Current", "Status"],
        "rows": [
            ("Adoption Rate",        "%",     20,   80,   55, "On track"),
            ("Implementation Time",  "weeks", 24,   12,   16, "On track"),
            ("Cost Reduction",       "%",      0,   30,   22, "On track"),
            ("Quality Improvement",  "%",      0,   25,   18, "On track"),
            ("Stakeholder Satisfaction","NPS", 20,   70,   58, "On track"),
            ("Compliance Coverage",  "%",     60,  100,   85, "At risk"),
            ("Incident Rate",        "per yr",12,    2,    5, "On track"),
            ("Training Completion",  "%",      0,   95,   72, "At risk"),
        ],
    }
    roadmap = {
        "title": "Implementation Roadmap",
        "headers": ["Phase", "Quarter", "Milestone", "Owner", "Budget_USD", "Status"],
        "rows": [
            ("Phase 1 — Foundation", "Q1 2025", "Assessment complete",      "PMO",         50_000, "Done"),
            ("Phase 1 — Foundation", "Q1 2025", "Team trained",             "L&D",         30_000, "Done"),
            ("Phase 2 — Pilot",      "Q2 2025", "Pilot deployed",           "Engineering", 150_000,"In progress"),
            ("Phase 2 — Pilot",      "Q2 2025", "Pilot evaluation report",  "PMO",         20_000, "Planned"),
            ("Phase 3 — Scale",      "Q3 2025", "Full rollout initiated",   "Engineering", 400_000,"Planned"),
            ("Phase 3 — Scale",      "Q3 2025", "Integration with core systems","Arch",    200_000,"Planned"),
            ("Phase 4 — Optimise",   "Q4 2025", "Continuous improvement",   "Operations",  100_000,"Planned"),
            ("Phase 4 — Optimise",   "Q4 2025", "Annual audit",             "Compliance",   40_000,"Planned"),
        ],
    }
    return {"overview": overview, "metrics": metrics, "roadmap": roadmap}


# ── Generators ────────────────────────────────────────────────────────────────

def generate_txt(topic: str) -> None:
    content = _genai_txt() if topic == DEFAULT_TOPIC else _generic_txt(topic)
    path = SAMPLE_DIR / "sample.txt"
    path.write_text(content, encoding="utf-8")
    print(f"  Created: {path}")


def generate_csv(topic: str) -> None:
    rows = _genai_csv_rows() if topic == DEFAULT_TOPIC else _generic_csv_rows(topic)
    path = SAMPLE_DIR / "sample.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    print(f"  Created: {path}")


def generate_excel(topic: str) -> None:
    from openpyxl import Workbook

    data = _genai_excel_data() if topic == DEFAULT_TOPIC else _generic_excel_data(topic)
    wb = Workbook()
    first = True
    for sheet_key, sheet in data.items():
        ws = wb.active if first else wb.create_sheet()
        ws.title = sheet["title"][:31]
        ws.append(sheet["headers"])
        for row in sheet["rows"]:
            ws.append(list(row))
        first = False

    path = SAMPLE_DIR / "sample.xlsx"
    wb.save(path)
    print(f"  Created: {path}")


def generate_pdf(topic: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    path = SAMPLE_DIR / "sample.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    def h1(text: str) -> Paragraph:
        return Paragraph(text, styles["Heading1"])

    def body(text: str) -> Paragraph:
        return Paragraph(text, styles["BodyText"])

    if topic == DEFAULT_TOPIC:
        story += [
            Paragraph("GENERATIVE AI AND AGENTIC AI — MARKET REPORT 2025", styles["Title"]),
            Spacer(1, 12),
            h1("Executive Summary"),
            body(
                "The Generative AI market reached $67 billion in 2024 and is projected to exceed "
                "$1.3 trillion by 2032 (CAGR ~44%). Enterprise adoption accelerated sharply: 89% of "
                "technology companies and 72% of financial services firms report active GenAI deployments. "
                "Agentic AI — where LLMs autonomously plan and execute multi-step tasks — is the fastest-"
                "growing sub-category, with frameworks such as LangGraph, AutoGen, and CrewAI crossing "
                "millions of monthly downloads in 2024."
            ),
            Spacer(1, 12),
            h1("Key Technology Milestones (2024–2025)"),
        ]
        milestones = [
            ["Milestone",                              "Date",    "Impact"],
            ["GPT-4o multimodal release",              "May 2024",    "High"],
            ["Claude 3.5 Sonnet coding SOTA",          "Jun 2024",    "High"],
            ["Llama 3.1 405B open weights",            "Jul 2024",    "High"],
            ["Gemini 1.5 Pro 1M context GA",           "Apr 2024",    "Medium"],
            ["OpenAI o1 reasoning models",             "Sep 2024",    "High"],
            ["LangGraph v0.2 checkpointing",           "Aug 2024",    "Medium"],
            ["Claude 3.5 Haiku fast inference",        "Nov 2024",    "Medium"],
            ["DeepSeek-V3 open-source release",        "Dec 2024",    "High"],
            ["GPT-4o real-time voice API GA",          "Oct 2024",    "Medium"],
        ]
        t1 = Table(milestones, colWidths=[230, 90, 70])
        t1.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("PADDING",       (0, 0), (-1, -1), 6),
        ]))
        story += [t1, Spacer(1, 12)]

        story += [
            h1("What is RAG (Retrieval-Augmented Generation)?"),
            body(
                "RAG — Retrieval-Augmented Generation — is a technique that grounds LLM responses in "
                "private or up-to-date knowledge by retrieving relevant document chunks at query time. "
                "Instead of relying solely on the LLM's training data, RAG fetches the most relevant "
                "passages from a vector database and injects them as context into the prompt. This "
                "approach reduces hallucination, keeps answers current, and enables the model to cite "
                "sources. RAG is now the standard architecture for enterprise document Q&A systems."
            ),
            Spacer(1, 12),
            h1("RAG Ingestion Pipeline"),
            body(
                "The RAG ingestion pipeline is the process of preparing documents for retrieval. "
                "RAG ingestion consists of four main stages:"
            ),
            Spacer(1, 6),
            body(
                "<b>Stage 1 — RAG Ingestion (Document Processing):</b> During RAG ingestion, raw documents "
                "(PDF, TXT, CSV, Excel) are parsed and split into overlapping chunks of 256–1024 tokens "
                "with a 10–20% overlap to preserve context at chunk boundaries. Each chunk is then "
                "embedded into a dense vector using text-embedding-3-small (OpenAI) or bge-m3 (BAAI). "
                "RAG ingestion supports file formats including PDF, plain text, CSV, and Excel spreadsheets."
            ),
            Spacer(1, 4),
            body(
                "<b>Stage 2 — Indexing:</b> After RAG ingestion, chunk embeddings are stored in a vector "
                "database (ChromaDB, Pinecone, Weaviate, or Qdrant). The database builds an approximate "
                "nearest-neighbour (ANN) index using algorithms such as HNSW. A BM25 keyword index may "
                "also be built at this stage for hybrid retrieval combining lexical and semantic search."
            ),
            Spacer(1, 4),
            body(
                "<b>Stage 3 — Retrieval:</b> At query time, the user's question is embedded and the "
                "top-k most similar chunks are fetched via cosine similarity or MMR (Maximal Marginal "
                "Relevance) to reduce redundancy. Multi-query expansion and HyDE (Hypothetical Document "
                "Embeddings) can further improve recall."
            ),
            Spacer(1, 4),
            body(
                "<b>Stage 4 — Generation:</b> The retrieved chunks are concatenated into a prompt context "
                "and the LLM generates a grounded answer, citing only information present in the context "
                "to reduce hallucination."
            ),
            Spacer(1, 12),
            h1("Agentic AI Framework Landscape"),
            body(
                "Agentic frameworks provide the scaffolding for multi-step, tool-using LLM systems. "
                "LangGraph (by LangChain) models agent logic as a stateful directed graph with built-in "
                "persistence, making it the preferred choice for production RAG pipelines. Microsoft "
                "AutoGen enables multi-agent conversation patterns. CrewAI provides a role-based crew "
                "abstraction suited to task decomposition workflows."
            ),
            Spacer(1, 12),
            h1("RAG Architecture Best Practices"),
            body(
                "Retrieval-Augmented Generation remains the primary approach for grounding LLM responses "
                "in private knowledge. Best-practice RAG pipelines use: (1) recursive character text "
                "splitting with 10–20% chunk overlap; (2) text-embedding-3-small or bge-m3 for embeddings; "
                "(3) ChromaDB or Pinecone for ANN vector search; (4) MMR retrieval to reduce redundancy; "
                "(5) a validator node to check faithfulness before returning answers to users."
            ),
            Spacer(1, 12),
            h1("2025 Deployment Guidance"),
        ]

        guidance = [
            ["Scenario",                 "Recommended Stack",                        "Vector Store"],
            ["Demo / proof-of-concept",  "Vercel serverless + gpt-4o-mini",          "In-memory"],
            ["Production RAG",           "Docker + FastAPI + ChromaDB + gpt-4o",      "ChromaDB (persistent)"],
            ["High-throughput agents",   "Kubernetes + LangGraph + Postgres checkpointing","pgvector"],
            ["Air-gapped / on-prem",     "Docker + Llama 3.1 70B + Ollama",          "ChromaDB (local)"],
            ["Edge / mobile",            "Phi-3 Mini + ONNX runtime",                "SQLite-VSS"],
        ]
        t2 = Table(guidance, colWidths=[140, 200, 110])
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF6FF")]),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("PADDING",       (0, 0), (-1, -1), 6),
        ]))
        story.append(t2)

    else:
        story += [
            Paragraph(f"{topic.upper()} — STRUCTURED OVERVIEW", styles["Title"]),
            Spacer(1, 12),
            h1("Introduction"),
            body(
                f"{topic} represents an important domain of knowledge and practice for modern "
                "organisations. This report provides a structured summary of key concepts, "
                "implementation guidance, governance requirements, and forward-looking trends."
            ),
            Spacer(1, 12),
            h1("Core Principles"),
            body(
                f"Effective engagement with {topic} requires adherence to a set of core principles: "
                "accuracy in information and claims, transparency in methods and limitations, "
                "continuous improvement through measurement and feedback, security and privacy "
                "as non-negotiable design constraints, and scalability to support organisational growth."
            ),
            Spacer(1, 12),
            h1("Implementation Phases"),
        ]
        phases = [
            ["Phase",          "Focus Area",       "Duration",  "Key Deliverable"],
            ["1 — Foundation", "Assessment",        "4 weeks",   "Current state report"],
            ["2 — Pilot",      "Limited rollout",   "8 weeks",   "Pilot evaluation report"],
            ["3 — Scale",      "Full deployment",   "12 weeks",  "Production system"],
            ["4 — Optimise",   "Measurement & tuning","Ongoing", "Continuous improvement log"],
        ]
        t1 = Table(phases, colWidths=[120, 120, 80, 150])
        t1.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("PADDING",       (0, 0), (-1, -1), 6),
        ]))
        story += [t1, Spacer(1, 12)]

        story += [
            h1("Governance and Risk"),
            body(
                f"A robust governance framework for {topic} defines roles and responsibilities, "
                "establishes risk thresholds, mandates regular audits, and ensures compliance with "
                "applicable regulations. Risk registers should be reviewed at least quarterly and "
                "updated whenever material changes occur in the operating environment."
            ),
            Spacer(1, 12),
            h1("Key Success Factors"),
            body(
                "Projects succeed when executive sponsorship is sustained, success metrics are agreed "
                "before implementation begins, cross-functional teams collaborate throughout, and "
                "lessons learned are documented and acted upon after each phase."
            ),
        ]

    doc.build(story)
    print(f"  Created: {path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sample documents for the Agentic RAG demo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help=f"Topic for the generated documents (default: '{DEFAULT_TOPIC}')",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF generation (avoids needing reportlab installed)",
    )
    parser.add_argument(
        "--no-xlsx",
        action="store_true",
        help="Skip XLSX generation (avoids needing openpyxl installed)",
    )
    args = parser.parse_args()

    topic = args.topic.strip() or DEFAULT_TOPIC
    print(f"\nGenerating sample documents — topic: \"{topic}\"")
    print()

    generate_txt(topic)
    generate_csv(topic)

    if not args.no_xlsx:
        try:
            generate_excel(topic)
        except ImportError:
            print("  Skipped XLSX (openpyxl not installed — run: pip install openpyxl)")

    if not args.no_pdf:
        try:
            generate_pdf(topic)
        except ImportError:
            print("  Skipped PDF (reportlab not installed — run: pip install reportlab)")

    print(f"\nAll sample files written to {SAMPLE_DIR}/")
    print("(These files are gitignored and must be regenerated after a fresh clone.)")


if __name__ == "__main__":
    main()
