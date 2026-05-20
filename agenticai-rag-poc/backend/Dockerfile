# Python 3.13-slim is the base image.
# Supported range: 3.11–3.13.
# Python 3.14+ does not yet have pre-built wheels for pydantic-core / bcrypt.
FROM python:3.13-slim AS base

WORKDIR /app

# OS-level deps: libmagic1 for python-magic (MIME detection)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
