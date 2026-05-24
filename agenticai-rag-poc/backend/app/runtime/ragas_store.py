"""
Persistent store for Ragas evaluation scores.

Scores are written by the live Ragas test suite and read by the admin
settings dashboard via GET /api/settings/ragas-scores.

File path controlled by RAGAS_SCORES_FILE env var; defaults to /tmp/ragas_scores.json.

OWASP A01 — endpoint is admin-only (enforced in api/settings.py).
OWASP A05 — RAGAS_SCORES_FILE is validated against an allowlist of base directories
             to prevent path traversal if the env var is attacker-controlled.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


def _allowed_bases() -> tuple[Path, ...]:
    """Compute the set of allowed directory roots at call time.

    Includes /tmp (Linux default), the real temp dir for this OS user
    (macOS uses /var/folders/…/T), and the process working directory
    so tests using pytest's tmp_path are also accepted.
    """
    return tuple({
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
        Path.cwd().resolve(),
    })


def _validate_scores_path(raw: str) -> Path:
    """Resolve the path and confirm it sits inside an allowed directory.

    Raises ValueError on traversal attempts (e.g. /tmp/../etc/passwd).
    """
    path = Path(raw)
    resolved = path.resolve()
    if not any(resolved.is_relative_to(base) for base in _allowed_bases()):
        raise ValueError(
            f"RAGAS_SCORES_FILE '{raw}' resolves to '{resolved}' which is outside "
            f"allowed directories: {[str(b) for b in _allowed_bases()]}"
        )
    return path


class RagasScores(TypedDict):
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float
    evaluated_at: str   # ISO-8601
    model: str
    num_samples: int


def _scores_path() -> Path:
    """Return the validated path for the Ragas scores file."""
    return _validate_scores_path(os.getenv("RAGAS_SCORES_FILE", "/tmp/ragas_scores.json"))


def get_ragas_scores() -> RagasScores | None:
    """Return the last saved Ragas scores, or None if no run has been saved."""
    path = _scores_path()
    if not path.exists():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
        required = {"faithfulness", "answer_relevancy", "context_precision", "context_recall"}
        if not required.issubset(data.keys()):
            return None
        return RagasScores(
            faithfulness=float(data["faithfulness"]),
            answer_relevancy=float(data["answer_relevancy"]),
            context_precision=float(data["context_precision"]),
            context_recall=float(data["context_recall"]),
            evaluated_at=str(data.get("evaluated_at", "")),
            model=str(data.get("model", "")),
            num_samples=int(data.get("num_samples", 0)),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_ragas_scores(
    faithfulness: float,
    answer_relevancy: float,
    context_precision: float,
    context_recall: float,
    model: str,
    num_samples: int,
) -> None:
    """Persist Ragas evaluation scores to disk."""
    scores: RagasScores = {
        "faithfulness": round(faithfulness, 4),
        "answer_relevancy": round(answer_relevancy, 4),
        "context_precision": round(context_precision, 4),
        "context_recall": round(context_recall, 4),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "num_samples": num_samples,
    }
    path = _scores_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(scores, f, indent=2)
