FROM python:3.11-slim

# HF Spaces requires a non-root user with uid 1000
RUN useradd -m -u 1000 user

WORKDIR /app

# Build dependencies for native extensions (uvloop, scikit-learn wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source and macro data CSVs
COPY app/ ./app/
COPY data/ ./data/

RUN chown -R user:user /app

USER user

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# HF Spaces Docker default port
EXPOSE 7860

# --proxy-headers + --forwarded-allow-ips=* so uvicorn trusts X-Forwarded-* from HF's reverse proxy
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "7860", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
