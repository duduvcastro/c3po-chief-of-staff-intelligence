#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.getenv("PLUGGY_BASE_URL", "https://api.pluggy.ai").rstrip("/")
CLIENT_ID = os.getenv("PLUGGY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("PLUGGY_CLIENT_SECRET", "")
WEBHOOK_HOST = os.getenv("PLUGGY_WEBHOOK_HOST", "")
WEBHOOK_TOKEN = os.getenv("PLUGGY_WEBHOOK_TOKEN", "")


def request_json(method, path, payload=None, api_key=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-KEY"] = api_key
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Pluggy API {exc.code}: {detail}") from exc
    return json.loads(body) if body else {}


def list_rows(payload):
    if isinstance(payload, list):
        return payload
    for key in ("results", "data", "webhooks"):
        rows = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(rows, list):
            return rows
    return []


def main():
    missing = [
        name
        for name, value in (
            ("PLUGGY_CLIENT_ID", CLIENT_ID),
            ("PLUGGY_CLIENT_SECRET", CLIENT_SECRET),
            ("PLUGGY_WEBHOOK_HOST", WEBHOOK_HOST),
            ("PLUGGY_WEBHOOK_TOKEN", WEBHOOK_TOKEN),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing environment values: {', '.join(missing)}")

    auth = request_json(
        "POST", "/auth", {"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET}
    )
    api_key = auth.get("apiKey")
    if not api_key:
        raise RuntimeError("Pluggy authentication did not return apiKey")

    target_url = f"https://{WEBHOOK_HOST}/pluggy/webhook"
    existing = list_rows(request_json("GET", "/webhooks", api_key=api_key))
    for webhook in existing:
        if webhook.get("event") == "all" and webhook.get("url") == target_url:
            print(
                json.dumps(
                    {
                        "status": "existing",
                        "id": webhook.get("id"),
                        "event": webhook.get("event"),
                        "url": webhook.get("url"),
                    }
                )
            )
            return

    created = request_json(
        "POST",
        "/webhooks",
        {
            "event": "all",
            "url": target_url,
            "headers": {"X-Webhook-Token": WEBHOOK_TOKEN},
        },
        api_key=api_key,
    )
    print(
        json.dumps(
            {
                "status": "created",
                "id": created.get("id"),
                "event": created.get("event"),
                "url": created.get("url"),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
