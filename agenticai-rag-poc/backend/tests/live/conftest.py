"""
Live dependency test configuration.

Required env : OPENAI_API_KEY  — real key (not sk-test-*)
Optional env : LIVE_SESSION_TIMEOUT  seconds before the entire session is killed (default 300)
               LIVE_STAGE_TIMEOUT    seconds to wait for each user prompt      (default 30)
               LIVE_BACKEND_URL      URL of a running backend                  (default http://localhost:8000)
               LIVE_QUESTION         pre-set question so prompts are skipped   (default: empty)
"""
import os
import sys
import signal
import threading
import warnings

# langgraph 0.2.x calls Reviver() without allowed_objects at import time;
# langchain-core >=0.3.56 warns about this. Suppress until langgraph is upgraded.
warnings.filterwarnings(
    "ignore",
    category=PendingDeprecationWarning,
    module=r"langgraph\..*",
)

import httpx
import pytest

_SESSION_TIMEOUT: int = int(os.getenv("LIVE_SESSION_TIMEOUT", "300"))
_STAGE_TIMEOUT:   int = int(os.getenv("LIVE_STAGE_TIMEOUT",   "30"))
_BACKEND_URL:     str = os.getenv("LIVE_BACKEND_URL", "http://localhost:8000")


# ── Hard session timeout via SIGALRM (Unix/macOS) ─────────────────────────────

def _alarm_handler(signum, frame):
    sys.stderr.write(
        f"\n\n[LIVE TESTS] Hard session timeout ({_SESSION_TIMEOUT}s) reached — aborting.\n"
        "  Increase with: LIVE_SESSION_TIMEOUT=<seconds> bash run-live-tests.sh\n\n"
    )
    sys.stderr.flush()
    os._exit(124)   # 124 mirrors the POSIX `timeout` command exit code


if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _alarm_handler)


def pytest_sessionstart(session):
    if hasattr(signal, "SIGALRM"):
        signal.alarm(_SESSION_TIMEOUT)
        print(
            f"\n[live] Hard session timeout armed: {_SESSION_TIMEOUT}s  "
            f"(override with LIVE_SESSION_TIMEOUT)\n",
            flush=True,
        )


def pytest_sessionfinish(session, exitstatus):
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


# ── Interactive helpers ────────────────────────────────────────────────────────

def _timed_input(prompt: str, timeout: int, default: str = "") -> str:
    """Read from stdin; return `default` if `timeout` seconds pass without input."""
    if not sys.stdin.isatty():
        print(f"{prompt}[non-interactive — using: '{default}']", flush=True)
        return default

    result = [default]
    answered = threading.Event()

    def _read():
        try:
            val = input(prompt)
            result[0] = val.strip() if val.strip() else default
        except EOFError:
            pass
        finally:
            answered.set()

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    if not answered.wait(timeout):
        print(
            f"\n  [timeout] {timeout}s elapsed — auto-continuing with default: '{default}'",
            flush=True,
        )
    return result[0]


def _stage_gate(title: str, description: str = "", skip_on_deny: bool = True) -> bool:
    """
    Print an interactive checkpoint banner before a test stage.

    Returns True to proceed, False if the user typed 'n'/'no'.
    Auto-proceeds with True after LIVE_STAGE_TIMEOUT seconds.
    """
    sep = "─" * 64
    print(f"\n{sep}", flush=True)
    print(f"  STAGE ▶  {title}", flush=True)
    if description:
        print(f"  {description}", flush=True)
    print(f"  (auto-continues in {_STAGE_TIMEOUT}s — Ctrl+C to abort all)", flush=True)
    print(sep, flush=True)
    ans = _timed_input("  Proceed? [Y/n]: ", _STAGE_TIMEOUT, "y")
    return ans.strip().lower() not in {"n", "no"}


# ── API key guard ──────────────────────────────────────────────────────────────

def _require_real_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key.startswith("sk-test") or key in {"test-key", "sk-fake"}:
        pytest.skip(
            "OPENAI_API_KEY is missing or is a placeholder — live tests require a real key.\n"
            "  Export a real key and re-run:  LIVE_TESTS=1 bash run-live-tests.sh",
            allow_module_level=True,
        )
    return key


# ── Session-scoped fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def openai_api_key() -> str:
    return _require_real_api_key()


@pytest.fixture(scope="session")
def backend_url() -> str:
    return _BACKEND_URL


@pytest.fixture(scope="session")
def live_http_client(backend_url: str):
    """httpx client pointed at a running backend. Skips the file if server is unreachable."""
    try:
        r = httpx.get(f"{backend_url}/api/health", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Backend not reachable at {backend_url}: {exc}")
    with httpx.Client(base_url=backend_url, timeout=60) as client:
        yield client


@pytest.fixture(scope="session")
def live_auth_headers(live_http_client: httpx.Client) -> dict:
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        pytest.skip(
            "ADMIN_PASSWORD env var is not set.\n"
            "  The startup banner prints it; or retrieve it with:\n"
            "    export ADMIN_PASSWORD=$(grep ADMIN_PASSWORD backend/.env | cut -d= -f2-)"
        )
    resp = live_http_client.post(
        "/api/auth/login",
        json={"username": os.getenv("ADMIN_USERNAME", "admin"), "password": password},
    )
    assert resp.status_code == 200, (
        f"Live auth login failed ({resp.status_code}): {resp.text}\n"
        f"  Ensure ADMIN_PASSWORD matches the running server's backend/.env."
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def prompt_question() -> str:
    """
    Ask the user once per session for a question to drive the agent tests.
    Skipped if LIVE_QUESTION is set or no TTY (CI / piped).
    """
    env_q = os.getenv("LIVE_QUESTION", "").strip()
    default = env_q if env_q else "What is Retrieval-Augmented Generation and how does it work?"
    print(f"\n[live] Enter the question to use across all agent stages.", flush=True)
    print(f"  LIVE_QUESTION env var pre-sets this without prompting.", flush=True)
    return _timed_input(f"  Question [{default}]: ", _STAGE_TIMEOUT, default)


# ── Function-scoped fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def stage_gate():
    """Inject into a test to display an interactive stage checkpoint with timeout."""
    return _stage_gate
