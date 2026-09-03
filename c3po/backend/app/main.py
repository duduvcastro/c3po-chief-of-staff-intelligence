from contextlib import asynccontextmanager
from datetime import date, datetime
import asyncio
import hashlib
import ipaddress
import re
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .auth import AuthService, AuthenticationError, EmailDeliveryError, RateLimitError
from .api_performance import (
    PerformanceObservabilityService,
    api_performance,
    run_performance_flush_loop,
)
from .chewie_fundamentals import ChewieFundamentalsService
from .access_control import (
    ALL_CAPABILITIES,
    ALL_VIEW_PERMISSIONS,
    CAPABILITY_PERMISSIONS,
    VIEW_PERMISSIONS,
    normalize_capabilities,
    normalize_permissions,
    required_capability,
    required_permissions,
)
from .config import get_settings
from .database import Database
from .legacy import LegacySummaryReader
from .leah_cloud import LeahAuthenticationError, LeahCloudService
from .investor_relations import InvestorRelationsService
from .ir_valuation import InvestorRelationsValuationProcessor
from .market_data import LiveMarketsService, MarketDataService, RealtimeMarketsService
from .market_data.b3_screener import B3ScreenerService
from .market_data.eodhd_stream import EodhdRealtimeStream
from .market_data.http import MarketDataRequestError
from .market_data.us_screener import USScreeningService
from .one_pager import OnePagerGenerationError, OnePagerService
from .push_notifications import PushNotificationService
from .operational_incidents import OperationalIncidentService
from .governance_vulnerability import GovernanceVulnerabilityService
from .r2d2 import R2D2PaperService
from .open_finance import OpenFinanceService, PluggyRequestError
from .official_fundamentals import ensure_builtin_official_fundamentals
from .code_census import CodeCensusService
from .server_usage import ServerUsageService
from .system_health import SystemHealthService
from .weather import WeatherLocationNotFound, WeatherRequestError, WeatherService
from .news import NewsService
from .observability import init_sentry
from .schemas import (
    AccessPermission,
    AccessCapability,
    AccessUser,
    AccessUserCreateRequest,
    AccessUserListResponse,
    AccessUserUpdateRequest,
    AlertReadRequest,
    AlertReadResponse,
    AuthSessionResponse,
    B3CandidateResponse,
    ChewieFundamentalsResponse,
    ChewieSearchResponse,
    CommandCenterResponse,
    FeedbackRequest,
    FeedbackResponse,
    LoginCodeRequest,
    LoginCodeResponse,
    LoginVerifyRequest,
    TotpCodeRequest,
    TotpSetupResponse,
    TotpStatusResponse,
    LiveMarketIndexResponse,
    LiveMarketsResponse,
    InvestorRelationsResponse,
    InvestorRelationsReviewRequest,
    InvestorRelationsSyncResponse,
    InvestorRelationsWatchRequest,
    InstrumentIntradayResponse,
    MatrixPowerResponse,
    MarketDataProviderHealth,
    MarketDataQuoteResponse,
    MarketDataSyncRequest,
    NavigationIndicator,
    NavigationIndicatorsResponse,
    NavigationSeenRequest,
    NavigationSeenResponse,
    OnePagerListResponse,
    OnePagerReport,
    OnePagerRequest,
    OpenFinanceResponse,
    OperationalIncident,
    OperationalIncidentListResponse,
    OperationalIncidentResolveRequest,
    PageLoadPerformanceRequest,
    PageLoadPerformanceResponse,
    PerformanceHistoryResponse,
    PushMutationResponse,
    PushStatusResponse,
    PushSubscribeRequest,
    PushTestResponse,
    PushUnsubscribeRequest,
    Provenance,
    RealtimeMarketResponse,
    RealtimePortfolioIntradayResponse,
    RealtimePortfolioRequest,
    RealtimePortfolioResponse,
    RealtimePortfolioSymbolSearchResponse,
    R2D2DashboardResponse,
    R2D2LivePositionsResponse,
    ServerUsageResponse,
    SystemHealthResponse,
    ValuationChangeResponse,
    WeatherResponse,
    NewsResponse,
    LeahAgentPairRequest,
    LeahAgentPairResponse,
    LeahAgentSyncRequest,
    LeahAgentSyncResponse,
    LeahCloudResponse,
    LeahItem,
    LeahItemWriteRequest,
    LeahPairingResponse,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _current_summary_context(now: datetime | None = None) -> tuple[str, str, str]:
    local_now = now or datetime.now(SAO_PAULO)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=SAO_PAULO)
    else:
        local_now = local_now.astimezone(SAO_PAULO)

    hour = local_now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    summary_name = (
        "Morning Summary" if hour < 13 else "Lunch Summary" if hour < 19 else "Night Summary"
    )
    return greeting, f"{summary_name} - {local_now:%d/%m/%Y}", local_now.strftime("%d/%m/%Y")


settings = get_settings()
init_sentry(settings, service_name="api")
database = Database(settings)
legacy = LegacySummaryReader(settings.legacy_root)
auth_service = AuthService(settings, database)
market_data = MarketDataService(settings, database)
eodhd_stream = EodhdRealtimeStream(settings.eodhd_api_token, max_symbols=settings.r2d2_ws_max_symbols)
live_markets = LiveMarketsService(settings, market_data.http, stream=eodhd_stream)
realtime_markets = RealtimeMarketsService(settings, database, market_data.http, stream=eodhd_stream)
b3_screener = B3ScreenerService(settings, database, market_data.http)
investor_relations = InvestorRelationsService(settings, database)
ir_valuation_processor = InvestorRelationsValuationProcessor(database, b3_screener)
server_usage = ServerUsageService(settings, database)
code_census = CodeCensusService(settings, database)
performance_observability = PerformanceObservabilityService(settings, database, api_performance)
weather = WeatherService()
news = NewsService()
open_finance = OpenFinanceService(settings)
system_health = SystemHealthService(
    settings,
    database,
    legacy,
    open_finance,
    market_data,
    server_usage,
)
one_pagers = OnePagerService(
    settings,
    database,
    market_data,
    b3_screener=b3_screener,
    investor_relations=investor_relations,
)
us_screener = USScreeningService(settings, database, realtime_markets, one_pagers)
one_pagers.set_us_screener(us_screener)
chewie_fundamentals = ChewieFundamentalsService(settings, database, market_data.http)
r2d2 = R2D2PaperService(settings, database, realtime_markets, b3_screener, one_pagers)
leah_cloud = LeahCloudService(settings, database)
push_notifications = PushNotificationService(settings, database)
operational_incidents = OperationalIncidentService(database)
governance_vulnerability = GovernanceVulnerabilityService(
    settings,
    database,
    push_notifications=push_notifications,
)
SESSION_COOKIE = "c3po_session"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auth_required and settings.environment == "production" and len(settings.auth_secret) < 32:
        raise RuntimeError("C3PO_AUTH_SECRET must contain at least 32 characters in production")
    database.initialize()
    database.ensure_access_owner(settings.auth_email, list(ALL_VIEW_PERMISSIONS), list(ALL_CAPABILITIES))
    ensure_builtin_official_fundamentals(database)
    r2d2.ensure_initialized()
    eodhd_stream.start()
    performance_stop = asyncio.Event()
    performance_task = asyncio.create_task(
        run_performance_flush_loop(performance_observability, performance_stop)
    )
    try:
        yield
    finally:
        performance_stop.set()
        await performance_task
        eodhd_stream.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Server-Timing", "X-Response-Time-Ms"],
)

PUBLIC_AUTH_PATHS = {
    "/api/v1/auth/request-code",
    "/api/v1/auth/verify-code",
    "/api/v1/auth/session",
    "/api/v1/auth/activity",
    "/api/v1/auth/logout",
}

PERFORMANCE_TELEMETRY_ROUTES = {
    "/api/v1/telemetry/page-load",
    "/api/v1/server-usage/performance",
}


def _api_route_template(request: Request) -> str:
    route = getattr(request.scope.get("route"), "path", None)
    if isinstance(route, str) and route.startswith("/api/"):
        return route
    return "/api/{unmatched}"


@app.middleware("http")
async def measure_api_performance(request: Request, call_next):
    started_at = perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        duration_ms = (perf_counter() - started_at) * 1_000
        route = _api_route_template(request)
        if route not in PERFORMANCE_TELEMETRY_ROUTES:
            api_performance.record(request.method, route, duration_ms, response.status_code)
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


@app.middleware("http")
async def require_authenticated_session(request: Request, call_next):
    path = request.url.path
    public_auth_route = path in PUBLIC_AUTH_PATHS or path.startswith("/api/v1/leah/agent/")
    protected_api = path.startswith("/api/") and not public_auth_route
    if settings.auth_required and protected_api and request.method != "OPTIONS":
        session = auth_service.authenticate(request.cookies.get(SESSION_COOKIE))
        if not session:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
                headers={"Cache-Control": "no-store"},
            )
        request.state.auth_session = session
        owner_only_path = path.startswith("/api/v1/admin/") or path in {"/api/docs", "/api/openapi.json"}
        if owner_only_path and session["role"] != "owner":
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Owner access required"},
                headers={"Cache-Control": "no-store"},
            )
        required = required_permissions(path)
        if required and not any(permission in session["permissions"] for permission in required):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "This module is not enabled for your account"},
                headers={"Cache-Control": "no-store"},
            )
        capability = required_capability(path, request.method)
        if session["role"] != "owner" and capability:
            capabilities = session.get("capabilities", ["read"])
            if capability == "owner" or capability not in capabilities:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "This action is not enabled for your account"},
                    headers={"Cache-Control": "no-store"},
                )
    response = await call_next(request)
    if path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def request_ip(request: Request) -> str:
    cloudflare_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cloudflare_ip:
        try:
            return str(ipaddress.ip_address(cloudflare_ip))
        except ValueError:
            pass
    return request.client.host if request.client else ""


def session_client_profile(request: Request, session: dict) -> dict[str, str]:
    current_client = auth_service.describe_client(
        request.headers.get("user-agent", ""),
        platform=request.headers.get("sec-ch-ua-platform", "").strip('"'),
    )
    matched_detail: dict = {}
    session_started_at = session.get("created_at")
    for event in database.list_audit_events(action="auth.login", limit=100):
        if str(event.get("actor", "")).strip().lower() != str(session.get("email", "")).strip().lower():
            continue
        occurred_at = event.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        if session_started_at and occurred_at and abs((occurred_at - session_started_at).total_seconds()) > 120:
            continue
        matched_detail = event.get("detail") or {}
        break
    recorded_client = matched_detail.get("client_info") or {}
    return {
        "ip_address": session.get("created_ip") or matched_detail.get("requested_ip") or request_ip(request) or "Não identificado",
        "device_type": recorded_client.get("device_type") or current_client.get("device_type") or "Não identificado",
        "operating_system": recorded_client.get("os") or current_client.get("os") or "Não identificado",
        "browser": recorded_client.get("browser") or current_client.get("browser") or "Não identificado",
    }


def authenticated_session_response(request: Request, session: dict) -> AuthSessionResponse:
    client = session_client_profile(request, session)
    return AuthSessionResponse(
        authenticated=True,
        email=session["email"],
        expires_at=session.get("expires_at"),
        session_started_at=session.get("created_at"),
        last_activity_at=session.get("last_seen_at"),
        display_name=session.get("display_name"),
        role=session.get("role"),
        is_admin=session.get("role") == "owner",
        permissions=session.get("permissions", []),
        capabilities=session.get("capabilities", ["read"]),
        idle_timeout_seconds=int(session["idle_timeout_seconds"]),
        totp_enabled=auth_service.totp_enabled(session["email"]),
        **client,
    )


def deliver_login_notification(
    email: str,
    display_name: str,
    role: str,
    requested_ip: str,
    occurred_at: datetime,
    client_info: dict[str, str],
) -> None:
    try:
        auth_service.send_login_notification(
            email=email,
            display_name=display_name,
            role=role,
            requested_ip=requested_ip,
            occurred_at=occurred_at,
            client_info=client_info,
        )
    except EmailDeliveryError as exc:
        database.record_audit_event(
            email,
            "auth.login_notification_failed",
            "access_user",
            email,
            {"error": str(exc), "requested_ip": requested_ip},
        )


def current_access_actor(request: Request) -> dict:
    if not settings.auth_required:
        return database.ensure_access_owner(
            settings.auth_email,
            list(ALL_VIEW_PERMISSIONS),
            list(ALL_CAPABILITIES),
        )
    session = getattr(request.state, "auth_session", None)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return session


def require_owner(request: Request) -> dict:
    actor = current_access_actor(request)
    if actor["role"] != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return actor


@app.get("/api/v1/operational-incidents", response_model=OperationalIncidentListResponse)
def list_operational_incidents(request: Request) -> OperationalIncidentListResponse:
    current_access_actor(request)
    return OperationalIncidentListResponse(
        generated_at=datetime.now().astimezone(),
        incidents=[
            OperationalIncident(**item)
            for item in database.list_operational_incidents(limit=50)
        ],
    )


@app.post(
    "/api/v1/operational-incidents/{incident_id}/acknowledge",
    response_model=OperationalIncident,
)
def acknowledge_operational_incident(
    incident_id: str,
    request: Request,
) -> OperationalIncident:
    actor = require_owner(request)
    incident = operational_incidents.acknowledge(incident_id, actor["email"])
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return OperationalIncident(**incident)


@app.post(
    "/api/v1/operational-incidents/{incident_id}/resolve",
    response_model=OperationalIncident,
)
def resolve_operational_incident(
    incident_id: str,
    payload: OperationalIncidentResolveRequest,
    request: Request,
) -> OperationalIncident:
    actor = require_owner(request)
    incident = operational_incidents.resolve(
        incident_id,
        actor["email"],
        payload.resolution,
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return OperationalIncident(**incident)
@app.post("/api/v1/admin/governance/attest")
def run_governance_attestation(request: Request) -> dict:
    require_owner(request)
    _, report = governance_vulnerability.run_supervised(settings.legacy_root)
    return {
        "status": report["status"],
        "session_date": report["session_date"],
        "revision": report["revision"],
        "report_sha256": report["report_sha256"],
        "generated_at": report["generated_at"],
    }


def normalize_access_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email address")
    return normalized


def access_user_response(item: dict) -> AccessUser:
    return AccessUser(**item)


def access_list_response() -> AccessUserListResponse:
    return AccessUserListResponse(
        items=[access_user_response(item) for item in database.list_access_users()],
        available_permissions=[
            AccessPermission(key=key, label=label) for key, label in VIEW_PERMISSIONS.items()
        ],
        available_capabilities=[
            AccessCapability(key=key, label=label) for key, label in CAPABILITY_PERMISSIONS.items()
        ],
    )


def deliver_login_code(code: str, email: str, challenge_id: str, requested_ip: str) -> None:
    try:
        auth_service.send_code_email(code, email)
    except EmailDeliveryError:
        database.record_audit_event(
            email,
            "auth.otp_delivery_failed",
            "auth_challenge",
            challenge_id,
            {"requested_ip": requested_ip},
        )


@app.post("/api/v1/auth/request-code", response_model=LoginCodeResponse)
def request_login_code(
    payload: LoginCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> LoginCodeResponse:
    client_ip = request_ip(request)
    try:
        challenge_id, expires_in, _verification_method, delivery = auth_service.request_code(
            payload.email,
            client_ip,
            payload.delivery_method,
        )
    except RateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    if delivery:
        background_tasks.add_task(deliver_login_code, *delivery, challenge_id, client_ip)
    return LoginCodeResponse(
        challenge_id=challenge_id,
        expires_in_seconds=expires_in,
        message="Use seu código de acesso. Se o e-mail estiver autorizado, as opções configuradas estarão disponíveis.",
    )


@app.get("/api/v1/auth/totp", response_model=TotpStatusResponse)
def totp_status(request: Request) -> TotpStatusResponse:
    actor = current_access_actor(request)
    return TotpStatusResponse(enabled=auth_service.totp_enabled(actor["email"]))


@app.post("/api/v1/auth/totp/setup", response_model=TotpSetupResponse)
def setup_totp(request: Request) -> TotpSetupResponse:
    actor = current_access_actor(request)
    try:
        setup = auth_service.begin_totp_setup(actor["email"])
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    database.record_audit_event(actor["email"], "auth.totp_setup_started", "access_user", actor["email"], {})
    return TotpSetupResponse(**setup)


@app.post("/api/v1/auth/totp/reconfigure", response_model=TotpSetupResponse)
def reconfigure_totp(request: Request) -> TotpSetupResponse:
    actor = current_access_actor(request)
    try:
        setup = auth_service.begin_totp_setup(actor["email"], replace=True)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    database.record_audit_event(actor["email"], "auth.totp_reconfiguration_started", "access_user", actor["email"], {})
    return TotpSetupResponse(**setup)


@app.post("/api/v1/auth/totp/confirm", response_model=TotpStatusResponse)
def confirm_totp(payload: TotpCodeRequest, request: Request) -> TotpStatusResponse:
    actor = current_access_actor(request)
    try:
        auth_service.confirm_totp_setup(actor["email"], payload.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    database.record_audit_event(actor["email"], "auth.totp_enabled", "access_user", actor["email"], {})
    return TotpStatusResponse(enabled=True)


@app.post("/api/v1/auth/totp/disable", response_model=TotpStatusResponse)
def disable_totp(payload: TotpCodeRequest, request: Request) -> TotpStatusResponse:
    actor = current_access_actor(request)
    try:
        auth_service.disable_totp(actor["email"], payload.code)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    database.record_audit_event(actor["email"], "auth.totp_disabled", "access_user", actor["email"], {})
    return TotpStatusResponse(enabled=False)


@app.post("/api/v1/auth/verify-code", response_model=AuthSessionResponse)
def verify_login_code(
    payload: LoginVerifyRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
) -> AuthSessionResponse:
    try:
        token, expires_at, email = auth_service.verify_code(payload.challenge_id, payload.code, request_ip(request))
    except RateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    max_age = max(1, int((expires_at - auth_service.now()).total_seconds()))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max_age,
        expires=expires_at,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    access_user = database.get_access_user(email)
    login_at = auth_service.now()
    display_name = access_user["display_name"] if access_user else email
    role = access_user["role"] if access_user else "member"
    source_ip = request_ip(request)
    client_info = auth_service.describe_client(
        request.headers.get("user-agent", ""),
        platform=payload.platform or request.headers.get("sec-ch-ua-platform", "").strip('"'),
        max_touch_points=payload.max_touch_points,
    )
    database.record_audit_event(
        email,
        "auth.login",
        "access_user",
        email,
        {
            "display_name": display_name,
            "role": role,
            "requested_ip": source_ip,
            "occurred_at": login_at.isoformat(),
            "client_info": client_info,
        },
    )
    push_notifications.notify(
        category="security_login",
        title="Novo login no C3PO",
        body=f"{display_name} · {login_at.astimezone(SAO_PAULO):%H:%M}",
        deep_link="/?view=health",
        event_key=f"security-login:{email}:{login_at.isoformat()}",
    )
    background_tasks.add_task(
        deliver_login_notification,
        email,
        display_name,
        role,
        source_ip,
        login_at,
        client_info,
    )
    authenticated = auth_service.authenticate(token)
    if not authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return authenticated_session_response(request, authenticated)


@app.get("/api/v1/auth/session", response_model=AuthSessionResponse)
def auth_session(request: Request) -> AuthSessionResponse:
    if not settings.auth_required:
        owner = database.ensure_access_owner(
            settings.auth_email,
            list(ALL_VIEW_PERMISSIONS),
            list(ALL_CAPABILITIES),
        )
        return AuthSessionResponse(
            authenticated=True,
            email=owner["email"],
            display_name=owner["display_name"],
            role="owner",
            is_admin=True,
            permissions=owner["permissions"],
            capabilities=owner["capabilities"],
            idle_timeout_seconds=None,
            ip_address=request_ip(request) or "Local",
            **{
                "device_type": auth_service.describe_client(request.headers.get("user-agent", "")).get("device_type"),
                "operating_system": auth_service.describe_client(request.headers.get("user-agent", "")).get("os"),
                "browser": auth_service.describe_client(request.headers.get("user-agent", "")).get("browser"),
            },
        )
    session = auth_service.authenticate(request.cookies.get(SESSION_COOKIE))
    if not session:
        return AuthSessionResponse(authenticated=False)
    return authenticated_session_response(request, session)


@app.post("/api/v1/auth/activity", response_model=AuthSessionResponse)
def record_auth_activity(request: Request) -> AuthSessionResponse:
    session = auth_service.authenticate(request.cookies.get(SESSION_COOKIE), touch_activity=True)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return authenticated_session_response(request, session)


@app.post("/api/v1/auth/logout", response_model=AuthSessionResponse)
def logout(request: Request, response: Response) -> AuthSessionResponse:
    auth_service.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="strict")
    return AuthSessionResponse(authenticated=False)


@app.get("/api/v1/push/status", response_model=PushStatusResponse)
def push_status(request: Request) -> PushStatusResponse:
    actor = current_access_actor(request)
    return PushStatusResponse(**push_notifications.status(actor["email"]))


@app.post("/api/v1/push/subscribe", response_model=PushMutationResponse)
def subscribe_push(
    payload: PushSubscribeRequest,
    request: Request,
) -> PushMutationResponse:
    actor = current_access_actor(request)
    try:
        result = push_notifications.subscribe(
            user_email=actor["email"],
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth_key=payload.keys.auth,
            categories=list(payload.categories),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return PushMutationResponse(**result)


@app.post("/api/v1/push/unsubscribe", response_model=PushMutationResponse)
def unsubscribe_push(
    payload: PushUnsubscribeRequest,
    request: Request,
) -> PushMutationResponse:
    actor = current_access_actor(request)
    try:
        result = push_notifications.unsubscribe(
            user_email=actor["email"],
            endpoint=payload.endpoint,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return PushMutationResponse(**result)


@app.post("/api/v1/push/test", response_model=PushTestResponse)
def test_push(request: Request) -> PushTestResponse:
    actor = require_owner(request)
    return PushTestResponse(**push_notifications.send_test(actor["email"]))


@app.get("/api/v1/admin/access-users", response_model=AccessUserListResponse)
def list_access_users(request: Request) -> AccessUserListResponse:
    require_owner(request)
    return access_list_response()


@app.post("/api/v1/admin/access-users", response_model=AccessUserListResponse, status_code=201)
def create_access_user(payload: AccessUserCreateRequest, request: Request) -> AccessUserListResponse:
    actor = require_owner(request)
    email = normalize_access_email(payload.email)
    if database.get_access_user(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    permissions = normalize_permissions(payload.permissions)
    capabilities = normalize_capabilities(["read", *payload.capabilities])
    if not permissions:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select at least one module")
    user = database.upsert_access_user(
        {
            "email": email,
            "display_name": payload.display_name.strip(),
            "role": "member",
            "is_active": payload.is_active,
            "permissions": permissions,
            "capabilities": capabilities,
            "created_by": actor["email"],
        }
    )
    database.record_audit_event(
        actor["email"], "access_user.created", "access_user", email,
        {
            "is_active": user["is_active"],
            "permissions": user["permissions"],
            "capabilities": user["capabilities"],
        },
    )
    return access_list_response()


@app.put("/api/v1/admin/access-users/{email}", response_model=AccessUserListResponse)
def update_access_user(email: str, payload: AccessUserUpdateRequest, request: Request) -> AccessUserListResponse:
    actor = require_owner(request)
    normalized_email = normalize_access_email(email)
    existing = database.get_access_user(normalized_email)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access user not found")
    if existing["role"] == "owner":
        if not payload.is_active or set(payload.permissions) != set(ALL_VIEW_PERMISSIONS):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner access cannot be reduced")
        permissions = list(ALL_VIEW_PERMISSIONS)
        capabilities = list(ALL_CAPABILITIES)
    else:
        permissions = normalize_permissions(payload.permissions)
        capabilities = normalize_capabilities(["read", *payload.capabilities])
        if payload.is_active and not permissions:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select at least one module")
    user = database.upsert_access_user(
        {
            "email": normalized_email,
            "display_name": payload.display_name.strip(),
            "role": existing["role"],
            "is_active": payload.is_active,
            "permissions": permissions,
            "capabilities": capabilities,
            "created_by": existing["created_by"],
        }
    )
    if not user["is_active"]:
        database.revoke_sessions_for_email(normalized_email, auth_service.now())
    database.record_audit_event(
        actor["email"], "access_user.updated", "access_user", normalized_email,
        {
            "is_active": user["is_active"],
            "permissions": user["permissions"],
            "capabilities": user["capabilities"],
        },
    )
    return access_list_response()


@app.delete("/api/v1/admin/access-users/{email}", response_model=AccessUserListResponse)
def delete_access_user(email: str, request: Request) -> AccessUserListResponse:
    actor = require_owner(request)
    normalized_email = normalize_access_email(email)
    existing = database.get_access_user(normalized_email)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access user not found")
    if existing["role"] == "owner":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner access cannot be deleted")
    database.revoke_sessions_for_email(normalized_email, auth_service.now())
    database.delete_access_user(normalized_email)
    database.record_audit_event(
        actor["email"], "access_user.deleted", "access_user", normalized_email,
        {
            "permissions": existing["permissions"],
            "capabilities": existing["capabilities"],
        },
    )
    return access_list_response()


def leah_device_response(item: dict) -> dict:
    return {
        **item,
        "id": str(item["id"]),
    }


def leah_item_response(item: dict) -> dict:
    return {
        **item,
        "id": str(item["id"]),
        "source_device_id": str(item["source_device_id"]) if item.get("source_device_id") else None,
    }


@app.get("/api/v1/leah", response_model=LeahCloudResponse)
def get_leah_cloud(request: Request) -> LeahCloudResponse:
    actor = current_access_actor(request)
    devices = database.list_leah_devices(actor["email"])
    items = [
        item for item in database.list_leah_changes(actor["email"])
        if not item.get("deleted_at")
    ]
    return LeahCloudResponse(
        generated_at=leah_cloud.now(),
        connected=bool(devices),
        devices=[leah_device_response(item) for item in devices],
        items=[leah_item_response(item) for item in items],
    )


@app.post("/api/v1/leah/pairings", response_model=LeahPairingResponse, status_code=201)
def create_leah_pairing(request: Request) -> LeahPairingResponse:
    actor = current_access_actor(request)
    return LeahPairingResponse(**leah_cloud.create_pairing(actor["email"]))


@app.delete("/api/v1/leah/devices/{device_id}", status_code=204)
def revoke_leah_device(device_id: str, request: Request) -> Response:
    actor = current_access_actor(request)
    if not database.revoke_leah_device(actor["email"], device_id, leah_cloud.now()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispositivo não encontrado")
    return Response(status_code=204)


@app.post("/api/v1/leah/items", response_model=LeahItem, status_code=201)
def create_leah_item(payload: LeahItemWriteRequest, request: Request) -> LeahItem:
    actor = current_access_actor(request)
    item = database.upsert_leah_item(
        {
            **payload.model_dump(),
            "owner_email": actor["email"],
            "source": "c3po",
            "updated_at": leah_cloud.now(),
        }
    )
    return LeahItem(**leah_item_response(item))


@app.put("/api/v1/leah/items/{item_id}", response_model=LeahItem)
def update_leah_item(item_id: str, payload: LeahItemWriteRequest, request: Request) -> LeahItem:
    actor = current_access_actor(request)
    existing = database.get_leah_item(actor["email"], item_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")
    item = database.upsert_leah_item(
        {
            **existing,
            **payload.model_dump(),
            "id": item_id,
            "owner_email": actor["email"],
            "source": "c3po",
            "source_device_id": None,
            "updated_at": leah_cloud.now(),
        }
    )
    return LeahItem(**leah_item_response(item))


@app.delete("/api/v1/leah/items/{item_id}", status_code=204)
def delete_leah_item(item_id: str, request: Request) -> Response:
    actor = current_access_actor(request)
    if not database.delete_leah_item(actor["email"], item_id, leah_cloud.now()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")
    return Response(status_code=204)


@app.post("/api/v1/leah/agent/pair", response_model=LeahAgentPairResponse)
def pair_leah_agent(payload: LeahAgentPairRequest) -> LeahAgentPairResponse:
    try:
        paired = leah_cloud.pair_device(payload.code, payload.name, payload.platform)
    except LeahAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return LeahAgentPairResponse(
        token=paired["token"],
        device=leah_device_response(paired["device"]),
    )


@app.post("/api/v1/leah/agent/sync", response_model=LeahAgentSyncResponse)
def sync_leah_agent(payload: LeahAgentSyncRequest, request: Request) -> LeahAgentSyncResponse:
    try:
        device = leah_cloud.authenticate_device(request.headers.get("authorization"))
    except LeahAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    result = leah_cloud.sync(device, payload.model_dump())
    return LeahAgentSyncResponse(
        cursor=result["cursor"],
        items=[leah_item_response(item) for item in result["items"]],
    )


@app.get("/api/v1/health")
def health() -> dict:
    report = legacy.latest_report()
    return {
        "status": "ok",
        "service": "c3po-api",
        "environment": settings.environment,
        "database": "configured" if settings.database_url else "local-fallback",
        "legacy_report": report.name if report else None,
        "time": datetime.now().astimezone().isoformat(),
    }


@app.get("/api/v1/system-health", response_model=SystemHealthResponse)
def consolidated_system_health() -> SystemHealthResponse:
    return system_health.snapshot()


@app.get("/api/v1/server-usage", response_model=ServerUsageResponse)
def server_usage_snapshot(hours: int = Query(default=24, ge=1, le=168)) -> ServerUsageResponse:
    return server_usage.snapshot(hours=hours)


@app.get("/api/v1/code-census")
def code_census_snapshot(days: int | None = Query(default=None, ge=2, le=365)) -> dict:
    return code_census.snapshot(days=days)


@app.get("/api/v1/server-usage/performance", response_model=PerformanceHistoryResponse)
def performance_history(
    hours: int = Query(default=168, ge=1, le=2_160),
) -> PerformanceHistoryResponse:
    return PerformanceHistoryResponse.model_validate(performance_observability.history(hours=hours))


@app.post(
    "/api/v1/telemetry/page-load",
    response_model=PageLoadPerformanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def capture_page_load_performance(
    payload: PageLoadPerformanceRequest,
) -> PageLoadPerformanceResponse:
    accepted = performance_observability.capture_page_load(payload.model_dump(mode="python"))
    return PageLoadPerformanceResponse(
        sample_id=payload.sample_id,
        accepted=accepted,
        flush_seconds=settings.performance_flush_seconds,
    )


@app.get("/api/v1/weather", response_model=WeatherResponse)
def weather_snapshot(search: str | None = Query(default=None, max_length=100)) -> WeatherResponse:
    try:
        return weather.snapshot(search=search)
    except WeatherLocationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WeatherRequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/news", response_model=NewsResponse)
def news_snapshot(response: Response, refresh: bool = Query(default=False)) -> NewsResponse:
    response.headers["Cache-Control"] = "no-store"
    return news.snapshot(refresh=refresh)


@app.get("/api/v1/open-finance", response_model=OpenFinanceResponse)
def open_finance_snapshot(
    hours: int = Query(default=36, ge=1, le=168),
    refresh: bool = Query(default=True),
) -> OpenFinanceResponse:
    try:
        return open_finance.snapshot(hours=hours, refresh=refresh)
    except PluggyRequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/command-center", response_model=CommandCenterResponse)
def command_center() -> CommandCenterResponse:
    snapshot = legacy.read()
    generated_at = snapshot["generated_at"]
    age_hours = max(0, (datetime.now().astimezone() - generated_at).total_seconds() / 3600)
    status = "fresh" if age_hours <= 16 else "stale"
    quality = 95 if status == "fresh" else 72
    greeting, report_title, report_date = _current_summary_context()
    snapshot["report_title"] = report_title
    snapshot["report_date"] = report_date

    return CommandCenterResponse(
        **snapshot,
        greeting=greeting,
        provenance=Provenance(
            source="Legacy Summary Adapter",
            as_of=generated_at,
            collected_at=datetime.now().astimezone(),
            quality=quality,
            status=status,
        ),
    )


def build_alert_feed(email: str) -> dict:
    snapshot = legacy.read()
    generated_at = snapshot["generated_at"]
    age_hours = max(0, (datetime.now().astimezone() - generated_at).total_seconds() / 3600)
    login_alerts: list[dict] = []
    for event in database.list_audit_events(action="auth.login", limit=50):
        detail = event.get("detail") or {}
        occurred_at = event["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)
        local_time = occurred_at.astimezone(ZoneInfo("America/Sao_Paulo"))
        identity = detail.get("display_name") or event["actor"]
        role_label = "proprietário" if detail.get("role") == "owner" else "usuário autorizado"
        client_info = detail.get("client_info") or {}
        device_summary = " · ".join(
            part for part in (
                client_info.get("device_type"),
                client_info.get("os"),
                client_info.get("browser"),
            ) if part
        )
        login_alerts.append(
            {
                "id": f"auth-login:{event['id']}",
                "subject": f"Login confirmado · {identity}",
                "context": event["actor"],
                "action": f"{role_label.capitalize()} entrou em {local_time.strftime('%d/%m/%Y às %H:%M:%S')}. {device_summary + '. ' if device_summary else ''}IP {detail.get('requested_ip') or 'não identificado'}.",
                "severity": "Security",
                "occurred_at": occurred_at,
                "source": "C3PO Access Control",
                "metadata": {
                    "Usuário": event["actor"],
                    "Perfil": role_label.capitalize(),
                    "Dispositivo": client_info.get("device_type") or "Não identificado",
                    "Sistema": client_info.get("os") or "Não identificado",
                    "Navegador": client_info.get("browser") or "Não identificado",
                    "Endereço IP": detail.get("requested_ip") or "Não identificado",
                },
            }
        )
    decision_alerts: list[dict] = []
    generated_key = generated_at.isoformat() if hasattr(generated_at, "isoformat") else str(generated_at)
    for index, item in enumerate(snapshot["decision_queue"]):
        fingerprint = "|".join(
            (generated_key, str(index), item.get("subject", ""), item.get("context", ""), item.get("action", ""))
        )
        decision_alerts.append(
            {
                "id": f"decision:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]}",
                "subject": item.get("subject", "Alerta para revisão"),
                "context": item.get("context", ""),
                "action": item.get("action", "Revisar e definir o próximo passo."),
                "severity": item.get("severity", "Review"),
                "occurred_at": generated_at,
                "source": "Legacy Summary Adapter",
                "metadata": {
                    "Origem": "Fila de decisões do Summary",
                    "Posição na fila": str(index + 1),
                },
            }
        )
    cash_yield_alerts: list[dict] = []
    cash_yield_actions = {
        "r2d2.cash_yield.failed": {
            "subject": "Cash Yield não processado",
            "severity": "Critical",
            "action": "A apropriação pré-abertura falhou. O servidor tentará novamente a cada 30 minutos até 10:00 BRT.",
        },
        "r2d2.cash_yield.recovered": {
            "subject": "Cash Yield recuperado",
            "severity": "Operational",
            "action": "A apropriação foi concluída por um retry automático; confira o NAV contábil atualizado.",
        },
    }
    for event_action, presentation in cash_yield_actions.items():
        for event in database.list_audit_events(action=event_action, limit=50):
            detail = event.get("detail") or {}
            cash_yield_alerts.append({
                "id": f"cash-yield:{event['id']}",
                "subject": f"{presentation['subject']} · {event['subject_id']}",
                "context": "R2D2 · accrual sintético de caixa às 06:00 BRT",
                "action": presentation["action"],
                "severity": presentation["severity"],
                "occurred_at": event["occurred_at"],
                "source": "R2D2 Accounting Controls",
                "metadata": {
                    "Sessão": event["subject_id"],
                    "Agendado para": detail.get("scheduled_for") or "N/D",
                    "Erro": detail.get("error") or "Nenhum; processamento recuperado",
                },
            })
    capacity_alerts = server_usage.capacity_alerts()
    items = capacity_alerts + login_alerts + decision_alerts + cash_yield_alerts
    items.sort(key=lambda item: item["occurred_at"], reverse=True)
    read_ids = database.alert_read_ids(email, [item["id"] for item in items])
    for item in items:
        item["is_read"] = item["id"] in read_ids
    return {
        "generated_at": generated_at,
        "status": "fresh" if age_hours <= 16 else "stale",
        "unread_count": sum(1 for item in items if not item["is_read"]),
        "items": items,
    }


@app.get("/api/v1/alerts")
def alerts(request: Request) -> dict:
    actor = current_access_actor(request)
    return build_alert_feed(actor["email"])


@app.post("/api/v1/alerts/read", response_model=AlertReadResponse)
def mark_alerts_read(payload: AlertReadRequest, request: Request) -> AlertReadResponse:
    actor = current_access_actor(request)
    read_at = datetime.now().astimezone()
    marked = database.mark_alerts_read(actor["email"], payload.alert_ids, read_at)
    return AlertReadResponse(marked_read=marked, read_at=read_at)


@app.get("/api/v1/navigation-indicators", response_model=NavigationIndicatorsResponse)
def navigation_indicators(request: Request) -> NavigationIndicatorsResponse:
    actor = current_access_actor(request)
    permissions = set(actor.get("permissions") or [])
    feed_keys = [key for key in ("relations", "intelligence") if key in permissions]
    seen_by_feed = database.navigation_feed_seen_at(actor["email"], feed_keys)
    generated_at = datetime.now().astimezone()
    feeds: dict[str, NavigationIndicator] = {}
    for feed_key in feed_keys:
        latest_at, _ = database.navigation_feed_activity(feed_key)
        last_seen_at = seen_by_feed.get(feed_key)
        if last_seen_at is None:
            last_seen_at = latest_at or generated_at
            database.mark_navigation_feed_seen(actor["email"], feed_key, last_seen_at)
        _, unseen_count = database.navigation_feed_activity(feed_key, after=last_seen_at)
        feeds[feed_key] = NavigationIndicator(
            has_new=unseen_count > 0,
            unseen_count=unseen_count,
            latest_at=latest_at,
            last_seen_at=last_seen_at,
        )
    return NavigationIndicatorsResponse(generated_at=generated_at, feeds=feeds)


@app.post("/api/v1/navigation-seen", response_model=NavigationSeenResponse)
def mark_navigation_seen(payload: NavigationSeenRequest, request: Request) -> NavigationSeenResponse:
    actor = current_access_actor(request)
    if payload.view not in set(actor.get("permissions") or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This module is not enabled for your account",
        )
    latest_at, _ = database.navigation_feed_activity(payload.view)
    requested_seen_at = datetime.now().astimezone()
    if latest_at and latest_at > requested_seen_at:
        requested_seen_at = latest_at
    seen_at = database.mark_navigation_feed_seen(
        actor["email"],
        payload.view,
        requested_seen_at,
    )
    return NavigationSeenResponse(view=payload.view, seen_at=seen_at)


@app.get("/api/v1/reports")
def reports() -> dict:
    return {"items": legacy.report_history()}


@app.get("/api/v1/search")
def global_search(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
) -> dict:
    actor = current_access_actor(request)
    permissions = set(actor.get("permissions") or [])
    clean_query = q.strip()
    normalized_query = clean_query.casefold()
    ticker_query = re.sub(r"[^A-Z0-9.]", "", clean_query.upper())

    companies: list[dict] = []
    company_modules = {"onepager", "intelligence", "relations", "candidates", "matrix", "realtime"}
    if permissions & company_modules:
        ranked_companies: list[tuple[int, str, dict]] = []
        for company in database.list_ir_companies():
            symbols = [str(symbol).upper() for symbol in company.get("symbols") or []]
            company_name = str(company.get("company_name") or "")
            exact_symbol = next((symbol for symbol in symbols if symbol == ticker_query), None)
            prefix_symbol = next((symbol for symbol in symbols if symbol.startswith(ticker_query)), None) if ticker_query else None
            name_matches = normalized_query in company_name.casefold()
            if not exact_symbol and not prefix_symbol and not name_matches:
                continue
            selected_symbol = exact_symbol or prefix_symbol or (symbols[0] if symbols else "")
            if not selected_symbol:
                continue
            score = 0 if exact_symbol else 1 if prefix_symbol else 2 if company_name.casefold().startswith(normalized_query) else 3
            ranked_companies.append((score, selected_symbol, {
                "symbol": selected_symbol,
                "symbols": symbols,
                "company_name": company_name,
                "market": company.get("market") or "B3",
                "exchange": company.get("exchange"),
                "ri_url": company.get("ri_url"),
            }))
        ranked_companies.sort(key=lambda item: (item[0], item[1]))
        companies = [item[2] for item in ranked_companies[:8]]

    valuations: list[dict] = []
    if "intelligence" in permissions:
        _, valuation_rows = database.list_valuation_changes(limit=12, symbol=clean_query)
        seen_symbols: set[tuple[str, str]] = set()
        for item in valuation_rows:
            key = (str(item.get("market") or ""), str(item.get("symbol") or ""))
            if key in seen_symbols:
                continue
            seen_symbols.add(key)
            valuations.append({
                "id": item.get("id"),
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "market": item.get("market"),
                "trigger_title": item.get("trigger_title"),
                "changed_at": item.get("changed_at"),
                "currency": item.get("currency"),
                "old_tp": item.get("old_tp"),
                "new_tp": item.get("new_tp"),
            })
            if len(valuations) >= 6:
                break

    documents: list[dict] = []
    if "relations" in permissions:
        for item in database.list_ir_events(limit=6, query=clean_query, monitored_only=False):
            documents.append({
                "id": item.get("id"),
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "market": item.get("market"),
                "source": item.get("source_code"),
                "event_type": item.get("event_type"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "official_url": item.get("official_url"),
            })

    return {
        "generated_at": datetime.now().astimezone(),
        "query": clean_query,
        "companies": companies,
        "valuations": valuations,
        "documents": documents,
    }


@app.get("/api/v1/valuation-records", response_model=ValuationChangeResponse)
def valuation_records(
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=100),
    market: str | None = Query(default=None, pattern=r"^(B3|NASDAQ|NYSE|US)$"),
    trigger_type: str | None = Query(
        default=None,
        pattern=r"^(initial|financial_results|material_event|web_research|market_data|methodology)$",
    ),
) -> ValuationChangeResponse:
    total, items = database.list_valuation_changes(
        limit=limit,
        offset=offset,
        symbol=q,
        market=market,
        trigger_type=trigger_type,
    )
    return ValuationChangeResponse(
        generated_at=datetime.now().astimezone(),
        total=total,
        item_count=len(items),
        items=items,
    )


@app.get("/api/v1/one-pagers", response_model=OnePagerListResponse)
def one_pager_history() -> OnePagerListResponse:
    return OnePagerListResponse(items=one_pagers.list_reports())


@app.post("/api/v1/one-pagers", response_model=OnePagerReport, status_code=201)
def generate_one_pager(payload: OnePagerRequest) -> OnePagerReport:
    try:
        return one_pagers.generate(payload.symbol)
    except OnePagerGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@app.get("/api/v1/one-pagers/{filename}", response_class=FileResponse)
def download_one_pager(filename: str) -> FileResponse:
    path = one_pagers.report_path(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One Pager not found")
    return FileResponse(path, media_type="application/pdf", filename=filename, content_disposition_type="inline")


@app.get("/api/v1/integrations")
def integrations() -> dict:
    snapshot = legacy.read()
    items = [*snapshot["integrations"], *open_finance.integration_health()]
    return {"items": [item.model_dump() for item in items]}


@app.get("/api/v1/investor-relations", response_model=InvestorRelationsResponse)
def investor_relations_feed(
    limit: int = Query(default=100, ge=1, le=300),
    market: str | None = Query(default=None, pattern=r"^(B3|US)$"),
    source: str | None = Query(default=None, pattern=r"^(cvm|sec|ri|finnhub)$"),
    event_type: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=120),
    scope: str = Query(default="coverage", pattern=r"^(coverage|all)$"),
) -> InvestorRelationsResponse:
    return investor_relations.feed(
        limit=limit, market=market, source=source, event_type=event_type, query=q,
        monitored_only=scope == "coverage",
    )


@app.post("/api/v1/investor-relations/sync", response_model=InvestorRelationsSyncResponse)
def sync_investor_relations(
    source: str = Query(default="all", pattern=r"^(all|cvm|sec|ri|finnhub)$"),
) -> InvestorRelationsSyncResponse:
    response = investor_relations.sync(source)
    ir_valuation_processor.process()
    return response


@app.post("/api/v1/investor-relations/watchlist", response_model=InvestorRelationsResponse, status_code=201)
def add_investor_relations_watch(payload: InvestorRelationsWatchRequest) -> InvestorRelationsResponse:
    investor_relations.add_watch(payload.symbol, payload.market, payload.company_name, payload.ri_url)
    return investor_relations.feed(limit=100)


@app.post("/api/v1/investor-relations/events/{event_id}/review", response_model=InvestorRelationsResponse)
def review_investor_relations_event(event_id: str, payload: InvestorRelationsReviewRequest) -> InvestorRelationsResponse:
    if not database.review_ir_event(event_id, payload.note):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investor Relations event not found")
    ir_valuation_processor.process()
    return investor_relations.feed(limit=100)


@app.get("/api/v1/investor-relations/report.pdf", response_class=FileResponse)
def investor_relations_report(
    market: str | None = Query(default=None, pattern=r"^(B3|US)$"),
    source: str | None = Query(default=None, pattern=r"^(cvm|sec|ri|finnhub)$"),
    event_type: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=120),
    scope: str = Query(default="coverage", pattern=r"^(coverage|all)$"),
) -> FileResponse:
    path = investor_relations.report(
        market=market, source=source, event_type=event_type, query=q,
        monitored_only=scope == "coverage",
    )
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@app.get("/api/v1/market-data/providers", response_model=list[MarketDataProviderHealth])
def market_data_providers() -> list[MarketDataProviderHealth]:
    return market_data.health()


@app.get("/api/v1/markets/live", response_model=LiveMarketsResponse)
def live_market_snapshot() -> LiveMarketsResponse:
    return live_markets.snapshot()


@app.get("/api/v1/markets/live/index", response_model=LiveMarketIndexResponse)
def live_market_index_snapshot() -> LiveMarketIndexResponse:
    return live_markets.index_snapshot()


@app.get("/api/v1/market-data/intraday", response_model=InstrumentIntradayResponse)
def instrument_intraday(
    symbol: str = Query(min_length=1, max_length=40),
    market: str | None = Query(default=None, max_length=20),
    name: str | None = Query(default=None, max_length=160),
    session_date: date | None = Query(default=None),
) -> InstrumentIntradayResponse:
    try:
        return realtime_markets.instrument_intraday(
            symbol,
            market=market,
            name=name,
            requested_session_date=session_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/realtime/{market}", response_model=RealtimeMarketResponse)
def realtime_market_snapshot(market: str) -> RealtimeMarketResponse:
    try:
        return realtime_markets.snapshot(market)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/realtime/portfolio/items", response_model=RealtimePortfolioResponse)
def realtime_portfolio() -> RealtimePortfolioResponse:
    return realtime_markets.portfolio_snapshot()


@app.get("/api/v1/realtime/portfolio/search", response_model=RealtimePortfolioSymbolSearchResponse)
def search_realtime_portfolio_symbols(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=8, ge=1, le=12),
) -> RealtimePortfolioSymbolSearchResponse:
    try:
        return realtime_markets.search_portfolio_symbols(q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@app.get(
    "/api/v1/realtime/portfolio/items/{symbol}/intraday",
    response_model=RealtimePortfolioIntradayResponse,
)
def realtime_portfolio_intraday(symbol: str) -> RealtimePortfolioIntradayResponse:
    try:
        return realtime_markets.portfolio_intraday(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/api/v1/realtime/portfolio/items", response_model=RealtimePortfolioResponse, status_code=201)
def add_realtime_portfolio(payload: RealtimePortfolioRequest) -> RealtimePortfolioResponse:
    try:
        return realtime_markets.add_portfolio_symbol(payload.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.delete("/api/v1/realtime/portfolio/items/{symbol}", response_model=RealtimePortfolioResponse)
def delete_realtime_portfolio(symbol: str) -> RealtimePortfolioResponse:
    try:
        return realtime_markets.delete_portfolio_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@app.get("/api/v1/market-data/quotes", response_model=MarketDataQuoteResponse)
def market_data_quotes(
    provider: str = Query(pattern=r"^(brapi|eodhd)$"),
    symbols: str = Query(min_length=1, max_length=300),
) -> MarketDataQuoteResponse:
    requested = [symbol for symbol in symbols.split(",") if symbol.strip()]
    try:
        quotes = market_data.fetch_quotes(provider, requested, persist=False)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return MarketDataQuoteResponse(items=quotes)


@app.post("/api/v1/market-data/sync", response_model=MarketDataQuoteResponse)
def market_data_sync(payload: MarketDataSyncRequest) -> MarketDataQuoteResponse:
    try:
        quotes = market_data.fetch_quotes(payload.provider, payload.symbols, persist=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return MarketDataQuoteResponse(items=quotes)


@app.get("/api/v1/candidates/b3", response_model=B3CandidateResponse)
def b3_candidates(refresh: bool = Query(default=False)) -> B3CandidateResponse:
    try:
        # Full screening is intentionally restricted to the midnight worker.
        # The UI refresh flag only reloads the latest persisted basis.
        return b3_screener.screen(refresh=False)
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/candidates/nasdaq", response_model=B3CandidateResponse)
def nasdaq_candidates(refresh: bool = Query(default=False)) -> B3CandidateResponse:
    try:
        return us_screener.screen("NASDAQ", refresh=False)
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/candidates/nyse", response_model=B3CandidateResponse)
def nyse_candidates(refresh: bool = Query(default=False)) -> B3CandidateResponse:
    try:
        return us_screener.screen("NYSE", refresh=False)
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/matrix-power/b3", response_model=MatrixPowerResponse)
def matrix_power_b3() -> MatrixPowerResponse:
    try:
        return b3_screener.matrix()
    except MarketDataRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/matrix-power/nasdaq", response_model=MatrixPowerResponse)
def matrix_power_nasdaq() -> MatrixPowerResponse:
    try:
        return us_screener.matrix("NASDAQ")
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/api/v1/matrix-power/nyse", response_model=MatrixPowerResponse)
def matrix_power_nyse() -> MatrixPowerResponse:
    try:
        return us_screener.matrix("NYSE")
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _chewie_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in {"B3", "NASDAQ", "NYSE"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown market")
    return normalized


@app.get("/api/v1/chewie-fundamentals/{market}", response_model=ChewieFundamentalsResponse)
def chewie_fundamentals_view(market: str) -> ChewieFundamentalsResponse:
    normalized = _chewie_market(market)
    try:
        payload = chewie_fundamentals.rows(normalized)  # type: ignore[arg-type]
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return ChewieFundamentalsResponse(**payload)


@app.get("/api/v1/chewie-fundamentals/{market}/search", response_model=ChewieSearchResponse)
def chewie_fundamentals_search(market: str, q: str = Query(min_length=1, max_length=40)) -> ChewieSearchResponse:
    normalized = _chewie_market(market)
    try:
        payload = chewie_fundamentals.search(normalized, q)  # type: ignore[arg-type]
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return ChewieSearchResponse(**payload)


@app.get("/api/v1/chewie-fundamentals/{market}/{symbol}/report.pdf", response_class=FileResponse)
def chewie_fundamentals_report(market: str, symbol: str) -> FileResponse:
    normalized = _chewie_market(market)
    try:
        path = chewie_fundamentals.render_report(normalized, symbol)  # type: ignore[arg-type]
    except (MarketDataRequestError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Símbolo não encontrado na fonte de fundamentos")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.get("/api/v1/r2d2", response_model=R2D2DashboardResponse)
def r2d2_dashboard() -> R2D2DashboardResponse:
    return r2d2.dashboard()


@app.get("/api/v1/r2d2/live-positions", response_model=R2D2LivePositionsResponse)
def r2d2_live_positions() -> R2D2LivePositionsResponse:
    return r2d2.live_positions()


@app.post("/api/v1/feedback", response_model=FeedbackResponse, status_code=201)
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    feedback_id = str(uuid4())
    database.save_feedback(
        {
            "id": feedback_id,
            "subject_type": request.subject_type,
            "subject_id": request.subject_id,
            "rating": request.rating,
            "comment": request.comment,
            "context": request.context,
            "created_at": datetime.now().astimezone().isoformat(),
        }
    )
    return FeedbackResponse(id=feedback_id)
