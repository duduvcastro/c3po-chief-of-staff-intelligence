FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    CHROME_BIN=/usr/bin/chromium

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        chromium \
        fonts-liberation \
        fonts-dejavu-core \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY work /app/work

RUN mkdir -p /app/outputs /app/work/billfish_reports

CMD ["sh", "work/cloud_run.sh", "--no-send"]
