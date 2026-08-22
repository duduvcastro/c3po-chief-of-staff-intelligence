from __future__ import annotations


VIEW_PERMISSIONS: dict[str, str] = {
    "command": "Millennium Falcon",
    "markets": "Markets",
    "realtime": "Hyperspace",
    "weather": "Dagobah Weather",
    "relations": "Tatooine Updates",
    "news": "Rebellion News",
    "r2d2": "R2D2 Rising",
    "candidates": "Candidate Stocks",
    "matrix": "Dark Side",
    "onepager": "One Pager",
    "intelligence": "I.Q. Records",
    "finance": "Midi-Chlorians Finance",
    "alerts": "Radar Alerts",
    "health": "Storm Troops",
    "serverusage": "Server Usage",
    "leah": "Leah Cloud",
}

ALL_VIEW_PERMISSIONS = tuple(VIEW_PERMISSIONS)

CAPABILITY_PERMISSIONS: dict[str, str] = {
    "read": "Somente leitura",
    "onepager_generate": "Gerar One Pagers",
    "delete": "Excluir dados",
}

ALL_CAPABILITIES = tuple(CAPABILITY_PERMISSIONS)


def normalize_permissions(values: list[str] | tuple[str, ...] | None) -> list[str]:
    requested = set(values or [])
    return [permission for permission in ALL_VIEW_PERMISSIONS if permission in requested]


def normalize_capabilities(values: list[str] | tuple[str, ...] | None) -> list[str]:
    requested = set(values or [])
    return [capability for capability in ALL_CAPABILITIES if capability in requested]


def required_capability(path: str, method: str) -> str | None:
    normalized_method = method.upper()
    if path.startswith("/api/v1/auth/totp"):
        return "read"
    if path.startswith("/api/v1/leah/"):
        return "read"
    if normalized_method in {"GET", "HEAD"}:
        return "read"
    if normalized_method == "POST" and path in {"/api/v1/alerts/read", "/api/v1/navigation-seen"}:
        return "read"
    if normalized_method == "POST" and path == "/api/v1/one-pagers":
        return "onepager_generate"
    if normalized_method == "DELETE":
        return "delete"
    if normalized_method in {"POST", "PUT", "PATCH"}:
        return "owner"
    return None


def required_permissions(path: str) -> tuple[str, ...]:
    mappings: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("/api/v1/server-usage", ("serverusage",)),
        ("/api/v1/leah", ("leah",)),
        ("/api/v1/weather", ("weather",)),
        ("/api/v1/news", ("news",)),
        ("/api/v1/open-finance", ("finance",)),
        ("/api/v1/command-center", ("command",)),
        ("/api/v1/alerts", ("alerts",)),
        ("/api/v1/navigation", ("relations", "intelligence")),
        ("/api/v1/reports", ("command", "candidates")),
        ("/api/v1/valuation-records", ("intelligence",)),
        ("/api/v1/one-pagers", ("onepager",)),
        ("/api/v1/integrations", ("health",)),
        ("/api/v1/investor-relations", ("relations",)),
        ("/api/v1/markets/live", ("markets",)),
        ("/api/v1/realtime", ("realtime",)),
        ("/api/v1/r2d2", ("r2d2",)),
        ("/api/v1/market-data/providers", ("markets", "realtime", "candidates", "health")),
        ("/api/v1/market-data/quotes", ("markets", "realtime", "candidates", "matrix", "onepager")),
        ("/api/v1/market-data/sync", ("markets", "realtime", "candidates", "matrix", "onepager")),
        ("/api/v1/candidates", ("candidates",)),
        ("/api/v1/matrix-power", ("matrix",)),
    )
    for prefix, permissions in mappings:
        if path.startswith(prefix):
            return permissions
    return ()
