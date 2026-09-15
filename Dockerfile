FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/var/evals.db \
    STATIC_DIR=/app/frontend/dist
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY data/ ./data/
RUN pip install --no-cache-dir .
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
RUN mkdir -p /app/var && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
