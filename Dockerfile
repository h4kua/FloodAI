FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    openai \
    apscheduler \
    psycopg2-binary \
    python-dotenv \
    pydantic \
    httpx \
    requests \
    beautifulsoup4 \
    "scikit-learn==1.8.0" \
    xgboost \
    "numpy==1.26.4" \
    pandas \
    joblib \
    structlog \
    python-json-logger \
    prometheus-fastapi-instrumentator \
    prometheus_client \
    tenacity \
    PyJWT \
    python-multipart \
    argon2-cffi \
    imbalanced-learn \
    shap

COPY api/ ./api/
COPY agents/ ./agents/
COPY services/ ./services/
COPY pipeline/ ./pipeline/
COPY config/ ./config/
COPY db/ ./db/
COPY models/ ./models/
COPY artifacts/ ./artifacts/

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
