# ============================================
# Bot AI Trading - Production Dockerfile
# ============================================
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies for native Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r botuser && useradd -r -g botuser -m botuser

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Copy application code
COPY *.py ./
COPY templates/ ./templates/

# Copy AI models (pre-trained)
COPY models/ ./models/

# Create logs directory
RUN mkdir -p logs && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Expose dashboard port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/status || exit 1

# Start with gunicorn (production WSGI server)
# Single worker because the bot uses threading + asyncio internally
# Render sets $PORT dynamically — must use shell form to expand it
CMD gunicorn \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 1 \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    web_dashboard:app
