FROM python:3.11-slim

# Install OS deps (optional but useful)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install python deps first (better layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY server.py ./server.py
COPY tools ./tools
COPY schemas ./schemas

# Create default manifests dir inside container
RUN mkdir -p /app/dcf_manifests

# Environment (can be overridden via compose)
ENV DCF_MANIFESTS_DIR=/app/dcf_manifests \
    SKILL_PREVIEW_CHARS=400 \
    PYTHONUNBUFFERED=1

EXPOSE 7337

# Streamable HTTP via ASGI (uvicorn)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7337"]
