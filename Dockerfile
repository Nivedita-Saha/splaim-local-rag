# Quality-gate image for splaim-local-rag.
#
# SCOPE (deliberate): this image builds the source and runs the full
# static-analysis + test gate (ruff, mypy, bandit, pytest) in a clean,
# from-scratch environment. It does NOT install Ollama or pull model
# weights: the RAG pipeline needs a host Ollama daemon and local models
# that are out of scope for a slim CI container. The image verifies that
# the code assembles and the quality gate passes in isolation.

FROM python:3.12-slim

WORKDIR /app

# Install dev/CI dependencies first (better layer caching)
COPY requirements-dev.txt pyproject.toml ./
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements-dev.txt

# Copy the source and tests
COPY src/ ./src/
COPY tests/ ./tests/

# Default: run the same quality gate as CI
CMD ["sh", "-c", "ruff check src tests && mypy src && bandit -r src && pytest -q"]
