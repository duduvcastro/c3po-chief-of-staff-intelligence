import base64
import hashlib
import hmac
import html
import re
import secrets
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

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

    def request_code(self, email: str, requested_ip: str) -> tuple[str, int]:
        normalized_email = email.strip().lower()
        if not self.database.database_url and normalized_email == self.settings.auth_email.strip().lower():
            self.database.ensure_access_owner(normalized_email, list(ALL_VIEW_PERMISSIONS))
        access_user = self.database.get_access_user(normalized_email)
        now = self.now()
        since = now - timedelta(minutes=15)
        if self.database.recent_login_code_count(normalized_email, requested_ip, since) >= 5:
            raise RateLimitError("Aguarde alguns minutos antes de solicitar outro código.")

        challenge_id = str(uuid4())
        code = f"{secrets.randbelow(1_000_000):06d}"
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
            }
        )

        if access_user and access_user["is_active"]:
            self.send_code_email(code, normalized_email)
        return challenge_id, self.settings.auth_code_minutes * 60

    def verify_code(self, challenge_id: str, code: str, requested_ip: str) -> tuple[str, datetime, str]:
        now = self.now()
        challenge = self.database.get_login_code(challenge_id)
        if not challenge:
            raise AuthenticationError("Código inválido ou expirado.")
        if challenge.get("used_at") or challenge["expires_at"] <= now:
            raise AuthenticationError("Código inválido ou expirado.")
        if challenge["attempts"] >= challenge["max_attempts"]:
            raise AuthenticationError("Limite de tentativas atingido. Solicite outro código.")

        expected = self.code_hash(challenge_id, code)
        valid = hmac.compare_digest(expected, challenge["code_hash"])
        self.database.record_login_attempt(challenge_id, used_at=now if valid else None)
        access_user = self.database.get_access_user(challenge["email"])
        if not valid or not access_user or not access_user["is_active"]:
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
        body = f"""
        <div style="font-family:Arial,sans-serif;color:#17191e;max-width:520px;padding:24px">
          <div style="font-size:13px;color:#8a6a17;font-weight:700">C3PO | CHIEF OF STAFF INTELLIGENCE</div>
          <h1 style="font-size:24px;margin:18px 0 8px">Código de acesso</h1>
          <p style="font-size:14px;line-height:1.5;color:#5c6570">Use o código abaixo para concluir seu login. Ele expira em {self.settings.auth_code_minutes} minutos.</p>
          <div style="font-size:34px;font-weight:800;letter-spacing:8px;background:#f7f2e4;border:1px solid #dbc47f;border-radius:6px;padding:18px 22px;text-align:center;margin:22px 0">{html.escape(code)}</div>
          <p style="font-size:12px;line-height:1.5;color:#7b838d">Se você não solicitou este acesso, ignore esta mensagem. O código funciona uma única vez.</p>
        </div>
        """
        self._send_html_email(subject, body, recipient_email)

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
        if not self.settings.exchange_server or not self.settings.exchange_user or not self.settings.exchange_app_password:
            raise EmailDeliveryError("Exchange não está configurado para enviar a notificação.")

        request_body = f"""
        <m:CreateItem MessageDisposition="SendAndSaveCopy">
          <m:SavedItemFolderId><t:DistinguishedFolderId Id="sentitems" /></m:SavedItemFolderId>
          <m:Items><t:Message>
            <t:Subject>{html.escape(subject)}</t:Subject>
            <t:Body BodyType="HTML">{html.escape(body)}</t:Body>
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
            f"{self.settings.exchange_user}:{self.settings.exchange_app_password}".encode("utf-8")
        ).decode("ascii")
        request = urllib.request.Request(
            f"https://{self.settings.exchange_server}/EWS/Exchange.asmx",
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
