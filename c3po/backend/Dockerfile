# Alpine base (same family as the web and database images): no perl, and a
# util-linux with the fixes Debian trixie has not shipped yet. All compiled
# dependencies in requirements.txt publish musllinux wheels.
FROM python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG C3PO_SECURITY_REBUILD=bootstrap
# tzdata: zoneinfo for America/Sao_Paulo and America/New_York (ZoneInfo).
# libstdc++/libgcc: runtime for the numpy/pandas/pydantic-core musl wheels.
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && apk upgrade --no-cache \
    && apk add --no-cache tzdata libstdc++ libgcc

WORKDIR /app

COPY backend/requirements.txt .
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tests ./tests
COPY db ./db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
