#!/usr/bin/env python3
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


HOST = os.getenv("PLUGGY_WEBHOOK_BIND", "0.0.0.0")
PORT = int(os.getenv("PLUGGY_WEBHOOK_PORT", "8080"))
TOKEN = os.getenv("PLUGGY_WEBHOOK_TOKEN", "")
EVENT_LOG = Path(os.getenv("PLUGGY_WEBHOOK_LOG", "outputs/pluggy-webhook-events.jsonl"))
MAX_BODY_BYTES = 1_048_576
LOG_LOCK = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_event(payload):
    transaction_ids = payload.get("transactionIds")
    if not isinstance(transaction_ids, list):
        transaction_ids = []
    return {
        "receivedAt": utc_now(),
        "event": payload.get("event"),
        "eventId": payload.get("eventId"),
        "itemId": payload.get("itemId"),
        "clientUserId": payload.get("clientUserId"),
        "triggeredBy": payload.get("triggeredBy"),
        "transactionCount": len(transaction_ids),
    }


def append_event(event):
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
    with LOG_LOCK:
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class PluggyWebhookHandler(BaseHTTPRequestHandler):
    server_version = "ChiefOfStaffWebhook/1.0"

    def log_message(self, _format, *_args):
        return

    def send_empty(self, status):
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if urlsplit(self.path).path != "/health":
            self.send_empty(404)
            return
        body = json.dumps({"status": "ok", "time": utc_now()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlsplit(self.path).path != "/pluggy/webhook":
            self.send_empty(404)
            return
        if not TOKEN:
            self.send_empty(503)
            return
        supplied_token = self.headers.get("X-Webhook-Token", "")
        if not hmac.compare_digest(supplied_token, TOKEN):
            self.send_empty(401)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_empty(400)
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self.send_empty(413)
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_empty(400)
            return
        if not isinstance(payload, dict) or not payload.get("event"):
            self.send_empty(400)
            return
        append_event(safe_event(payload))
        self.send_empty(204)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("PLUGGY_WEBHOOK_TOKEN is required")
    ThreadingHTTPServer((HOST, PORT), PluggyWebhookHandler).serve_forever()
