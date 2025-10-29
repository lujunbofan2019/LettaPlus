# file: Dockerfile.stub-mcp
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STUB_CONFIG=/app/generated/stub/stub_config.json \
    STUB_MCP_HOST=0.0.0.0 \
    STUB_MCP_PORT=8765 \
    STUB_MCP_PATH=/mcp

RUN pip install --no-cache-dir mcp>=1.2 uvicorn>=0.30

WORKDIR /app
COPY stub_mcp_server.py /app/stub_mcp_server.py
# Expect you to mount ../generated/stub into /app/generated/stub at runtime

EXPOSE 8765
CMD ["python", "/app/stub_mcp_server.py"]
