FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG C3PO_SECURITY_REBUILD=bootstrap
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        libssl3t64 \
        openssl \
        openssl-provider-legacy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tests ./tests
COPY db ./db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
