from __future__ import annotations

import base64
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .config import Settings


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class APNsResponse:
    status_code: int
    reason: str | None = None


class APNsClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._jwt: tuple[str, float] | None = None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        path = self.settings.watch_apns_private_key_path
        return bool(
            self.settings.watch_apns_key_id.strip()
            and self.settings.watch_apns_team_id.strip()
            and self.settings.watch_apns_bundle_id.strip()
            and path.is_file()
        )

    def send(
        self,
        *,
        device_token: str,
        payload: dict[str, Any],
        push_type: str = "alert",
    ) -> APNsResponse:
        normalized = device_token.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64,200}", normalized):
            raise ValueError("Invalid APNs device token")
        if not self.configured:
            raise RuntimeError("Watch APNs is not configured")
        host = (
            "https://api.push.apple.com"
            if self.settings.watch_apns_environment == "production"
            else "https://api.sandbox.push.apple.com"
        )
        kwargs = {
            "url": f"{host}/3/device/{normalized}",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            "headers": {
                "authorization": f"bearer {self._authorization_token()}",
                "apns-topic": self.settings.watch_apns_bundle_id,
                "apns-push-type": push_type,
                "apns-priority": "10" if push_type == "alert" else "5",
                "apns-expiration": "0",
            },
            "timeout": self.settings.watch_apns_timeout_seconds,
        }
        if self.transport:
            response = self.transport(**kwargs)
        else:
            with httpx.Client(http2=True, timeout=self.settings.watch_apns_timeout_seconds) as client:
                response = client.post(**kwargs)
        reason = None
        try:
            reason = response.json().get("reason")
        except Exception:
            pass
        return APNsResponse(status_code=int(response.status_code), reason=reason)

    def _authorization_token(self) -> str:
        now = time.time()
        with self._lock:
            if self._jwt and now - self._jwt[1] < 50 * 60:
                return self._jwt[0]
            token = self._make_jwt(int(now))
            self._jwt = (token, now)
            return token

    def _make_jwt(self, issued_at: int) -> str:
        header = _b64url(json.dumps(
            {"alg": "ES256", "kid": self.settings.watch_apns_key_id.strip()},
            separators=(",", ":"),
        ).encode())
        claims = _b64url(json.dumps(
            {"iss": self.settings.watch_apns_team_id.strip(), "iat": issued_at},
            separators=(",", ":"),
        ).encode())
        signing_input = f"{header}.{claims}".encode("ascii")
        key_payload = Path(self.settings.watch_apns_private_key_path).read_bytes()
        private_key = serialization.load_pem_private_key(key_payload, password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("APNs private key must be elliptic-curve PKCS8")
        der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{header}.{claims}.{_b64url(signature)}"
