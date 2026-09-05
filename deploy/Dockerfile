# Multi-stage hardened production Dockerfile for DietFit
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies in isolated wheels
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# Final runtime image
FROM python:3.11-slim

# Create dedicated non-root user and group with explicit UID/GID
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy wheels from builder and install
COPY --from=builder /app/wheels /app/wheels
RUN pip install --no-cache-dir /app/wheels/* && rm -rf /app/wheels

# Copy application source code
COPY --chown=appuser:appgroup . /app

# Create dedicated runtime data and log directories with restricted permissions
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appgroup /app/data /app/logs && \
    chmod 700 /app/data /app/logs

# Switch to non-root user
USER appuser

# Expose internal Streamlit port (bound only to internal container network)
EXPOSE 8501

# Healthcheck to verify service responsiveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health').read()" || exit 1

# Launch Streamlit with production flags
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
