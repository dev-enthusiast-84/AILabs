"""Vercel Python serverless entry point.

Vercel routes all /api/* requests here. FastAPI handles them with its own
/api/* routing (planner→retriever→generator→validator pipeline).

Required Vercel env vars:
  SECRET_KEY, ADMIN_PASSWORD, VECTOR_STORE_TYPE=pinecone

Billing-bearing provider settings such as OPENAI_API_KEY, PINECONE_API_KEY,
BLOB_READ_WRITE_TOKEN, LangSmith keys, and model/token controls are ignored
from env when APP_ENV=production. Enter them through the app Settings UI.

Optional deployment shape for durable original file previews/downloads:
  FILE_STORE_TYPE=blob
"""
import os
import sys

# Put backend/ on the path so `from app.xxx import yyy` works.
#
# Local repo layout:        <repo>/api/index.py          + <repo>/backend/app
# Vercel Services layout:  /var/task/index.py (flattened) + /var/task/backend/app
_here = os.path.dirname(os.path.abspath(__file__))
for _candidate in (
    os.path.join(_here, "backend"),
    os.path.join(_here, "..", "backend"),
):
    if os.path.isdir(os.path.join(_candidate, "app")):
        sys.path.insert(0, _candidate)
        break

from app.main import app  # noqa: F401  — Vercel ASGI handler
