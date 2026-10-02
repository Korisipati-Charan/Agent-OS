# Multi-stage security-hardened Dockerfile for AgentOS
FROM python:3.11.17-slim-trixie AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY README.md .
COPY agentos ./agentos
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir --prefix=/install .

# Production Runner Stage
FROM python:3.11.17-slim-trixie AS runner

# Apply Debian security updates and remove build-time Python package tooling.
RUN apt-get update \
    && apt-get upgrade -y \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 agentos && \
    useradd -u 10001 -g agentos -s /bin/bash -m agentos

WORKDIR /app

# Copy only the application and declared runtime dependencies.
COPY --from=builder /install /usr/local
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
