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
# The base image bundles the pip of its build date; the scanner reports pip's own
# advisories (CVE-2025-8869, CVE-2026-1703/3219/6357/8643/13346 on pip 25.0.1), so pip
# is upgraded to a fixed release before the application dependencies are installed.
# pip is a build tool: it installs the pinned dependencies and verifies them (`pip check`), then
# leaves the runtime image. pip vendors its own copies of msgpack and setuptools (pip/_vendor,
# declared in its CycloneDX BOM), which the scanner reports as findings the application never
# uses; without pip in the image there is nothing to report and nothing to install at runtime.
RUN test -n "$C3PO_SECURITY_REBUILD" \
    && pip install --no-cache-dir --upgrade "pip>=26.2" \
    && pip install --no-cache-dir -r requirements.txt \
    && pip check \
    && pip uninstall -y pip \
    && python -c "import importlib.util, sys; sys.exit(1 if importlib.util.find_spec('pip') else 0)"

COPY backend/app ./app
COPY backend/tests ./tests
COPY db ./db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
