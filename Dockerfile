# ==============================================================================
# HealthSlip AI - Production Container Image
# Multi-stage, non-root, security-hardened Docker image for FastAPI & WebSockets
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools for C-extension dependencies (cryptography, greenlet)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------------------
# Final Production Runtime Stage
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 healthslip && \
    useradd -u 10001 -g healthslip -m -s /bin/bash appuser

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Set environment paths
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8005 \
    HOST=0.0.0.0 \
    ENVIRONMENT=production

# Copy application source code
COPY --chown=appuser:healthslip . /app

# Switch to non-root security context
USER appuser

# Health check to ensure API and WebSocket endpoints are responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Expose container application port
EXPOSE 8005

# Run with Gunicorn Uvicorn workers in production or direct Uvicorn fallback
CMD ["python", "main.py"]
