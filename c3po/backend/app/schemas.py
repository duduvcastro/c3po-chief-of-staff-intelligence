from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str
    as_of: datetime | None = None
    collected_at: datetime
    quality: int = Field(ge=0, le=100)
    status: Literal["fresh", "stale", "unavailable"]


class LeahDevice(BaseModel):
    id: str
    name: str
    platform: str
    calendar_authorized: bool = False
    reminders_authorized: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime


class LeahItem(BaseModel):
    id: str | None = None
    kind: Literal["event", "task"]
    external_id: str | None = None
    container_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=10_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    due_at: datetime | None = None
    is_all_day: bool = False
    is_completed: bool = False
    source: Literal["icloud", "c3po"] = "c3po"
    source_device_id: str | None = None
    source_modified_at: datetime | None = None
    deleted_at: datetime | None = None
    version: int = 1
    updated_at: datetime | None = None


class LeahItemWriteRequest(BaseModel):
    kind: Literal["event", "task"]
    title: str = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=10_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    due_at: datetime | None = None
    is_all_day: bool = False
    is_completed: bool = False


class LeahCloudResponse(BaseModel):
    generated_at: datetime
    connected: bool
    devices: list[LeahDevice]
    items: list[LeahItem]


class LeahPairingResponse(BaseModel):
    code: str
    expires_at: datetime


class LeahAgentPairRequest(BaseModel):
    code: str = Field(min_length=8, max_length=8)
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="macOS", max_length=80)


class LeahAgentPairResponse(BaseModel):
    token: str
    device: LeahDevice


class LeahEventOccurrence(BaseModel):
    external_id: str = Field(min_length=1, max_length=2_000)
    starts_at: datetime


class LeahAgentSyncRequest(BaseModel):
    cursor: datetime | None = None
    calendar_authorized: bool = False
    reminders_authorized: bool = False
    items: list[LeahItem] = Field(default_factory=list, max_length=10_000)
    calendar_snapshot: list[LeahEventOccurrence] | None = Field(default=None, max_length=10_000)
    calendar_snapshot_start: datetime | None = None
    calendar_snapshot_end: datetime | None = None


class LeahAgentSyncResponse(BaseModel):
    cursor: datetime
    items: list[LeahItem]


class WeatherHour(BaseModel):
    time: str
    temperature_c: float | None = None
    apparent_c: float | None = None
    rain_probability_percent: float | None = Field(default=None, ge=0, le=100)
    weather_code: int | None = None
    condition: str
    wind_kts: float | None = Field(default=None, ge=0)
    wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    wind_direction: str


class WeatherLocation(BaseModel):
    key: str
    label: str
    city: str
    region: str
    country: str
    latitude: float
    longitude: float
    timezone: str
    fixed: bool = False
    current_temperature_c: float | None = None
    current_apparent_c: float | None = None
    current_weather_code: int | None = None
    current_condition: str
    current_precipitation_mm: float | None = Field(default=None, ge=0)
    current_wind_kts: float | None = Field(default=None, ge=0)
    current_wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    current_wind_direction: str
    as_of: str
    hours: list[WeatherHour]


class WeatherResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int = Field(ge=30)
    source: str
    searched_for: str | None = None
    locations: list[WeatherLocation]
    errors: list[str] = Field(default_factory=list)


class NewsItem(BaseModel):
    rank: int = Field(ge=0)
    source: str
    title: str
    summary: str = ""
    url: str
    published_at: datetime | None = None
    score: float


class NewsSourceGroup(BaseModel):
    code: Literal["globo", "uol", "bloomberg", "cnbc"]
    name: str
    homepage_url: str
    status: Literal["fresh", "partial", "unavailable"]
    fetched_at: datetime | None = None
    items: list[NewsItem]
    errors: list[str] = Field(default_factory=list)


class NewsResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int = Field(ge=60)
    source_count: int = Field(ge=0, le=4)
    item_count: int = Field(ge=0, le=20)
    groups: list[NewsSourceGroup]


class Metric(BaseModel):
    label: str
    value: str
    detail: str = ""
    tone: Literal["neutral", "positive", "warning", "critical"] = "neutral"


class MarketItem(BaseModel):
    symbol: str
    price: str
    change: str
    time: str
    direction: Literal["up", "down", "flat"]


class PortfolioItem(BaseModel):
    symbol: str
    price: str
    change: str
    direction: Literal["up", "down", "flat"]


class IntegrationHealth(BaseModel):
    name: str
    status: Literal["healthy", "attention", "offline"]
    detail: str
    last_update: str


class ApiUsageMetric(BaseModel):
    provider: str
    used: int = Field(ge=0)
    limit: int = Field(gt=0)
    percent_used: float = Field(ge=0)
    period: str = "daily"
    status: Literal["healthy", "attention", "critical"]
    detail: str
    measured_at: datetime


class AiUsageMetric(BaseModel):
    provider: Literal["OpenAI", "Anthropic"]
    product: str
    status: Literal["healthy", "attention", "unavailable"]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    requests: int | None = Field(default=None, ge=0)
    period: str = "month_to_date"
    detail: str
    measured_at: datetime


class SystemHealthGroup(BaseModel):
    key: Literal["apis", "external_services", "open_finance", "aws", "quotes", "official_sources", "automations"]
    label: str
    status: Literal["healthy", "attention", "offline"]
    healthy_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    items: list[IntegrationHealth]


class SystemHealthResponse(BaseModel):
    generated_at: datetime
    status: Literal["healthy", "attention", "offline"]
    quality: int = Field(ge=0, le=100)
    healthy_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    api_usage: list[ApiUsageMetric] = Field(default_factory=list)
    ai_usage: list[AiUsageMetric] = Field(default_factory=list)
    groups: list[SystemHealthGroup]


class MarketDataProviderHealth(BaseModel):
    code: Literal["brapi", "eodhd"]
    name: str
    market: str
    configured: bool
    plan: str
    status: Literal["healthy", "attention", "unconfigured"]
    last_success_at: datetime | None = None
    last_error: str | None = None


class NormalizedQuote(BaseModel):
    provider: Literal["brapi", "eodhd"]
    symbol: str
    provider_symbol: str
    exchange: str | None = None
    currency: str | None = None
    price: float
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    low: float | None = None
    high: float | None = None
    previous_close: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    as_of: datetime
    collected_at: datetime
    quality_score: int = Field(ge=0, le=100)
    is_delayed: bool = True


class MarketDataQuoteResponse(BaseModel):
    items: list[NormalizedQuote]
    errors: list[str] = Field(default_factory=list)


class B3Candidate(BaseModel):
    rank: int = Field(ge=1, le=10)
    symbol: str
    name: str
    security_type: Literal["Stock", "ETF"] = "Stock"
    logo_url: str | None = None
    sector: str
    industry: str | None = None
    peer_group: str | None = None
    sector_source: str | None = None
    sector_confidence: float | None = Field(default=None, ge=0, le=100)
    valuation_profile: Literal["financial", "real_estate", "utilities", "cyclical", "growth", "quality_compounder", "general"]
    price: float
    change_percent: float | None = None
    volume: float | None = None
    average_daily_value_90d: float | None = None
    market_cap: float | None = None
    our_tp: float
    internal_tp: float
    consensus_weight_percent: float = Field(ge=0, le=100)
    upside_percent: float
    expected_total_return_percent: float
    buy_in: float
    price_vs_buy_in_percent: float
    buy_in_models: dict[str, float]
    public_consensus_tp: float | None = None
    analyst_count: int | None = None
    pe: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    peg: float | None = None
    price_to_book: float | None = None
    roe_percent: float | None = None
    fcf_yield_percent: float | None = None
    score: float = Field(ge=0, le=100)
    risk_score: float = Field(ge=0, le=100)
    valuation_confidence: float = Field(ge=0, le=100)
    method_dispersion_percent: float = Field(ge=0)
    data_source_count: int = Field(default=1, ge=1)
    source_agreement_percent: float = Field(default=30, ge=0, le=100)
    fundamentals_as_of: str | None = None
    ir_status: Literal["current", "pending_review", "unavailable"] = "unavailable"
    latest_ir_event_at: datetime | None = None
    latest_ir_event_type: str | None = None
    tp_validation_score: float = Field(ge=0, le=100)
    tp_validation_reasons: list[str] = Field(default_factory=list)
    consensus_gap_percent: float | None = Field(default=None, ge=0)
    valuation_method_count: int = Field(ge=0)
    internal_method_count: int = Field(ge=0)
    quality_score: int = Field(ge=0, le=100)
    status: Literal["full_match", "near_buy", "watchlist"]
    thesis: str
    risk: str
    as_of: datetime


class B3CandidateResponse(BaseModel):
    market: Literal["B3", "NASDAQ", "NYSE"] = "B3"
    source: str
    methodology: str
    methodology_version: int
    universe_size: int
    eligible_count: int
    generated_at: datetime
    items: list[B3Candidate]
    criteria: dict[str, str]


class MatrixPowerItem(BaseModel):
    symbol: str
    name: str
    security_type: Literal["Stock", "ETF"] = "Stock"
    logo_url: str | None = None
    sector: str
    industry: str | None = None
    peer_group: str | None = None
    sector_source: str | None = None
    sector_confidence: float | None = Field(default=None, ge=0, le=100)
    valuation_profile: Literal["financial", "real_estate", "utilities", "cyclical", "growth", "quality_compounder", "general"]
    price: float
    change_percent: float | None = None
    our_tp: float
    internal_tp: float
    public_consensus_tp: float | None = None
    analyst_count: int | None = None
    consensus_weight_percent: float = Field(ge=0, le=100)
    expected_return_percent: float
    tp_upside_percent: float
    buy_in: float
    price_vs_buy_in_percent: float
    risk_score: float = Field(ge=0, le=100)
    power_score: float = Field(ge=0, le=100)
    valuation_confidence: float = Field(ge=0, le=100)
    method_dispersion_percent: float = Field(ge=0)
    data_source_count: int = Field(default=1, ge=1)
    source_agreement_percent: float = Field(default=30, ge=0, le=100)
    fundamentals_as_of: str | None = None
    ir_status: Literal["current", "pending_review", "unavailable"] = "unavailable"
    latest_ir_event_at: datetime | None = None
    latest_ir_event_type: str | None = None
    tp_validation_score: float = Field(ge=0, le=100)
    tp_validation_reasons: list[str] = Field(default_factory=list)
    consensus_gap_percent: float | None = Field(default=None, ge=0)
    valuation_method_count: int = Field(ge=0)
    internal_method_count: int = Field(ge=0)
    signal_quality: Literal["validated", "provisional"]
    beta: float | None = None
    volatility_90d_percent: float | None = None
    quadrant: Literal[
        "high_return_low_risk",
        "high_return_high_risk",
        "low_return_low_risk",
        "low_return_high_risk",
    ]
    x_percent: float = Field(ge=0, le=100)
    y_percent: float = Field(ge=0, le=100)
    as_of: datetime


class MatrixPowerResponse(BaseModel):
    market: Literal["B3", "NASDAQ", "NYSE"] = "B3"
    source: str
    methodology_name: str
    methodology_version: int
    universe_size: int
    source_eligible_count: int
    item_count: int
    validated_count: int = 0
    provisional_count: int = 0
    coverage_audit: dict[str, int] = Field(default_factory=dict)
    tp_upside_cutoff_percent: float
    risk_cutoff: float
    quote_refresh_seconds: int
    provider_delay_minutes: int
    basis_generated_at: datetime
    generated_at: datetime
    items: list[MatrixPowerItem]
    methodology: dict[str, str]


class LiveMarketItem(BaseModel):
    group: Literal["Future Index", "Index", "Currencies", "Crypto", "Portfolio"]
    symbol: str
    name: str
    provider_symbol: str
    provider: str
    exchange: str | None = None
    currency: str | None = None
    price: float
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    low: float | None = None
    high: float | None = None
    previous_close: float | None = None
    market_state: str
    status: Literal["live", "delayed", "closed", "stale"]
    delay_minutes: int
    as_of: datetime
    collected_at: datetime
    quality_score: int = Field(ge=0, le=100)


class LiveMarketsResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int
    cache_seconds: int
    item_count: int
    groups: dict[str, list[LiveMarketItem]]
    errors: list[str] = Field(default_factory=list)
    methodology: dict[str, str]


class LiveMarketIndexResponse(BaseModel):
    generated_at: datetime
    refresh_seconds: int
    items: list[LiveMarketItem]
    errors: list[str] = Field(default_factory=list)


class RealtimeMarketIndex(BaseModel):
    symbol: str
    name: str
    value: float
    change_percent: float | None = None
    currency: str
    market_state: str
    status: Literal["live", "delayed", "closed", "stale"]
    as_of: datetime


class RealtimeMarketLeader(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float
    volume: float
    cash_volume: float
    currency: str
    exchange: str
    as_of: datetime
    logo_url: str | None = None
    status: Literal["live", "delayed", "closed", "stale"] = "delayed"
    delay_minutes: int = 15


class RealtimeMarketResponse(BaseModel):
    market: Literal["B3", "NASDAQ", "NYSE"]
    index: RealtimeMarketIndex
    universe_size: int
    gainers: list[RealtimeMarketLeader]
    losers: list[RealtimeMarketLeader]
    volume_leaders: list[RealtimeMarketLeader]
    cash_leaders: list[RealtimeMarketLeader]
    source: str
    delay_minutes: int
    refresh_seconds: int
    generated_at: datetime
    errors: list[str] = Field(default_factory=list)


class RealtimePortfolioRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=18, pattern=r"^[A-Za-z0-9.\-]+$")


class RealtimePortfolioSymbolSuggestion(BaseModel):
    symbol: str
    name: str
    market: Literal["B3", "NASDAQ", "NYSE", "OTC"]
    exchange: str
    security_type: str
    currency: str
    already_tracked: bool = False


class RealtimePortfolioSymbolSearchResponse(BaseModel):
    query: str
    item_count: int = Field(ge=0)
    items: list[RealtimePortfolioSymbolSuggestion]
    sources: list[str]
    errors: list[str] = Field(default_factory=list)


class RealtimePortfolioItem(RealtimeMarketLeader):
    market: Literal["B3", "NASDAQ", "NYSE", "OTC"]
    source: str
    delay_minutes: int
    status: Literal["live", "delayed", "closed", "stale"]


class RealtimePortfolioIntradayPoint(BaseModel):
    as_of: datetime
    price: float = Field(gt=0)
    volume: float = Field(default=0, ge=0)


class InstrumentIntradayResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    session_date: str
    series_kind: Literal["intraday", "daily"] = "intraday"
    interval_minutes: int = Field(default=5, ge=1)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    current: float = Field(gt=0)
    change_percent: float
    points: list[RealtimePortfolioIntradayPoint]
    source: str
    delay_minutes: int = Field(ge=0)
    status: Literal["live", "delayed", "closed", "stale"]
    generated_at: datetime


class RealtimePortfolioIntradayResponse(BaseModel):
    symbol: str
    name: str
    market: Literal["B3", "NASDAQ", "NYSE", "OTC"]
    currency: str
    session_date: str
    interval_minutes: int = Field(default=5, ge=1)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    current: float = Field(gt=0)
    change_percent: float
    points: list[RealtimePortfolioIntradayPoint]
    source: str
    delay_minutes: int = Field(ge=0)
    status: Literal["live", "delayed", "closed", "stale"]
    generated_at: datetime


class RealtimePortfolioResponse(BaseModel):
    item_count: int
    items: list[RealtimePortfolioItem]
    refresh_seconds: int
    generated_at: datetime
    sources: list[str]
    errors: list[str] = Field(default_factory=list)


class R2D2SummaryStats(BaseModel):
    closed_days: int = Field(ge=0)
    positive_days: int = Field(ge=0)
    above_half_percent_days: int = Field(ge=0)
    negative_days: int = Field(ge=0)
    below_minus_half_percent_days: int = Field(ge=0)
    flat_days: int = Field(ge=0)
    win_rate_percent: float = Field(ge=0, le=100)
    total_transactions: int = Field(default=0, ge=0)
    positive_transactions: int = Field(default=0, ge=0)
    negative_transactions: int = Field(default=0, ge=0)


class R2D2TrackPoint(BaseModel):
    session_date: str
    nav_usd: float
    daily_pnl_usd: float
    daily_return_percent: float
    is_final: bool


class R2D2LearningCurvePoint(BaseModel):
    session_date: str
    positive_percent: float
    positive_trades: int
    negative_trades: int


class R2D2Position(BaseModel):
    market: Literal["B3", "NASDAQ", "NYSE"]
    symbol: str
    name: str
    logo_url: str | None = None
    currency: str
    quantity: float
    average_cost_local: float
    last_price_local: float
    market_value_usd: float
    unrealized_pnl_usd: float
    unrealized_return_percent: float
    allocation_percent: float
    stop_price_local: float
    technical_score: float = Field(default=0, ge=0, le=100)
    trend_state: str = "pending"
    volume_state: str = "pending"
    data_status: str = "pending"
    decision_state: str = "monitor"
    quote_status: str = "stored"
    quote_as_of: datetime | None = None
    technical_as_of: datetime | None = None
    opened_at: datetime
    updated_at: datetime


class R2D2Trade(BaseModel):
    id: str
    market: Literal["B3", "NASDAQ", "NYSE"]
    symbol: str
    name: str
    side: Literal["BUY", "SELL"]
    quantity: float
    signal_price_local: float
    fill_price_local: float
    currency: str
    gross_value_usd: float
    fees_usd: float
    slippage_usd: float
    realized_pnl_usd: float | None = None
    realized_return_percent: float | None = None
    reason: str
    executed_at: datetime
    quote_as_of: datetime


class R2D2CycleStatus(BaseModel):
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    scanned_count: int = Field(default=0, ge=0)
    signal_count: int = Field(default=0, ge=0)
    trade_count: int = Field(default=0, ge=0)
    error_summary: str | None = None


class R2D2LearningState(BaseModel):
    version: int = Field(ge=1)
    effective_date: str
    sample_days: int = Field(ge=0)
    sample_trades: int = Field(ge=0)
    parameters: dict[str, float]
    metrics: dict[str, float]
    rationale: list[str]


class R2D2DashboardResponse(BaseModel):
    experiment_code: str
    status: Literal["scheduled", "running", "paused", "completed"]
    methodology_version: str
    start_date: str
    checkpoint_date: str
    checkpoint_reached: bool
    checkpoint_days: int
    operating_days_elapsed: int
    starting_capital_usd: float
    nav_usd: float
    cash_usd: float
    gross_exposure_usd: float
    total_return_percent: float
    daily_pnl_usd: float
    daily_return_percent: float
    open_positions: int
    stats: R2D2SummaryStats
    track_record: list[R2D2TrackPoint]
    learning_curve: list[R2D2LearningCurvePoint]
    positions: list[R2D2Position]
    trades: list[R2D2Trade]
    last_cycle: R2D2CycleStatus | None = None
    learning: R2D2LearningState
    mandate: dict[str, Any]
    generated_at: datetime


class MarketDataSyncRequest(BaseModel):
    provider: Literal["brapi", "eodhd"]
    symbols: list[str] = Field(min_length=1, max_length=20)


class OnePagerRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=18)


class OnePagerReport(BaseModel):
    symbol: str
    company_name: str
    market: Literal["B3", "US"]
    currency: str
    filename: str
    generated_at: datetime
    source: str
    methodology_name: str = "Legacy valuation"
    methodology_version: int | None = None
    price: float
    c3po_tp: float
    consensus_tp: float | None = None
    buy_in: float
    upside_percent: float
    confidence: int = Field(ge=0, le=100)
    method_count: int = Field(ge=1, le=5)
    download_url: str


class OnePagerListResponse(BaseModel):
    items: list[OnePagerReport]


class ValuationChangeRecord(BaseModel):
    id: str
    snapshot_id: str | None = None
    market: Literal["B3", "NASDAQ", "NYSE", "US"]
    symbol: str
    company_name: str
    logo_url: str | None = None
    changed_at: datetime
    trigger_type: Literal["initial", "financial_results", "material_event", "web_research", "market_data", "methodology"]
    trigger_title: str
    trigger_summary: str = ""
    source_name: str = ""
    source_url: str | None = None
    currency: str
    old_tp: float | None = None
    new_tp: float
    tp_change_percent: float | None = None
    old_buy_in: float | None = None
    new_buy_in: float | None = None
    old_consensus_tp: float | None = None
    new_consensus_tp: float | None = None
    price: float | None = None
    old_confidence: float | None = None
    new_confidence: float | None = None
    methodology_name: str
    methodology_version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValuationChangeResponse(BaseModel):
    generated_at: datetime
    total: int = Field(ge=0)
    item_count: int = Field(ge=0)
    items: list[ValuationChangeRecord]


class InvestorRelationsSourceHealth(BaseModel):
    code: Literal["cvm", "sec", "ri", "finnhub"]
    name: str
    status: Literal["healthy", "attention", "unconfigured"]
    last_success_at: datetime | None = None
    last_error: str | None = None
    detail: str


class InvestorRelationsEvent(BaseModel):
    id: str
    source: Literal["cvm", "sec", "ri", "finnhub"]
    market: Literal["B3", "US"]
    symbol: str | None = None
    company_name: str
    regulator_id: str | None = None
    event_type: str
    form: str | None = None
    title: str
    summary: str = ""
    published_at: datetime
    published_time_precision: Literal["datetime", "date", "collected"] = "datetime"
    reference_date: str | None = None
    official_url: str
    document_url: str | None = None
    materiality: Literal["high", "medium", "low"]
    valuation_relevant: bool
    valuation_status: Literal["pending_review", "incorporated", "informational"]
    reviewed_at: datetime | None = None
    review_note: str = ""
    collected_at: datetime


class InvestorRelationsResponse(BaseModel):
    generated_at: datetime
    total_events: int
    today_events: int
    pending_reviews: int
    high_materiality: int
    monitored_companies: int
    items: list[InvestorRelationsEvent]
    sources: list[InvestorRelationsSourceHealth]
    methodology: dict[str, str]


class InvestorRelationsSyncResponse(BaseModel):
    generated_at: datetime
    records_read: int
    records_written: int
    sources: dict[str, str]


class InvestorRelationsWatchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=18, pattern=r"^[A-Za-z0-9.\-]+$")
    market: Literal["B3", "US"]
    company_name: str = Field(default="", max_length=200)
    ri_url: str | None = Field(default=None, max_length=1000)


class InvestorRelationsReviewRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class ServerUsagePoint(BaseModel):
    collected_at: datetime
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    cpu_moving_average_5m: float | None = Field(default=None, ge=0, le=100)
    disk_percent: float | None = Field(default=None, ge=0, le=100)


class ServerUsageCurrent(BaseModel):
    cpu_percent: float | None = Field(default=None, ge=0, le=100)
    cpu_moving_average_5m: float | None = Field(default=None, ge=0, le=100)
    disk_percent: float | None = Field(default=None, ge=0, le=100)
    disk_total_bytes: int | None = Field(default=None, ge=0)
    disk_used_bytes: int | None = Field(default=None, ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    collected_at: datetime | None = None


class ServerUsageServer(BaseModel):
    server_id: str
    server_name: str
    region: str
    cpu_count: int = Field(ge=1)
    status: Literal["healthy", "attention", "offline"]
    current: ServerUsageCurrent
    history: list[ServerUsagePoint]


class ServerUsageResponse(BaseModel):
    generated_at: datetime
    window_hours: int
    moving_average_minutes: int
    refresh_seconds: int
    servers: list[ServerUsageServer]
    methodology: dict[str, str]


class OpenFinanceAccount(BaseModel):
    id: str
    name: str
    product: Literal["BANK", "CREDIT", "OTHER"]
    subtype: str
    display_number: str
    balance: float
    currency: str
    available_credit: float | None = None
    credit_limit: float | None = None
    due_date: str | None = None


class OpenFinanceInvestment(BaseModel):
    id: str
    name: str
    type: str
    gross_value: float
    net_value: float | None = None
    unit_value: float | None = None
    quantity: float | None = None
    currency: str
    status: str
    as_of: datetime | None = None


class OpenFinanceTransaction(BaseModel):
    id: str
    account_id: str
    account_name: str
    account_number: str
    account_product: Literal["BANK", "CREDIT", "OTHER"]
    description: str
    category: str
    amount: float
    currency: str
    status: str
    transaction_at: datetime


class OpenFinanceBank(BaseModel):
    code: Literal["btg", "santander", "itau"]
    name: str
    connection_status: Literal["healthy", "syncing", "attention", "offline"]
    execution_status: str
    last_sync_at: datetime | None = None
    next_sync_at: datetime | None = None
    connector_name: str | None = None
    is_open_finance: bool = False
    refresh_status: Literal["completed", "started", "recent", "scheduled", "needs_action", "unavailable"]
    refresh_detail: str
    accounts: list[OpenFinanceAccount]
    investments: list[OpenFinanceInvestment]
    transactions: list[OpenFinanceTransaction]
    cash_total_brl: float
    credit_balance_brl: float
    investments_total_brl: float


class OpenFinanceResponse(BaseModel):
    generated_at: datetime
    window_hours: int
    window_start: datetime
    source: str
    refresh_requested: bool
    banks: list[OpenFinanceBank]
    cash_total_brl: float
    credit_balance_brl: float
    investments_total_brl: float
    errors: list[str]
    methodology: dict[str, str]


class CommandCenterResponse(BaseModel):
    generated_at: datetime
    report_title: str
    report_path: str | None
    report_date: str
    greeting: str
    metrics: list[Metric]
    markets: dict[str, list[MarketItem]]
    portfolio: list[PortfolioItem]
    billfish: dict[str, str]
    priorities: list[str]
    agenda: list[str]
    decision_queue: list[dict[str, str]]
    integrations: list[IntegrationHealth]
    provenance: Provenance


class FeedbackRequest(BaseModel):
    subject_type: str = Field(min_length=1, max_length=80)
    subject_id: str = Field(min_length=1, max_length=160)
    rating: Literal[-1, 1]
    comment: str = Field(default="", max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    id: str
    accepted: bool = True


class AlertReadRequest(BaseModel):
    alert_ids: list[str] = Field(default_factory=list, max_length=250)


class AlertReadResponse(BaseModel):
    marked_read: int = Field(ge=0)
    read_at: datetime


class NavigationIndicator(BaseModel):
    has_new: bool
    unseen_count: int = Field(ge=0)
    latest_at: datetime | None = None
    last_seen_at: datetime | None = None


class NavigationIndicatorsResponse(BaseModel):
    generated_at: datetime
    feeds: dict[Literal["relations", "intelligence"], NavigationIndicator]


class NavigationSeenRequest(BaseModel):
    view: Literal["relations", "intelligence"]


class NavigationSeenResponse(BaseModel):
    view: Literal["relations", "intelligence"]
    seen_at: datetime


class LoginCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class LoginCodeResponse(BaseModel):
    challenge_id: str
    expires_in_seconds: int
    message: str


class LoginVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=36, max_length=36)
    code: str = Field(pattern=r"^\d{6}$")
    platform: str | None = Field(default=None, max_length=120)
    max_touch_points: int = Field(default=0, ge=0, le=20)


class AuthSessionResponse(BaseModel):
    authenticated: bool
    email: str | None = None
    expires_at: datetime | None = None
    session_started_at: datetime | None = None
    last_activity_at: datetime | None = None
    display_name: str | None = None
    role: Literal["owner", "member"] | None = None
    is_admin: bool = False
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    idle_timeout_seconds: int | None = None
    ip_address: str | None = None
    device_type: str | None = None
    operating_system: str | None = None
    browser: str | None = None


class AccessPermission(BaseModel):
    key: str
    label: str


class AccessCapability(BaseModel):
    key: str
    label: str


class AccessUser(BaseModel):
    email: str
    display_name: str
    role: Literal["owner", "member"]
    is_active: bool
    permissions: list[str]
    capabilities: list[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AccessUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(default="", max_length=120)
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=lambda: ["read"])


class AccessUserUpdateRequest(BaseModel):
    display_name: str = Field(default="", max_length=120)
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=lambda: ["read"])


class AccessUserListResponse(BaseModel):
    items: list[AccessUser]
    available_permissions: list[AccessPermission]
    available_capabilities: list[AccessCapability]
