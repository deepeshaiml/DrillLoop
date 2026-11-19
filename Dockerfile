FROM node:24-alpine3.22@sha256:191c9f0080fcbbc6547a85dc0ff7988072214a355aabdc1d2ec55a7dae5eea8a AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.16-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS runtime
ARG TESSERACT_OCR_VERSION=5.5.0-1+b1
ARG TESSERACT_ENG_VERSION=1:4.1.0-2
ARG BUILD_VERSION=dev
ARG BUILD_REVISION=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DRILLLOOP_BUILD_VERSION=${BUILD_VERSION} \
    DRILLLOOP_BUILD_REVISION=${BUILD_REVISION}
WORKDIR /app
COPY requirements-prod.lock ./
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        "tesseract-ocr=${TESSERACT_OCR_VERSION}" \
        "tesseract-ocr-eng=${TESSERACT_ENG_VERSION}" \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --require-hashes -r requirements-prod.lock \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin drillloop
COPY --chown=10001:10001 backend/ ./backend/
COPY --chown=10001:10001 migrations/ ./migrations/
COPY --chown=10001:10001 alembic.ini ./alembic.ini
COPY --chown=10001:10001 demo/ ./demo/
COPY --from=frontend-build --chown=10001:10001 /build/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
