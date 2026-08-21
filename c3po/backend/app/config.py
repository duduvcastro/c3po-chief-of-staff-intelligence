from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_paths() -> tuple[Path, Path, Path]:
    backend_root = Path(__file__).resolve().parent.parent
    if backend_root.name == "backend":
        project_root = backend_root.parent
        return project_root.parent, project_root / "db", project_root / "data" / "one-pagers"
    return Path("/legacy"), Path("/app/db"), Path("/app/generated-one-pagers")


DEFAULT_LEGACY_ROOT, DEFAULT_MIGRATIONS_DIR, DEFAULT_ONE_PAGER_OUTPUT_DIR = _default_paths()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="C3PO_", extra="ignore", populate_by_name=True)

    app_name: str = "C3PO | Chief of Staff Intelligence"
    environment: str = "development"
    database_url: str = ""
    legacy_root: Path = DEFAULT_LEGACY_ROOT
    migrations_dir: Path = DEFAULT_MIGRATIONS_DIR
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081,http://127.0.0.1:8081"
    auth_required: bool = False
    auth_email: str = "eu@eduardocastro.com.br"
    auth_secret: str = "development-only-change-me"
    auth_code_minutes: int = 10
    auth_session_hours: int = 24
    auth_owner_session_hours: int = 24
    auth_member_idle_minutes: int = 60
    auth_cookie_secure: bool = True
    public_url: str = "https://c3po.eduardocastro.com.br"
    system_health_external_timeout_seconds: float = 6.0
    github_api_url: str = "https://api.github.com"
    github_repository: str = "duduvcastro/c3po-chief-of-staff-intelligence"
    deploy_version_file: Path = DEFAULT_LEGACY_ROOT / ".deploy-version"
    exchange_server: str = Field(default="", validation_alias=AliasChoices("C3PO_EXCHANGE_SERVER", "EXCHANGE_SERVER"))
    exchange_user: str = Field(default="", validation_alias=AliasChoices("C3PO_EXCHANGE_USER", "EXCHANGE_USER"))
    exchange_app_password: str = Field(default="", validation_alias=AliasChoices("C3PO_EXCHANGE_APP_PASSWORD", "EXCHANGE_APP_PASSWORD"))
    notification_exchange_server: str = Field(
        default="",
        validation_alias=AliasChoices("C3PO_NOTIFICATION_EXCHANGE_SERVER", "NOTIFICATION_EXCHANGE_SERVER"),
    )
    notification_exchange_user: str = Field(
        default="",
        validation_alias=AliasChoices("C3PO_NOTIFICATION_EXCHANGE_USER", "NOTIFICATION_EXCHANGE_USER"),
    )
    notification_exchange_app_password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "C3PO_NOTIFICATION_EXCHANGE_APP_PASSWORD",
            "NOTIFICATION_EXCHANGE_APP_PASSWORD",
        ),
    )
    pluggy_base_url: str = Field(default="https://api.pluggy.ai", validation_alias=AliasChoices("C3PO_PLUGGY_BASE_URL", "PLUGGY_BASE_URL"))
    pluggy_client_id: str = Field(default="", validation_alias=AliasChoices("C3PO_PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_ID"))
    pluggy_client_secret: str = Field(default="", validation_alias=AliasChoices("C3PO_PLUGGY_CLIENT_SECRET", "PLUGGY_CLIENT_SECRET"))
    pluggy_item_ids: str = Field(default="", validation_alias=AliasChoices("C3PO_PLUGGY_ITEM_IDS", "PLUGGY_ITEM_IDS"))
    pluggy_timeout_seconds: float = 18.0
    pluggy_refresh_minimum_minutes: int = 55
    brapi_token: str = Field(default="", validation_alias=AliasChoices("C3PO_BRAPI_TOKEN", "BRAPI_TOKEN"))
    brapi_base_url: str = "https://brapi.dev"
    brapi_plan: str = "unconfigured"
    eodhd_api_token: str = Field(default="", validation_alias=AliasChoices("C3PO_EODHD_API_TOKEN", "EODHD_API_TOKEN"))
    eodhd_base_url: str = "https://eodhd.com"
    eodhd_plan: str = "unconfigured"
    finnhub_api_token: str = Field(default="", validation_alias=AliasChoices("C3PO_FINNHUB_API_TOKEN", "FINNHUB_API_TOKEN"))
    finnhub_base_url: str = "https://finnhub.io"
    fmp_api_token: str = Field(default="", validation_alias=AliasChoices("C3PO_FMP_API_TOKEN", "FMP_API_TOKEN"))
    fmp_base_url: str = "https://financialmodelingprep.com"
    fmp_plan: str = "unconfigured"
    openai_admin_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("C3PO_OPENAI_ADMIN_API_KEY", "OPENAI_ADMIN_KEY"),
    )
    openai_usage_project_ids: str = ""
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("C3PO_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_admin_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("C3PO_ANTHROPIC_ADMIN_API_KEY", "ANTHROPIC_ADMIN_KEY"),
    )
    anthropic_usage_workspace_ids: str = ""
    market_data_timeout_seconds: float = 15.0
    market_data_max_retries: int = 2
    one_pager_output_dir: Path = DEFAULT_ONE_PAGER_OUTPUT_DIR
    investor_relations_output_dir: Path = DEFAULT_ONE_PAGER_OUTPUT_DIR.parent / "investor-relations"
    cvm_data_base_url: str = "https://dados.cvm.gov.br/dados"
    sec_data_base_url: str = "https://data.sec.gov"
    sec_archives_base_url: str = "https://www.sec.gov"
    sec_fulltext_base_url: str = "https://efts.sec.gov"
    sec_user_agent: str = "C3PO Chief of Staff Intelligence eu@eduardocastro.com.br"
    investor_relations_poll_minutes: int = 15
    investor_relations_cvm_poll_minutes: int = 120
    investor_relations_ri_poll_minutes: int = 60
    investor_relations_sec_watchlist: str = "AMZN,MSFT,META,AVGO,TTWO,VOO,MHVYF"
    server_usage_server_id: str = "lightsail-sa-east-1"
    server_usage_server_name: str = "Chief of Staff Intelligence"
    server_usage_region: str = "São Paulo · sa-east-1"
    server_usage_cpu_count: int = 2
    server_usage_proc_stat_path: Path = Path("/proc/stat")
    server_usage_disk_path: Path = Path("/")
    server_usage_interval_seconds: int = 60
    server_usage_retention_days: int = 7
    server_usage_cpu_peak_warning_percent: float = 85.0
    server_usage_cpu_peak_critical_percent: float = 95.0
    server_usage_cpu_average_warning_percent: float = 70.0
    server_usage_cpu_average_critical_percent: float = 85.0
    server_usage_disk_warning_percent: float = 70.0
    server_usage_disk_critical_percent: float = 85.0
    r2d2_experiment_code: str = "R2D2-90D-001"
    r2d2_start_date: str = "2026-08-17"
    r2d2_checkpoint_days: int = Field(
        default=90,
        validation_alias=AliasChoices("C3PO_R2D2_CHECKPOINT_DAYS", "C3PO_R2D2_DURATION_DAYS"),
    )
    r2d2_starting_capital_usd: float = 1_000_000.0
    r2d2_cycle_seconds: int = 60
    r2d2_risk_monitor_enabled: bool = False
    r2d2_risk_monitor_interval_seconds: float = 3.0
    r2d2_max_positions: int = 20
    # Dudu, 2026-08-20: while still in the test phase, widened from 6.0/1.5 so
    # a normal day's volatility doesn't halt trading (losing trading hours
    # entirely) before enough real trades accumulate to learn from. Position
    # sizing still decides the actual allocation within [2%, 5%] per trade.
    r2d2_max_position_percent: float = 5.0
    r2d2_max_market_percent: float = 48.0
    r2d2_max_cash_percent: float = 25.0
    r2d2_min_cash_buffer_percent: float = 5.0
    r2d2_max_gross_exposure_percent: float = 95.0
    r2d2_daily_loss_limit_percent: float = 2.0
    r2d2_soft_loss_exit_percent: float = 0.25
    r2d2_max_position_loss_percent: float = 0.65
    r2d2_live_quote_max_age_seconds: int = 90
    r2d2_delayed_quote_protection_grace_minutes: float = 3.0
    r2d2_delayed_quote_fallback_max_age_minutes: float = 30.0
    r2d2_trade_cooldown_minutes: int = 8
    # Root-caused 2026-08-20: this default (not an env override) is what the
    # worker falls back to whenever a deploy doesn't carry forward a manual
    # production tweak -- it silently reverted from a 200 override earlier
    # today, hit the cap at 131 orders by mid-afternoon, and starved the rest
    # of the session of any new BUYs. Raised the versioned default itself so
    # this can't regress again. Risk per trade is now normalized (V20:
    # RISK_BUDGET_PERCENT of NAV per position), so the order count itself
    # carries far less risk than it did under the old fixed 2-6%-of-NAV
    # sizing -- 500 is generous headroom above a realistic day's volume
    # (~180 extrapolated from today) while still tripping on genuine
    # runaway/erratic behavior.
    r2d2_max_daily_orders: int = 500
    r2d2_ws_max_symbols: int = 50
    r2d2_ws_rotation_grace_cycles: int = 3
    r2d2_ws_rotation_core_percent: float = 50.0
    r2d2_fmp_prefilter_enabled: bool = True
    r2d2_fmp_prefilter_cache_seconds: int = 15
    r2d2_fmp_prefilter_max_quote_age_seconds: int = 120
    r2d2_fmp_prefilter_batch_size: int = 100
    r2d2_deployment_technical_review_per_market: int = 32
    r2d2_standard_technical_review_per_market: int = 24

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def sec_watchlist(self) -> list[str]:
        return [value.strip().upper() for value in self.investor_relations_sec_watchlist.split(",") if value.strip()]

    @property
    def pluggy_items(self) -> list[str]:
        normalized = self.pluggy_item_ids.replace(";", ",").replace("\n", ",")
        return [value.strip() for value in normalized.split(",") if value.strip()]

    @property
    def openai_usage_projects(self) -> list[str]:
        return [value.strip() for value in self.openai_usage_project_ids.split(",") if value.strip()]

    @property
    def anthropic_usage_workspaces(self) -> list[str]:
        return [value.strip() for value in self.anthropic_usage_workspace_ids.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
