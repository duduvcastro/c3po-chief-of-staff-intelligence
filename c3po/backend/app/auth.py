import base64
import hashlib
import hmac
import html
import re
import secrets
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken

from .access_control import ALL_VIEW_PERMISSIONS
from .config import Settings
from .database import Database


class AuthenticationError(Exception):
    pass


class RateLimitError(AuthenticationError):
    pass


class EmailDeliveryError(AuthenticationError):
    pass


class AuthService:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def code_hash(self, challenge_id: str, code: str) -> str:
        message = f"{challenge_id}:{code}".encode("utf-8")
        return hmac.new(self.settings.auth_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def _totp_cipher(self) -> Fernet:
        key = hashlib.sha256(f"c3po:totp:{self.settings.auth_secret}".encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    def encrypt_totp_secret(self, secret: str) -> str:
        return self._totp_cipher().encrypt(secret.encode("ascii")).decode("ascii")

    def decrypt_totp_secret(self, encrypted_secret: str) -> str:
        try:
            return self._totp_cipher().decrypt(encrypted_secret.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError) as exc:
            raise AuthenticationError("A configuração do autenticador não pôde ser lida.") from exc

    @staticmethod
    def totp_code(secret: str, step: int) -> str:
        padding = "=" * ((8 - len(secret) % 8) % 8)
        key = base64.b32decode(secret + padding, casefold=True)
        digest = hmac.new(key, step.to_bytes(8, "big"), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
        return f"{value % 1_000_000:06d}"

    def matching_totp_step(self, secret: str, code: str, now: datetime) -> int | None:
        current_step = int(now.timestamp()) // 30
        for step in (current_step, current_step - 1, current_step + 1):
            if hmac.compare_digest(self.totp_code(secret, step), code):
                return step
        return None

    def totp_enabled(self, email: str) -> bool:
        credential = self.database.get_totp_credential(email)
        return bool(credential and credential.get("confirmed_at"))

    def begin_totp_setup(self, email: str) -> dict[str, str | int]:
        normalized_email = email.strip().lower()
        if self.totp_enabled(normalized_email):
            raise AuthenticationError("O autenticador já está ativo para este usuário.")
        now = self.now()
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        expires_at = now + timedelta(minutes=10)
        self.database.upsert_totp_setup(normalized_email, self.encrypt_totp_secret(secret), expires_at, now)
        label = quote(f"C3PO:{normalized_email}", safe="")
        issuer = quote("C3PO", safe="")
        uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
        image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
        output = BytesIO()
        image.save(output)
        qr_data_url = "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode("ascii")
        return {"secret": secret, "otpauth_uri": uri, "qr_code_data_url": qr_data_url, "expires_in_seconds": 600}

    def confirm_totp_setup(self, email: str, code: str) -> None:
        now = self.now()
        credential = self.database.get_totp_credential(email)
        if not credential or credential.get("confirmed_at") or credential["setup_expires_at"] <= now:
            raise AuthenticationError("A configuração expirou. Gere um novo QR Code.")
        secret = self.decrypt_totp_secret(credential["encrypted_secret"])
        step = self.matching_totp_step(secret, code, now)
        if step is None or not self.database.confirm_totp(email, step, now):
            raise AuthenticationError("Código inválido. Confira o app Senhas e tente novamente.")

    def disable_totp(self, email: str, code: str) -> None:
        now = self.now()
        credential = self.database.get_totp_credential(email)
        if not credential or not credential.get("confirmed_at"):
            raise AuthenticationError("O autenticador não está ativo.")
        secret = self.decrypt_totp_secret(credential["encrypted_secret"])
        if self.matching_totp_step(secret, code, now) is None:
            raise AuthenticationError("Código inválido.")
        self.database.delete_totp_credential(email)

    @staticmethod
    def session_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def describe_client(
        user_agent: str,
        *,
        platform: str = "",
        max_touch_points: int = 0,
    ) -> dict[str, str]:
        ua = (user_agent or "").strip()
        ua_lower = ua.lower()
        platform_lower = (platform or "").strip().lower()

        def version(pattern: str) -> str:
            match = re.search(pattern, ua, flags=re.IGNORECASE)
            return match.group(1).replace("_", ".") if match else ""

        is_ipad = "ipad" in ua_lower or (
            platform_lower.startswith("mac") and max_touch_points > 1 and "mobile/" in ua_lower
        )
        is_iphone = "iphone" in ua_lower
        is_android = "android" in ua_lower

        if is_ipad:
            device_type = "iPad"
            os_name = "iPadOS"
            os_version = version(r"OS ([0-9_]+)") if "ipad" in ua_lower else ""
        elif is_iphone:
            device_type = "iPhone"
            os_name = "iOS"
            os_version = version(r"OS ([0-9_]+)")
        elif is_android:
            is_mobile = "mobile" in ua_lower
            device_type = "Celular Android" if is_mobile else "Tablet Android"
            os_name = "Android"
            os_version = version(r"Android\s+([0-9.]+)")
        elif "cros" in ua_lower:
            device_type = "Chromebook"
            os_name = "ChromeOS"
            os_version = version(r"CrOS\s+[^\s]+\s+([0-9.]+)")
        elif "windows" in ua_lower or platform_lower.startswith("win"):
            device_type = "Computador (desktop/laptop)"
            os_name = "Windows"
            windows_version = version(r"Windows NT\s+([0-9.]+)")
            os_version = {
                "10.0": "10/11",
                "6.3": "8.1",
                "6.2": "8",
                "6.1": "7",
            }.get(windows_version, windows_version)
        elif "macintosh" in ua_lower or platform_lower.startswith("mac"):
            device_type = "Computador Apple (desktop/laptop)"
            os_name = "macOS"
            os_version = version(r"Mac OS X\s+([0-9_.]+)")
        elif "linux" in ua_lower or platform_lower.startswith("linux"):
            device_type = "Computador (desktop/laptop)"
            os_name = "Linux"
            os_version = ""
        elif "mobile" in ua_lower:
            device_type = "Celular"
            os_name = "Sistema móvel"
            os_version = ""
        else:
            device_type = "Dispositivo não identificado"
            os_name = "Sistema não identificado"
            os_version = ""

        browser_candidates = (
            ("Microsoft Edge", r"(?:EdgA|EdgiOS|Edg)/([0-9.]+)"),
            ("Opera", r"OPR/([0-9.]+)"),
            ("Samsung Internet", r"SamsungBrowser/([0-9.]+)"),
            ("Chrome", r"(?:CriOS|Chrome)/([0-9.]+)"),
            ("Firefox", r"(?:FxiOS|Firefox)/([0-9.]+)"),
            ("Safari", r"Version/([0-9.]+)"),
        )
        browser_name = "Navegador não identificado"
        browser_version = ""
        for candidate_name, candidate_pattern in browser_candidates:
            candidate_version = version(candidate_pattern)
            if candidate_version:
                browser_name = candidate_name
                browser_version = candidate_version
                break

        return {
            "device_type": device_type,
            "os": f"{os_name} {os_version}".strip(),
            "browser": f"{browser_name} {browser_version}".strip(),
        }

    def request_code(
        self, email: str, requested_ip: str, delivery_method: str = "auto",
    ) -> tuple[str, int, str, tuple[str, str] | None]:
        normalized_email = email.strip().lower()
        if not self.database.database_url and normalized_email == self.settings.auth_email.strip().lower():
            self.database.ensure_access_owner(normalized_email, list(ALL_VIEW_PERMISSIONS))
        access_user = self.database.get_access_user(normalized_email)
        now = self.now()
        since = now - timedelta(minutes=self.settings.auth_rate_limit_minutes)
        email_count, ip_count = self.database.recent_login_code_counts(normalized_email, requested_ip, since)
        if (
            email_count >= self.settings.auth_request_limit_per_email
            or ip_count >= self.settings.auth_request_limit_per_ip
        ):
            raise RateLimitError("Aguarde alguns minutos antes de solicitar outro código.")

        challenge_id = str(uuid4())
        code = f"{secrets.randbelow(1_000_000):06d}"
        verification_method = "totp" if delivery_method == "auto" and self.totp_enabled(normalized_email) else "email"
        expires_at = now + timedelta(minutes=self.settings.auth_code_minutes)
        self.database.create_login_code(
            {
                "id": challenge_id,
                "email": normalized_email,
                "code_hash": self.code_hash(challenge_id, code),
                "expires_at": expires_at,
                "attempts": 0,
                "max_attempts": 5,
                "requested_ip": requested_ip,
                "created_at": now,
                "verification_method": verification_method,
            }
        )

        self.database.record_audit_event(
            normalized_email, "auth.otp_requested", "auth_challenge", challenge_id,
            {"requested_ip": requested_ip, "delivery_requested": delivery_method},
        )
        delivery = (code, normalized_email) if verification_method == "email" and access_user and access_user["is_active"] else None
        return challenge_id, self.settings.auth_code_minutes * 60, verification_method, delivery

    def verify_code(self, challenge_id: str, code: str, requested_ip: str) -> tuple[str, datetime, str]:
        now = self.now()
        challenge = self.database.get_login_code(challenge_id)
        if not challenge:
            raise AuthenticationError("Código inválido ou expirado.")
        access_user = self.database.get_access_user(challenge["email"])
        if challenge.get("verification_method") == "totp":
            credential = self.database.get_totp_credential(challenge["email"])
            secret = self.decrypt_totp_secret(credential["encrypted_secret"]) if credential and credential.get("confirmed_at") else ""
            step = self.matching_totp_step(secret, code, now) if secret else None
            valid = step is not None and self.database.claim_totp_step(challenge["email"], step, now)
        else:
            expected = self.code_hash(challenge_id, code)
            valid = hmac.compare_digest(expected, challenge["code_hash"])
        outcome, claimed = self.database.claim_login_attempt(
            challenge_id,
            code_valid=bool(valid and access_user and access_user["is_active"]),
            requested_ip=requested_ip,
            at=now,
            since=now - timedelta(minutes=self.settings.auth_rate_limit_minutes),
            ip_failure_limit=self.settings.auth_verify_failure_limit_per_ip,
        )
        if outcome == "rate_limited":
            raise RateLimitError("Muitas tentativas de acesso. Aguarde alguns minutos.")
        if outcome != "accepted" or not claimed:
            raise AuthenticationError("Código inválido ou expirado.")

        token = secrets.token_urlsafe(48)
        is_owner = access_user["role"] == "owner" or challenge["email"] == self.settings.auth_email.strip().lower()
        session_hours = self.settings.auth_owner_session_hours if is_owner else self.settings.auth_session_hours
        expires_at = now + timedelta(hours=session_hours)
        self.database.create_session(
            {
                "id": str(uuid4()),
                "email": challenge["email"],
                "token_hash": self.session_hash(token),
                "expires_at": expires_at,
                "created_at": now,
                "last_seen_at": now,
                "created_ip": requested_ip,
            }
        )
        self.database.touch_access_user_login(challenge["email"], now)
        return token, expires_at, challenge["email"]

    def authenticate(self, token: str | None, *, touch_activity: bool = False) -> dict | None:
        if not token:
            return None
        now = self.now()
        session = self.database.get_session(
            self.session_hash(token),
            now,
            idle_cutoff=now - timedelta(minutes=self.settings.auth_member_idle_minutes),
            idle_exempt_email=self.settings.auth_email,
            touch_activity=touch_activity,
        )
        if not session:
            return None
        access_user = self.database.get_access_user(session["email"])
        if not access_user or not access_user["is_active"]:
            return None
        return {**session, **access_user}

    def logout(self, token: str | None) -> None:
        if token:
            self.database.revoke_session(self.session_hash(token), self.now())

    def send_code_email(self, code: str, recipient_email: str) -> None:
        subject = "Seu código de acesso ao C3PO"
        body = (
            "C3PO | CHIEF OF STAFF INTELLIGENCE\n\n"
            f"Código de acesso: {code}\n\n"
            "Use este código para concluir seu login no C3PO. "
            f"Ele expira em {self.settings.auth_code_minutes} minutos e funciona uma única vez.\n\n"
            "Se você não solicitou este acesso, ignore esta mensagem."
        )
        self._send_text_email(subject, body, recipient_email)

    def send_login_notification(
        self,
        *,
        email: str,
        display_name: str,
        role: str,
        requested_ip: str,
        occurred_at: datetime,
        client_info: dict[str, str] | None = None,
    ) -> None:
        local_time = occurred_at.astimezone(ZoneInfo("America/Sao_Paulo"))
        identity = display_name.strip() or email
        role_label = "Proprietário" if role == "owner" else "Usuário autorizado"
        device = client_info or {}
        device_type = device.get("device_type") or "Não identificado"
        operating_system = device.get("os") or "Não identificado"
        browser = device.get("browser") or "Não identificado"
        subject = f"C3PO | Novo login: {identity}"
        body = f"""
        <div style="font-family:Arial,sans-serif;color:#17191e;max-width:560px;padding:24px">
          <div style="font-size:13px;color:#8a6a17;font-weight:700">C3PO | SECURITY NOTIFICATION</div>
          <h1 style="font-size:24px;margin:18px 0 8px">Novo acesso confirmado</h1>
          <p style="font-size:14px;line-height:1.5;color:#5c6570">Um usuário autorizado concluiu o login no C3PO.</p>
          <table style="width:100%;border-collapse:collapse;margin:22px 0;background:#f7f8fa;border:1px solid #dfe3e8">
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Usuário</td><td style="padding:11px 14px;font-weight:700;border-bottom:1px solid #dfe3e8">{html.escape(identity)}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">E-mail</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{html.escape(email)}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Perfil</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{role_label}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Data e hora</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{local_time.strftime('%d/%m/%Y às %H:%M:%S')}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Tipo de dispositivo</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{html.escape(device_type)}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Sistema operacional</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{html.escape(operating_system)}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d;border-bottom:1px solid #dfe3e8">Navegador</td><td style="padding:11px 14px;border-bottom:1px solid #dfe3e8">{html.escape(browser)}</td></tr>
            <tr><td style="padding:11px 14px;color:#68717d">Endereço IP</td><td style="padding:11px 14px">{html.escape(requested_ip or 'Não identificado')}</td></tr>
          </table>
          <p style="font-size:12px;line-height:1.5;color:#7b838d">Se você não reconhecer este acesso, remova ou suspenda o usuário imediatamente na aba Death Star.</p>
        </div>
        """
        self._send_html_email(subject, body, self.settings.auth_email)

    def _send_html_email(self, subject: str, body: str, recipient_email: str) -> None:
        self._send_email(subject, body, recipient_email, body_type="HTML")

    def _send_text_email(self, subject: str, body: str, recipient_email: str) -> None:
        self._send_email(subject, body, recipient_email, body_type="Text")

    def _send_email(self, subject: str, body: str, recipient_email: str, *, body_type: str) -> None:
        server = self.settings.notification_exchange_server or self.settings.exchange_server
        user = self.settings.notification_exchange_user or self.settings.exchange_user
        password = self.settings.notification_exchange_app_password or self.settings.exchange_app_password
        if not server or not user or not password:
            raise EmailDeliveryError("Exchange não está configurado para enviar a notificação.")

        request_body = f"""
        <m:CreateItem MessageDisposition="SendAndSaveCopy">
          <m:SavedItemFolderId><t:DistinguishedFolderId Id="sentitems" /></m:SavedItemFolderId>
          <m:Items><t:Message>
            <t:Subject>{html.escape(subject)}</t:Subject>
            <t:Body BodyType="{body_type}">{html.escape(body)}</t:Body>
            <t:ToRecipients><t:Mailbox><t:EmailAddress>{html.escape(recipient_email)}</t:EmailAddress></t:Mailbox></t:ToRecipients>
          </t:Message></m:Items>
        </m:CreateItem>
        """
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
          xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
          xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
          <s:Header><t:RequestServerVersion Version="Exchange2013" /></s:Header>
          <s:Body>{request_body}</s:Body>
        </s:Envelope>"""
        token = base64.b64encode(
            f"{user}:{password}".encode("utf-8")
        ).decode("ascii")
        request = urllib.request.Request(
            f"https://{server}/EWS/Exchange.asmx",
            data=envelope.encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "text/xml; charset=utf-8",
                "Accept": "text/xml",
                "User-Agent": "C3PO/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
            root = ET.fromstring(payload)
            namespace = {"m": "http://schemas.microsoft.com/exchange/services/2006/messages"}
            result = root.find(".//m:CreateItemResponseMessage", namespace)
            if result is None or result.attrib.get("ResponseClass") != "Success":
                raise EmailDeliveryError("O Exchange recusou o envio da notificação.")
        except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError) as exc:
            raise EmailDeliveryError("Não foi possível enviar a notificação pelo Exchange.") from exc
