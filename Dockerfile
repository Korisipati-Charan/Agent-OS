# Multi-stage security-hardened Dockerfile for AgentOS
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .

# Production Runner Stage
FROM python:3.11-slim-bookworm AS runner

# Security: Non-root user with explicit UID/GID
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && groupadd -g 10001 agentos \
    && useradd -u 10001 -g agentos -s /bin/bash -m agentos \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY agentos /app/agentos
COPY agentos.yaml /app/agentos.yaml

# Create necessary mount points with proper permissions
RUN mkdir -p /app/data /app/workspace /app/logs && \
    chown -R agentos:agentos /app

# Principle: Read-only root filesystem compatible
USER 10001:10001

EXPOSE 8000
VOLUME ["/app/data", "/app/workspace"]

ENTRYPOINT ["python", "-m", "agentos"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
