Warning: truncated output (original token count: 95198)
Total output lines: 8069

"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bell,
  BookOpenCheck,
  Brain,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ChartPie,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Cloud,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSun,
  Command,
  Cpu,
  Download,
  Droplets,
  ExternalLink,
  FileChartColumn,
  FileDown,
  FilePlus2,
  Github,
  Gauge,
  HeartPulse,
  HardDrive,
  Inbox,
  LineChart,
  LockKeyhole,
  LogOut,
  Mail,
  Menu,
  Minus,
  PanelsTopLeft,
  Plus,
  RefreshCw,
  Search,
  Server,
  Save,
  ShieldCheck,
  Snowflake,
  Sun,
  Target,
  ThumbsDown,
  ThumbsUp,
  TrendingDown,
  TrendingUp,
  Trash2,
  Users,
  WalletCards,
  Wind,
  X
} from "lucide-react";
import { type ComponentType, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode, createContext, forwardRef, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Tone = "neutral" | "positive" | "warning" | "critical";
type Direction = "up" | "down" | "flat";
type AccessCapabilityKey = "read" | "onepager_generate" | "delete";
type ViewKey =
  | "home"
  | "command"
  | "markets"
  | "realtime"
  | "weather"
  | "portfolio"
  | "relations"
  | "news"
  | "r2d2"
  | "candidates"
  | "matrix"
  | "chewie"
  | "onepager"
  | "intelligence"
  | "finance"
  | "alerts"
  | "health"
  | "serverusage"
  | "leah"
  | "helm";

interface AuthSession {
  authenticated: boolean;
  email: string | null;
  display_name: string | null;
  role: "owner" | "member" | null;
  is_admin: boolean;
  permissions: ViewKey[];
  capabilities: AccessCapabilityKey[];
  expires_at: string | null;
  session_started_at: string | null;
  last_activity_at: string | null;
  idle_timeout_seconds: number | null;
  ip_address: string | null;
  device_type: string | null;
  operating_system: string | null;
  browser: string | null;
  totp_enabled: boolean;
}

interface LeahDevice {
  id: string;
  name: string;
  platform: string;
  calendar_authorized: boolean;
  reminders_authorized: boolean;
  last_seen_at: string | null;
  created_at: string;
}

interface LeahItem {
  id: string;
  kind: "event" | "task";
  title: string;
  notes: string;
  starts_at: string | null;
  ends_at: string | null;
  due_at: string | null;
  is_all_day: boolean;
  is_completed: boolean;
  source: "icloud" | "c3po";
  updated_at: string | null;
}

interface LeahCloudResponse {
  connected: boolean;
  devices: LeahDevice[];
  items: LeahItem[];
}

interface AccessPermission {
  key: ViewKey;
  label: string;
}

interface AccessCapability {
  key: AccessCapabilityKey;
  label: string;
}

interface AccessUser {
  email: string;
  display_name: string;
  role: "owner" | "member";
  is_active: boolean;
  permissions: ViewKey[];
  capabilities: AccessCapabilityKey[];
  created_by: string;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

interface AccessUserListResponse {
  items: AccessUser[];
  available_permissions: AccessPermission[];
  available_capabilities: AccessCapability[];
}

interface Metric {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
}

interface MarketItem {
  symbol: string;
  price: string;
  change: string;
  time: string;
  direction: Direction;
}

interface PortfolioItem {
  symbol: string;
  price: string;
  change: string;
  direction: Direction;
}

interface Integration {
  name: string;
  status: "healthy" | "attention" | "offline";
  detail: string;
  last_update: string;
}

type SystemHealthGroupKey = "apis" | "external_services" | "open_finance" | "aws" | "controls" | "quotes" | "official_sources" | "automations";

interface SystemHealthGroup {
  key: SystemHealthGroupKey;
  label: string;
  status: "healthy" | "attention" | "offline";
  healthy_count: number;
  total_count: number;
  items: Integration[];
}

interface SystemHealthData {
  generated_at: string;
  status: "healthy" | "attention" | "offline";
  quality: number;
  healthy_count: number;
  total_count: number;
  api_usage: ApiUsageMetric[];
  groups: SystemHealthGroup[];
}

interface ApiUsageMetric {
  provider: string;
  used: number;
  limit: number;
  percent_used: number;
  period: string;
  status: "healthy" | "attention" | "critical";
  detail: string;
  measured_at: string;
}

interface R2D2DashboardData {
  experiment_code: string;
  status: "scheduled" | "running" | "paused" | "completed";
  entries_paused: boolean;
  entries_paused_at: string | null;
  entries_pause_operator: string | null;
  entries_pause_reason: string | null;
  methodology_version: string;
  start_date: string;
  checkpoint_date: string;
  checkpoint_reached: boolean;
  checkpoint_days: number;
  operating_days_elapsed: number;
  starting_capital_usd: number;
  nav_usd: number;
  accounting_nav_usd: number;
  cumulative_pnl_usd: number;
  cash_usd: number;
  gross_exposure_usd: number;
  total_return_percent: number;
  daily_pnl_usd: number;
  daily_return_percent: number;
  daily_pnl_date: string | null;
  open_positions: number;
  stats: {
    closed_days: number;
    positive_days: number;
    above_half_percent_days: number;
    negative_days: number;
    below_minus_half_percent_days: number;
    flat_days: number;
    win_rate_percent: number;
    total_transactions: number;
    positive_transactions: number;
    negative_transactions: number;
  };
  track_record: Array<{
    session_date: string;
    nav_usd: number;
    daily_pnl_usd: number;
    daily_return_percent: number;
    is_final: boolean;
  }>;
  learning_curve: Array<{
    session_date: string;
    positive_percent: number;
    positive_trades: number;
    negative_trades: number;
  }>;
  positions: Array<{
    market: "B3" | "NASDAQ" | "NYSE";
    symbol: string;
    name: string;
    logo_url: string | null;
    currency: string;
    quantity: number;
    average_cost_local: number;
    last_price_local: number;
    market_value_usd: number;
    unrealized_pnl_usd: number;
    unrealized_return_percent: number;
    allocation_percent: number;
    stop_price_local: number;
    technical_score: number;
    trend_state: string;
    volume_state: string;
    data_status: string;
    decision_state: string;
    technical_defense_score: number;
    technical_defense_severity: string;
    technical_defense_reviews: number;
    technical_defense_reductions: number;
    technical_defense_drivers: string[];
    technical_defense_reviewed_at: string | null;
    quote_status: string;
    quote_as_of: string | null;
    technical_as_of: string | null;
    opened_at: string;
    updated_at: string;
  }>;
  trades: Array<{
    id: string;
    market: "B3" | "NASDAQ" | "NYSE";
    symbol: string;
    name: string;
    side: "BUY" | "SELL";
    quantity: number;
    signal_price_local: number;
    fill_price_local: number;
    currency: string;
    gross_value_usd: number;
    fees_usd: number;
    slippage_usd: number;
    realized_pnl_usd: number | null;
    realized_return_percent: number | null;
    reason: string;
    executed_at: string;
    quote_as_of: string;
  }>;
  last_cycle: {
    status: string;
    started_at: string | null;
    completed_at: string | null;
    scanned_count: number;
    signal_count: number;
    trade_count: number;
    error_summary: string | null;
  } | null;
  learning: {
    version: number;
    effective_date: string;
    sample_days: number;
    sample_trades: number;
    parameters: Record<string, number>;
    metrics: Record<string, number>;
    rationale: string[];
  };
  mandate: Record<string, unknown>;
  generated_at: string;
}

interface R2D2LivePositionsData {
  generated_at: string;
  refresh_seconds: number;
  nav_usd: number;
  cash_usd: number;
  gross_exposure_usd: number;
  open_positions: number;
  positions: R2D2DashboardData["positions"];
}

interface ServerUsagePoint {
  collected_at: string;
  cpu_percent: number | null;
  cpu_moving_average_5m: number | null;
  disk_percent: number | null;
}

interface ServerUsageCurrent {
  cpu_percent: number | null;
  cpu_moving_average_5m: number | null;
  disk_percent: number | null;
  disk_total_bytes: number | null;
  disk_used_bytes: number | null;
  disk_free_bytes: number | null;
  collected_at: string | null;
}

interface ServerUsageServer {
  server_id: string;
  server_name: string;
  region: string;
  cpu_count: number;
  status: "healthy" | "attention" | "offline";
  current: ServerUsageCurrent;
  history: ServerUsagePoint[];
}

interface ServerUsageResponse {
  generated_at: string;
  window_hours: number;
  moving_average_minutes: number;
  refresh_seconds: number;
  servers: ServerUsageServer[];
  api_endpoints: {
    method: string;
    route: string;
    request_count: number;
    average_ms: number;
    p95_ms: number;
    max_ms: number;
    error_percent: number;
  }[];
  api_window_minutes: number;
  methodology: Record<string, string>;
}

interface PageLoadPerformanceStats {
  totalMs: number;
  apiWaitMs: number;
  backendMs: number;
  renderMs: number;
  requestCount: number;
  count: number;
}

interface WeatherHour {
  time: string;
  temperature_c: number | null;
  apparent_c: number | null;
  rain_probability_percent: number | null;
  weather_code: number | null;
  condition: string;
  wind_kts: number | null;
  wind_direction_deg: number | null;
  wind_direction: string;
}

interface WeatherLocation {
  key: string;
  label: string;
  city: string;
  region: string;
  country: string;
  latitude: number;
  longitude: number;
  timezone: string;
  fixed: boolean;
  current_temperature_c: number | null;
  current_apparent_c: number | null;
  current_weather_code: number | null;
  current_condition: string;
  current_precipitation_mm: number | null;
  current_wind_kts: number | null;
  current_wind_direction_deg: number | null;
  current_wind_direction: string;
  as_of: string;
  hours: WeatherHour[];
}

interface WeatherResponse {
  generated_at: string;
  refresh_seconds: number;
  source: string;
  searched_for: string | null;
  locations: WeatherLocation[];
  errors: string[];
}

interface NewsItem {
  rank: number;
  source: string;
  title: string;
  summary: string;
  url: string;
  published_at: string | null;
  score: number;
}

interface NewsSourceGroup {
  code: "globo" | "uol" | "bloomberg" | "cnbc";
  name: string;
  homepage_url: string;
  status: "fresh" | "partial" | "unavailable";
  fetched_at: string | null;
  items: NewsItem[];
  errors: string[];
}

interface NewsResponse {
  generated_at: string;
  refresh_seconds: number;
  source_count: number;
  item_count: number;
  groups: NewsSourceGroup[];
}

interface MarketDataProvider {
  code: "brapi" | "eodhd";
  name: string;
  market: string;
  configured: boolean;
  plan: string;
  status: "healthy" | "attention" | "unconfigured";
  last_success_at: string | null;
  last_error: string | null;
}

interface B3Candidate {
  rank: number;
  symbol: string;
  name: string;
  security_type: "Stock" | "ETF";
  logo_url: string | null;
  sector: string;
  industry: string | null;
  peer_group: string | null;
  sector_source: string | null;
  sector_confidence: number | null;
  valuation_profile: "financial" | "real_estate" | "utilities" | "cyclical" | "growth" | "quality_compounder" | "general";
  price: number;
  change_percent: number | null;
  volume: number | null;
  average_daily_value_90d: number | null;
  market_cap: number | null;
  our_tp: number;
  internal_tp: number;
  consensus_weight_percent: number;
  upside_percent: number;
  expected_total_return_percent: number;
  buy_in: number;
  price_vs_buy_in_percent: number;
  buy_in_models: Record<string, number>;
  public_consensus_tp: number | null;
  analyst_count: number | null;
  pe: number | null;
  forward_pe: number | null;
  ev_ebitda: number | null;
  peg: number | null;
  price_to_book: number | null;
  roe_percent: number | null;
  fcf_yield_percent: number | null;
  score: number;
  risk_score: number;
  valuation_confidence: number;
  method_dispersion_percent: number;
  data_source_count: number;
  source_agreement_percent: number;
  fundamentals_as_of: string | null;
  tp_validation_score: number;
  tp_validation_reasons: string[];
  consensus_gap_percent: number | null;
  valuation_method_count: number;
  internal_method_count: number;
  quality_score: number;
  status: "full_match" | "near_buy" | "watchlist";
  thesis: string;
  risk: string;
  as_of: string;
}

interface B3CandidateResponse {
  market: ResearchMarket;
  source: string;
  methodology: string;
  methodology_version: number;
  universe_size: number;
  eligible_count: number;
  generated_at: string;
  items: B3Candidate[];
  criteria: Record<string, string>;
}

type MatrixQuadrant =
  | "high_return_low_risk"
  | "high_return_high_risk"
  | "low_return_low_risk"
  | "low_return_high_risk";

interface MatrixPowerItem {
  symbol: string;
  name: string;
  security_type: "Stock" | "ETF";
  logo_url: string | null;
  sector: string;
  industry: string | null;
  peer_group: string | null;
  sector_source: string | null;
  sector_confidence: number | null;
  valuation_profile: B3Candidate["valuation_profile"];
  price: number;
  change_percent: number | null;
  our_tp: number;
  internal_tp: number;
  public_consensus_tp: number | null;
  analyst_count: number | null;
  consensus_weight_percent: number;
  expected_return_percent: number;
  tp_upside_percent: number;
  buy_in: number;
  price_vs_buy_in_percent: number;
  risk_score: number;
  power_score: number;
  valuation_confidence: number;
  method_dispersion_percent: number;
  data_source_count: number;
  source_agreement_percent: number;
  fundamentals_as_of: string | null;
  tp_validation_score: number;
  tp_validation_reasons: string[];
  consensus_gap_percent: number | null;
  valuation_method_count: number;
  internal_method_count: number;
  signal_quality: "validated" | "provisional";
  beta: number | null;
  volatility_90d_percent: number | null;
  quadrant: MatrixQuadrant;
  x_percent: number;
  y_percent: number;
  as_of: string;
}

interface MatrixPowerResponse {
  market: ResearchMarket;
  source: string;
  methodology_name: string;
  methodology_version: number | null;
  universe_size: number;
  source_eligible_count: number;
  item_count: number;
  validated_count: number;
  provisional_count: number;
  coverage_audit: Record<string, number>;
  tp_upside_cutoff_percent: number;
  risk_cutoff: number;
  quote_refresh_seconds: number;
  provider_delay_minutes: number;
  basis_generated_at: string;
  generated_at: string;
  items: MatrixPowerItem[];
  methodology: Record<string, string>;
}

interface ChewieFundamentalsItem {
  market: ResearchMarket;
  symbol: string;
  name: string;
  sector: string;
  logo_url: string | null;
  market_cap: number | null;
  fundamentals_as_of: string | null;
  refreshed_at: string | null;
  sources: string[];
  from_universe: boolean;
  multiples: { pe: number | null; forward_pe: number | null; ev_ebitda: number | null; peg: number | null; price_to_book: number | null; dividend_yield_percent: number | null };
  profitability: { roe_percent: number | null; roa_percent: number | null; profit_margin_percent: number | null; operating_margin_percent: number | null; ebitda_margin_percent: number | null };
  leverage: { debt_to_equity: number | null; net_debt_to_ebitda: number | null; total_cash: number | null; total_debt: number | null };
  growth: { revenue_growth_percent: number | null; earnings_growth_percent: number | null };
}

interface ChewieFundamentalsResponse {
  market: ResearchMarket;
  source: string;
  universe_size: number;
  covered_count: number;
  generated_at: string;
  items: ChewieFundamentalsItem[];
}

interface ChewieSearchResponse {
  market: ResearchMarket;
  query: string;
  items: ChewieFundamentalsItem[];
}

type ResearchMarket = "B3" | "NASDAQ" | "NYSE";

type LiveMarketStatus = "live" | "delayed" | "closed" | "stale";

interface LiveMarketItem {
  group: "Future Index" | "Index" | "Currencies" | "Crypto" | "Portfolio";
  symbol: string;
  name: string;
  provider_symbol: string;
  provider: string;
  exchange: string | null;
  currency: string | null;
  price: number;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  low: number | null;
  high: number | null;
  previous_close: number | null;
  market_state: string;
  status: LiveMarketStatus;
  delay_minutes: number;
  as_of: string;
  collected_at: string;
  quality_score: number;
}

interface LiveMarketsResponse {
  generated_at: string;
  refresh_seconds: number;
  cache_seconds: number;
  item_count: number;
  groups: Record<string, LiveMarketItem[]>;
  errors: string[];
  methodology: Record<string, string>;
}

interface LiveMarketIndexResponse {
  generated_at: string;
  refresh_seconds: number;
  items: LiveMarketItem[];
  errors: string[];
}

type RealtimeMarketKey = "B3" | "NASDAQ" | "NYSE";
type RealtimeTabKey = RealtimeMarketKey | "PORTFOLIO";
type RealtimePortfolioMarket = RealtimeMarketKey | "OTC";

interface RealtimeMarketIndex {
  symbol: string;
  name: string;
  value: number;
  change_percent: number | null;
  currency: string;
  market_state: string;
  status: LiveMarketStatus;
  as_of: string;
}

interface RealtimeMarketLeader {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  cash_volume: number;
  currency: string;
  exchange: string;
  as_of: string;
  logo_url: string | null;
  status: LiveMarketStatus;
  delay_minutes: number;
}

interface RealtimeMarketResponse {
  market: RealtimeMarketKey;
  index: RealtimeMarketIndex;
  universe_size: number;
  gainers: RealtimeMarketLeader[];
  losers: RealtimeMarketLeader[];
  volume_leaders: RealtimeMarketLeader[];
  cash_leaders: RealtimeMarketLeader[];
  source: string;
  delay_minutes: number;
  refresh_seconds: number;
  generated_at: string;
  errors: string[];
}

interface RealtimePortfolioItem extends RealtimeMarketLeader {
  market: RealtimePortfolioMarket;
  source: string;
  delay_minutes: number;
  status: LiveMarketStatus;
}

interface RealtimePortfolioResponse {
  item_count: number;
  items: RealtimePortfolioItem[];
  refresh_seconds: number;
  generated_at: string;
  sources: string[];
  errors: string[];
}

interface RealtimePortfolioIntradayPoint {
  as_of: string;
  price: number;
  volume: number;
}

interface RealtimePortfolioIntradayResponse {
  symbol: string;
  name: string;
  market: string;
  currency: string;
  session_date: string;
  series_kind?: "intraday" | "daily";
  interval_minutes: number;
  open: number;
  high: number;
  low: number;
  current: number;
  change_percent: number;
  points: RealtimePortfolioIntradayPoint[];
  source: string;
  delay_minutes: number;
  status: LiveMarketStatus;
  generated_at: string;
}

interface InstrumentPreviewDescriptor {
  symbol: string;
  name: string;
  market?: string;
}

interface RealtimePortfolioSymbolSuggestion {
  symbol: string;
  name: string;
  market: RealtimePortfolioMarket;
  exchange: string;
  security_type: string;
  currency: string;
  already_tracked: boolean;
}

interface RealtimePortfolioSymbolSearchResponse {
  query: string;
  item_count: number;
  items: RealtimePortfolioSymbolSuggestion[];
  sources: string[];
  errors: string[];
}

interface CommandCenterData {
  generated_at: string;
  report_title: string;
  report_date: string;
  greeting: string;
  metrics: Metric[];
  markets: Record<string, MarketItem[]>;
  portfolio: PortfolioItem[];
  billfish: Record<string, string>;
  priorities: string[];
  agenda: string[];
  decision_queue: { subject: string; context: string; action: string }[];
  integrations: Integration[];
  provenance: {
    source: string;
    as_of: string;
    collected_at: string;
    quality: number;
    status: "fresh" | "stale" | "unavailable";
  };
}

interface AlertItem {
  id: string;
  subject: string;
  context: string;
  action: string;
  severity?: string;
  occurred_at?: string;
  source?: string;
  source_url?: string;
  metadata?: Record<string, string>;
  is_read: boolean;
}

interface AlertsData {
  generated_at: string;
  status: "fresh" | "stale";
  unread_count: number;
  items: AlertItem[];
  detail?: string;
}

const ALERTS_PAGE_SIZE = 20;

type NavigationFeedKey = "relations" | "intelligence";

interface NavigationIndicator {
  has_new: boolean;
  unseen_count: number;
  latest_at?: string | null;
  last_seen_at?: string | null;
}

interface NavigationIndicatorsData {
  generated_at: string;
  feeds: Partial<Record<NavigationFeedKey, NavigationIndicator>>;
}

type OpenFinanceConnectionStatus = "healthy" | "syncing" | "attention" | "offline";

interface OpenFinanceAccount {
  id: string;
  name: string;
  product: "BANK" | "CREDIT" | "OTHER";
  subtype: string;
  display_number: string;
  balance: number;
  currency: string;
  available_credit: number | null;
  credit_limit: number | null;
  due_date: string | null;
}

interface OpenFinanceInvestment {
  id: string;
  name: string;
  type: string;
  gross_value: number;
  net_value: number | null;
  unit_value: number | null;
  quantity: number | null;
  currency: string;
  status: string;
  as_of: string | null;
}

interface OpenFinanceTransaction {
  id: string;
  account_id: string;
  account_name: string;
  account_number: string;
  account_product: "BANK" | "CREDIT" | "OTHER";
  description: string;
  category: string;
  amount: number;
  currency: string;
  status: string;
  transaction_at: string;
}

interface OpenFinanceBank {
  code: "btg" | "santander" | "itau";
  name: string;
  connection_status: OpenFinanceConnectionStatus;
  execution_status: string;
  last_sync_at: string | null;
  next_sync_at: string | null;
  connector_name: string | null;
  is_open_finance: boolean;
  refresh_status: "completed" | "started" | "recent" | "scheduled" | "needs_action" | "unavailable";
  refresh_detail: string;
  accounts: OpenFinanceAccount[];
  investments: OpenFinanceInvestment[];
  transactions: OpenFinanceTransaction[];
  cash_total_brl: number;
  credit_balance_brl: number;
  investments_total_brl: number;
}

interface OpenFinanceResponse {
  generated_at: string;
  window_hours: number;
  window_start: string;
  source: string;
  refresh_requested: boolean;
  banks: OpenFinanceBank[];
  cash_total_brl: number;
  credit_balance_brl: number;
  investments_total_brl: number;
  errors: string[];
  methodology: Record<string, string>;
}

interface ReportItem {
  name: string;
  path: string;
  updated_at: string;
  size: string;
}

interface OnePagerReport {
  symbol: string;
  company_name: string;
  market: "B3" | "US";
  currency: string;
  filename: string;
  generated_at: string;
  source: string;
  methodology_name: string;
  methodology_version: number;
  price: number;
  c3po_tp: number;
  consensus_tp: number | null;
  buy_in: number;
  upside_percent: number;
  confidence: number;
  method_count: number;
  download_url: string;
}

type ValuationTrigger = "initial" | "financial_results" | "material_event" | "web_research" | "market_data" | "methodology";

interface ValuationChangeRecord {
  id: string;
  snapshot_id: string | null;
  market: "B3" | "NASDAQ" | "NYSE" | "US";
  symbol: string;
  company_name: string;
  logo_url: string | null;
  changed_at: string;
  trigger_type: ValuationTrigger;
  trigger_title: string;
  trigger_summary: string;
  source_name: string;
  source_url: string | null;
  currency: string;
  old_tp: number | null;
  new_tp: number;
  tp_change_percent: number | null;
  old_buy_in: number | null;
  new_buy_in: number | null;
  old_consensus_tp: number | null;
  new_consensus_tp: number | null;
  price: number | null;
  old_confidence: number | null;
  new_confidence: number | null;
  methodology_name: string;
  methodology_version: number | null;
  metadata: Record<string, unknown>;
}

interface ValuationChangeResponse {
  generated_at: string;
  total: number;
  item_count: number;
  items: ValuationChangeRecord[];
}

type InvestorRelationsSource = "cvm" | "sec" | "ri";
type InvestorRelationsStatus = "pending_review" | "incorporated" | "informational";

interface InvestorRelationsEvent {
  id: string;
  source: InvestorRelationsSource;
  market: "B3" | "US";
  symbol: string | null;
  company_name: string;
  regulator_id: string | null;
  event_type: string;
  form: string | null;
  title: string;
  summary: string;
  published_at: string;
  published_time_precision: "datetime" | "date" | "collected";
  reference_date: string | null;
  official_url: string;
  document_url: string | null;
  materiality: "high" | "medium" | "low";
  valuation_relevant: boolean;
  valuation_status: InvestorRelationsStatus;
  reviewed_at: string | null;
  review_note: string;
  collected_at: string;
}

interface InvestorRelationsSourceHealth {
  code: InvestorRelationsSource;
  name: string;
  status: "healthy" | "attention" | "unconfigured";
  last_success_at: string | null;
  last_error: string | null;
  detail: string;
}

interface InvestorRelationsResponse {
  generated_at: string;
  total_events: number;
  today_events: number;
  pending_reviews: number;
  high_materiality: number;
  monitored_companies: number;
  items: InvestorRelationsEvent[];
  sources: InvestorRelationsSourceHealth[];
  methodology: Record<string, string>;
}

interface GlobalSearchCompany {
  symbol: string;
  symbols: string[];
  company_name: string;
  market: "B3" | "US";
  exchange: string | null;
  ri_url: string | null;
}

interface GlobalSearchValuation {
  id: string;
  symbol: string;
  company_name: string;
  market: "B3" | "US";
  trigger_title: string;
  changed_at: string;
  currency: string;
  old_tp: number | null;
  new_tp: number;
}

interface GlobalSearchDocument {
  id: string;
  symbol: string | null;
  company_name: string;
  market: "B3" | "US";
  source: InvestorRelationsSource;
  event_type: string;
  title: string;
  published_at: string;
  official_url: string;
}

interface GlobalSearchResponse {
  generated_at: string;
  query: string;
  companies: GlobalSearchCompany[];
  valuations: GlobalSearchValuation[];
  documents: GlobalSearchDocument[];
}

type GlobalSearchGroup = "navigation" | "actions" | "companies" | "valuations" | "documents";

interface GlobalSearchResult {
  id: string;
  group: GlobalSearchGroup;
  title: string;
  subtitle: string;
  meta?: string;
  view: ViewKey;
  query?: string;
  icon: ComponentType<{ size?: number }>;
  instrument?: InstrumentPreviewDescriptor;
}

const API_URL = process.env.NEXT_PUBLIC_C3PO_API_URL ?? "http://localhost:8000";

function useR2D2LivePositions() {
  const [telemetry, setTelemetry] = useState<R2D2LivePositionsData | null>(null);
  const requestInFlight = useRef(false);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      if (requestInFlight.current) return;
      requestInFlight.current = true;
      try {
        const response = await fetch(`${API_URL}/api/v1/r2d2/live-positions`, {
          cache: "no-store",
          credentials: "include"
        });
        if (!response.ok) return;
        const payload: R2D2LivePositionsData = await response.json();
        if (!mounted) return;
        setTelemetry((current) => {
          if (current && Date.parse(payload.generated_at) < Date.parse(current.generated_at)) return current;
          return payload;
        });
      } catch {
        // Keep the last valid marks visible while the full dashboard remains available.
      } finally {
        requestInFlight.current = false;
      }
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void load();
    };

    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 1_000);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      mounted = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return telemetry;
}

function MillenniumFalconIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="millennium-falcon-icon"
      height={size}
      src="/millennium-falcon-mark.png"
      width={size}
    />
  );
}

function C3POProtocolIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="c3po-protocol-icon"
      height={size}
      src="/c3po-protocol-mark.svg"
      width={size}
    />
  );
}

function TatooineNewsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="tatooine-news-icon"
      height={size}
      src="/tatooine-news-mark.png"
      width={size}
    />
  );
}

function RebellionNewsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="rebellion-news-icon"
      height={size}
      src="/rebellion-news-mark.png?v=2"
      width={size}
    />
  );
}

function MasterLukeIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="master-luke-icon"
      height={size}
      src="/master-luke-mark.svg"
      width={size}
    />
  );
}

function LaserPagerIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="laser-pager-icon"
      height={size}
      src="/laser-pager-mark.svg"
      width={size}
    />
  );
}

function LastJediIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="last-jedi-icon"
      height={size}
      src="/last-jedi-mark.svg"
      width={size}
    />
  );
}

function BenKenobiRecordsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="ben-kenobi-records-icon"
      height={size}
      src="/ben-kenobi-records-mark.svg?v=2"
      width={size}
    />
  );
}

function RadarAlertsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="radar-alerts-icon"
      height={size}
      src="/radar-alerts-mark.png"
      width={size}
    />
  );
}

function DagobahWeatherIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="dagobah-weather-icon"
      height={size}
      src="/dagobah-weather-mark.svg"
      width={size}
    />
  );
}

function DarkSideIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="dark-side-icon"
      height={size}
      src="/dark-side-mark.svg"
      width={size}
    />
  );
}

function ChewieFundamentalsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="chewie-fundamentals-icon"
      height={size}
      src="/chewie-fundamentals-mark.svg"
      width={size}
    />
  );
}

function HyperspaceIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="hyperspace-icon"
      height={size}
      src="/hyperspace-mark.svg"
      width={size}
    />
  );
}

function StormTroopsIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="storm-troops-icon"
      height={size}
      src="/storm-troops-mark.svg"
      width={size}
    />
  );
}

function DeathStarIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="death-star-icon"
      height={size}
      src="/death-star-mark.svg"
      width={size}
    />
  );
}

function TieFighterUsageIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="tie-fighter-usage-icon"
      height={size}
      src="/tie-fighter-usage-mark.svg"
      width={size}
    />
  );
}

function MidiChloriansFinanceIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="midi-chlorians-finance-icon"
      height={size}
      src="/midi-chlorians-finance-mark.svg"
      width={size}
    />
  );
}

function R2D2RisingIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="r2d2-rising-icon"
      height={size}
      src="/r2d2-rising-mark.svg"
      width={size}
    />
  );
}

function LeahCloudIcon({ size = 24 }: { size?: number }) {
  return (
    <img
      alt=""
      aria-hidden="true"
      className="leah-cloud-icon"
      height={size}
      src="/nina-castro-mark.svg?v=1"
      width={size}
    />
  );
}

const navItems: { key: ViewKey; label: string; icon: ComponentType<{ size?: number }> }[] = [
  { key: "command", label: "Falcon CAPCOM", icon: MillenniumFalconIcon },
  { key: "markets", label: "Master Luke", icon: MasterLukeIcon },
  { key: "realtime", label: "Hyperspace", icon: HyperspaceIcon },
  { key: "weather", label: "Dagobah Weather", icon: DagobahWeatherIcon },
  { key: "relations", label: "Tatooine Updates", icon: TatooineNewsIcon },
  { key: "news", label: "Rebellion News", icon: RebellionNewsIcon },
  { key: "r2d2", label: "R2D2 Rising", icon: R2D2RisingIcon },
  { key: "candidates", label: "Last Jedi", icon: LastJediIcon },
  { key: "matrix", label: "Dark Side", icon: DarkSideIcon },
  { key: "chewie", label: "Chewie Fundamentals", icon: ChewieFundamentalsIcon },
  { key: "onepager", label: "Laser Pager", icon: LaserPagerIcon },
  { key: "intelligence", label: "Ben Kenobi Records", icon: BenKenobiRecordsIcon },
  { key: "finance", label: "Midi-Chlorians Finance", icon: MidiChloriansFinanceIcon },
  { key: "alerts", label: "Radar Alerts", icon: RadarAlertsIcon },
  { key: "health", label: "Storm Troops", icon: StormTroopsIcon },
  { key: "serverusage", label: "TIE Fighter Usage", icon: TieFighterUsageIcon },
  { key: "leah", label: "Leah Cloud", icon: LeahCloudIcon }
];

const viewIcons: Record<ViewKey, ComponentType<{ size?: number }>> = {
  home: C3POProtocolIcon,
  command: MillenniumFalconIcon,
  markets: MasterLukeIcon,
  realtime: HyperspaceIcon,
  weather: DagobahWeatherIcon,
  portfolio: BriefcaseBusiness,
  relations: TatooineNewsIcon,
  news: RebellionNewsIcon,
  r2d2: R2D2RisingIcon,
  candidates: LastJediIcon,
  matrix: DarkSideIcon,
  chewie: ChewieFundamentalsIcon,
  onepager: LaserPagerIcon,
  intelligence: BenKenobiRecordsIcon,
  finance: MidiChloriansFinanceIcon,
  alerts: RadarAlertsIcon,
  health: StormTroopsIcon,
  serverusage: TieFighterUsageIcon,
  leah: LeahCloudIcon,
  helm: DeathStarIcon
};

const helmNavItem: { key: ViewKey; label: string; icon: ComponentType<{ size?: number }> } = {
  key: "helm",
  label: "Death Star",
  icon: DeathStarIcon
};

const viewTitles: Record<ViewKey, { title: string; eyebrow: string }> = {
  home: { title: "C3PO", eyebrow: "Chief of Staff Intelligence" },
  command: { title: "Falcon CAPCOM", eyebrow: "Mission control · R2D2 performance and live market intelligence" },
  markets: { title: "Master Luke", eyebrow: "Protocol intelligence · Near-real-time market console" },
  realtime: { title: "Hyperspace", eyebrow: "Protocol intelligence · Market-wide leaders" },
  weather: { title: "Dagobah Weather", eyebrow: "Atmospheric intelligence · 24-hour operational forecast" },
  portfolio: { title: "Portfolio", eyebrow: "Protocol intelligence · Positions and allocation" },
  relations: { title: "Tatooine Updates", eyebrow: "Official intelligence · CVM First + SEC EDGAR + issuer RI" },
  news: { title: "Rebellion News", eyebrow: "Galactic briefing · Brazil and global headlines" },
  r2d2: { title: "R2D2 Rising", eyebrow: "Paper trading laboratory · Governed strategy validation" },
  candidates: { title: "Last Jedi", eyebrow: "Protocol intelligence · Versioned opportunity set" },
  matrix: { title: "Dark Side", eyebrow: "Protocol intelligence · Live risk-return field" },
  chewie: { title: "Chewie Fundamentals", eyebrow: "Protocol intelligence · Company fundamentals across markets" },
  onepager: { title: "Laser Pager", eyebrow: "Protocol intelligence · On-demand equity research" },
  intelligence: { title: "Ben Kenobi Records", eyebrow: "Valuation intelligence · Permanent audit trail" },
  finance: { title: "Midi-Chlorians Finance", eyebrow: "Protocol intelligence · Banking and investments" },
  alerts: { title: "Radar Alerts", eyebrow: "Protocol intelligence · Exceptions requiring attention" },
  health: { title: "Storm Troops", eyebrow: "Operational readiness · Services, sources and scheduled jobs" },
  serverusage: { title: "TIE Fighter Usage", eyebrow: "AWS telemetry · Lightsail infrastructure" },
  leah: { title: "Leah Cloud", eyebrow: "Personal cloud · Agenda and tasks" },
  helm: { title: "Death Star", eyebrow: "Access control · Authorized crew and module permissions" }
};

const marketLabels: Record<string, string> = {
  Index: "Indices",
  Currencies: "Currencies",
  CRIPTO: "Crypto"
};

const matrixQuadrants: { key: MatrixQuadrant; label: string; shortLabel: string }[] = [
  { key: "high_return_low_risk", label: "High TP upside · Low risk", shortLabel: "Power zone" },
  { key: "high_return_high_risk", label: "High TP upside · High risk", shortLabel: "Aggressive" },
  { key: "low_return_low_risk", label: "Low TP upside · Low risk", shortLabel: "Defensive" },
  { key: "low_return_high_risk", label: "Low TP upside · High risk", shortLabel: "Avoid zone" }
];

function DirectionIcon({ direction, size = 15 }: { direction: Direction; size?: number }) {
  if (direction === "up") return <TrendingUp size={size} aria-label="up" />;
  if (direction === "down") return <TrendingDown size={size} aria-label="down" />;
  return <Activity size={size} aria-label="flat" />;
}

function formatDate(value?: string) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatNewsAge(value: string | null) {
  if (!value) return "Horário não informado";
  const published = new Date(value);
  if (Number.isNaN(published.getTime())) return value;
  const minutes = Math.max(0, Math.round((Date.now() - published.getTime()) / 60000));
  if (minutes < 2) return "Agora";
  if (minutes < 60) return `Há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Há ${hours}h`;
  const days = Math.floor(hours / 24);
  return `Há ${days}d`;
}

function formatRecordDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatBrl(value: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: currency === "BRL" ? "BRL" : "USD"
  }).format(value);
}

function formatPositionPercentMagnitude(returnPercent: number) {
  return Math.abs(returnPercent).toFixed(3);
}

function formatResearchPrice(value: number, market: ResearchMarket) {
  return formatCurrency(value, market === "B3" ? "BRL" : "USD");
}

function formatIntradayPrice(value: number, currency: string, market: string) {
  if (["Indices", "Future Index", "Index"].includes(market)) {
    return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
  }
  if (market === "Currencies") {
    return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 6 }).format(value);
  }
  try {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: value < 0.01 ? 8 : 2
    }).format(value);
  } catch {
    return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 8 }).format(value);
  }
}

function formatPercent(value: number | null, digits = 1) {
  if (value === null) return "N/D";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits).replace(".", ",")}%`;
}

function formatMultiple(value: number | null) {
  return value === null ? "N/M" : `${value.toFixed(1).replace(".", ",")}x`;
}

function formatCompact(value: number | null) {
  if (value === null) return "N/D";
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatCompactMoney(value: number | null, market: ResearchMarket) {
  if (value === null) return "N/D";
  const prefix = market === "B3" ? "R$" : "US$";
  return `${prefix} ${new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
}

function formatBytes(value: number | null) {
  if (value === null) return "N/D";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit >= 3 ? 1 : 0).replace(".", ",")} ${units[unit]}`;
}

function formatLiveMarketPrice(item: LiveMarketItem) {
  const digits = item.group === "Currencies" ? 4 : ["US3Y", "US10Y"].includes(item.symbol) ? 3 : item.symbol === "BONK" ? 8 : ["SOL", "DOGE"].includes(item.symbol) ? 4 : 2;
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(item.price);
}

function normalizeSearchText(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

function currentViewQuery() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("q")?.trim() ?? "";
}

function GlobalSearch({
  session,
  items,
  onNavigate,
  onSessionExpired
}: {
  session: AuthSession;
  items: { key: ViewKey; label: string; icon: ComponentType<{ size?: number }> }[];
  onNavigate: (view: ViewKey, realtimeTab?: RealtimeTabKey, query?: string) => void;
  onSessionExpired: () => void;
}) {
  const [query, setQuery] = useState("");
  const [remote, setRemote] = useState<GlobalSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const normalized = normalizeSearchText(query);
  const permissions = useMemo(() => new Set(session.permissions), [session.permissions]);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", focusSearch);
    window.addEventListener("pointerdown", closeOnOutsideClick);
    return () => {
      window.removeEventListener("keydown", focusSearch);
      window.removeEventListener("pointerdown", closeOnOutsideClick);
    };
  }, []);

  useEffect(() => {
    if (normalized.length < 2) {
      setRemote(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const debounce = window.setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q: query.trim() });
        const response = await fetch(`${API_URL}/api/v1/search?${params.toString()}`, {
          cache: "no-store",
          credentials: "include",
          signal: controller.signal
        });
        if (response.status === 401) {
          onSessionExpired();
          return;
        }
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
        setRemote(payload);
      } catch (requestError) {
        if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setRemote(null);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 240);
    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [normalized, onSessionExpired, query]);

  const sections = useMemo(() => {
    const navigation: GlobalSearchResult[] = normalized.length < 2 ? [] : items
      .filter((item) => normalizeSearchText(`${item.label} ${viewTitles[item.key].title} ${viewTitles[item.key].eyebrow}`).includes(normalized))
      .slice(0, 5)
      .map((item) => ({
        id: `nav-${item.key}`,
        group: "navigation",
        title: item.label,
        subtitle: viewTitles[item.key].eyebrow,
        view: item.key,
        icon: item.icon
      }));

    const compactTicker = query.trim().toUpperCase().replace(/\s/g, "");
    const looksLikeTicker = /^(?:[A-Z]{1,5}|[A-Z]{3,6}[0-9]{1,2}|[A-Z]{1,5}\.[A-Z])$/.test(compactTicker);
    const actions: GlobalSearchResult[] = [];
    if (looksLikeTicker && permissions.has("onepager")) {
      actions.push({
        id: `action-onepager-${compactTicker}`,
        group: "actions",
        title: `Gerar One Pager de ${compactTicker}`,
        subtitle: "Abrir o research engine com o ticker preenchido",
        view: "onepager",
        query: compactTicker,
        icon: LaserPagerIcon
      });
    }
    if (looksLikeTicker && permissions.has("intelligence")) {
      actions.push({
        id: `action-iq-${compactTicker}`,
        group: "actions",
        title: `Histórico de valuation de ${compactTicker}`,
        subtitle: "Abrir as alterações mais recentes no Ben Kenobi Records",
        view: "intelligence",
        query: compactTicker,
        icon: BenKenobiRecordsIcon
      });
    }
    if (looksLikeTicker && permissions.has("relations")) {
      actions.push({
        id: `action-ir-${compactTicker}`,
        group: "actions",
        title: `Documentos oficiais de ${compactTicker}`,
        subtitle: "Abrir fatos e resultados na Tatooine Updates",
        view: "relations",
        query: compactTicker,
        icon: TatooineNewsIcon
      });
    }

    const companyDestination: ViewKey = permissions.has("onepager")
      ? "onepager"
      : permissions.has("intelligence")
        ? "intelligence"
        : permissions.has("relations")
          ? "relations"
          : permissions.has("matrix")
            ? "matrix"
            : "candidates";
    const companies: GlobalSearchResult[] = (remote?.companies ?? []).map((company) => ({
      id: `company-${company.market}-${company.symbol}`,
      group: "companies",
      title: `${company.symbol} · ${company.company_name}`,
      subtitle: `${company.market}${company.exchange ? ` · ${company.exchange}` : ""}`,
      meta: company.symbols.length > 1 ? company.symbols.join(" · ") : undefined,
      view: companyDestination,
      query: company.symbol,
      icon: Building2,
      instrument: { symbol: company.symbol, name: company.company_name, market: company.market }
    }));
    const valuations: GlobalSearchResult[] = (remote?.valuations ?? []).map((valuation) => ({
      id: `valuation-${valuation.id}`,
      group: "valuations",
      title: `${valuation.symbol} · ${valuation.company_name}`,
      subtitle: valuation.trigger_title,
      meta: `C3PO TP ${formatCurrency(valuation.new_tp, valuation.currency)}`,
      view: "intelligence",
      query: valuation.symbol,
      icon: BenKenobiRecordsIcon,
      instrument: { symbol: valuation.symbol, name: valuation.company_name, market: valuation.market }
    }));
    const documents: GlobalSearchResult[] = (remote?.documents ?? []).map((document) => ({
      id: `document-${document.id}`,
      group: "documents",
      title: document.title,
      subtitle: `${document.symbol || document.company_name} · ${document.event_type}`,
      meta: formatDate(document.published_at),
      view: "relations",
      query: document.symbol || document.company_name,
      icon: TatooineNewsIcon,
      instrument: document.symbol
        ? { symbol: document.symbol, name: document.company_name, market: document.market }
        : undefined
    }));

    return [
      { key: "navigation" as const, label: "Navegação", items: navigation },
      { key: "actions" as const, label: "Ações rápidas", items: actions },
      { key: "companies" as const, label: "Empresas", items: companies },
      { key: "valuations" as const, label: "Ben Kenobi Records", items: valuations },
      { key: "documents" as const, label: "Tatooine Updates", items: documents }
    ].filter((section) => section.items.length);
  }, [items, normalized, permissions, query, remote]);

  const allResults = sections.flatMap((section) => section.items);

  useEffect(() => {
    setActiveIndex(0);
  }, [normalized, remote]);

  const chooseResult = (result: GlobalSearchResult) => {
    onNavigate(result.view, undefined, result.query);
    setQuery("");
    setRemote(null);
    setOpen(false);
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!allResults.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % allResults.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + allResults.length) % allResults.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseResult(allResults[activeIndex] ?? allResults[0]);
    }
  };

  const showResults = open && normalized.length >= 2;
  let resultOffset = 0;
  return (
    <div className="global-search" ref={containerRef}>
      <div className={showResults ? "search-wrap search-wrap-active" : "search-wrap"}>
        <Search size={17} />
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Buscar empresa, tela ou comando"
          aria-label="Busca universal"
          aria-expanded={showResults}
          aria-controls="global-search-results"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
        />
        {loading ? <RefreshCw size={15} className="spin global-search-spinner" /> : query ? (
          <button type="button" className="global-search-clear" onClick={() => { setQuery(""); setRemote(null); inputRef.current?.focus(); }} aria-label="Limpar busca">
            <X size={14} />
          </button>
        ) : null}
      </div>
      {showResults && (
        <div className="global-search-results" id="global-search-results" role="listbox">
          {sections.map((section) => {
            const startIndex = resultOffset;
            resultOffset += section.items.length;
            return (
              <section className="global-search-section" key={section.key}>
                <header><span>{section.label}</span><small>{section.items.length}</small></header>
                {section.items.map((result, index) => {
                  const Icon = result.icon;
                  const flatIndex = startIndex + index;
                  return (
                    <button
                      type="button"
                      className={activeIndex === flatIndex ? "global-search-result global-search-result-active" : "global-search-result"}
                      key={result.id}
                      onClick={() => chooseResult(result)}
                      onMouseEnter={() => setActiveIndex(flatIndex)}
                      role="option"
                      aria-selected={activeIndex === flatIndex}
                    >
                      <i><Icon size={18} /></i>
                      <span>
                        <strong>
                          {result.instrument ? (
                            <InstrumentPreviewTarget instrument={result.instrument} nested pinOnClick={false}>
                              {result.title}
                            </InstrumentPreviewTarget>
                          ) : result.title}
                        </strong>
                        <small>{result.subtitle}</small>
                      </span>
                      {result.meta && <em>{result.meta}</em>}
                      <ChevronRight size={15} />
                    </button>
                  );
                })}
              </section>
            );
          })}
          {!allResults.length && !loading && <div className="global-search-empty"><Search size={18} /><span>Nenhum resultado encontrado</span></div>}
        </div>
      )}
    </div>
  );
}

const capabilityLabels: Record<AccessCapabilityKey, string> = {
  read: "Leitura dos dados autorizados",
  onepager_generate: "Geração de One Pagers",
  delete: "Exclusão de dados"
};

function profileInitials(displayName?: string | null, email?: string | null) {
  return displayName?.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase()
    || email?.slice(0, 2).toUpperCase()
    || "C3";
}

function hasNinaCastroMark(displayName?: string | null, email?: string | null) {
  const normalizedName = (displayName ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
  const emailName = (email ?? "").split("@")[0].replace(/[._-]+/g, " ").trim().toLowerCase();
  return normalizedName === "nina castro" || emailName === "nina" || emailName === "nina castro";
}

function hasEduardoCastroMark(displayName?: string | null, email?: string | null) {
  const normalizedName = (displayName ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
  const normalizedEmail = (email ?? "").trim().toLowerCase();
  return normalizedName === "eduardo castro" || normalizedEmail === "eu@eduardocastro.com.br";
}

function UserAvatar({
  displayName,
  email,
  className
}: {
  displayName?: string | null;
  email?: string | null;
  className?: string;
}) {
  const ninaMark = hasNinaCastroMark(displayName, email);
  const eduardoMark = hasEduardoCastroMark(displayName, email);
  const customMark = ninaMark || eduardoMark;
  return (
    <div className={`${className ?? ""}${customMark ? " user-avatar-mark" : ""}`.trim()}>
      {eduardoMark
        ? <img alt="Eduardo Castro" src="/eduardo-castro-mark.svg?v=1" />
        : ninaMark
        ? <img alt="Nina Castro" src="/nina-castro-mark.svg?v=1" />
        : profileInitials(displayName, email)}
    </div>
  );
}

interface TotpSetupData {
  secret: string;
  otpauth_uri: string;
  qr_code_data_url: string;
  expires_in_seconds: number;
}

function TotpSecurityPanel({ initiallyEnabled }: { initiallyEnabled: boolean }) {
  const [enabled, setEnabled] = useState(initiallyEnabled);
  const [setup, setSetup] = useState<TotpSetupData | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const beginSetup = async (replace = false) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/totp/${replace ? "reconfigure" : "setup"}`, { method: "POST", credentials: "include" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível iniciar a configuração.");
      setSetup(payload);
      setCode("");
    } catch (setupError) {
      setError(setupError instanceof Error ? setupError.message : "Não foi possível iniciar a configuração.");
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (action: "confirm" | "disable") => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/totp/${action}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Código inválido.");
      setEnabled(payload.enabled);
      setSetup(null);
      setCode("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Código inválido.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="profile-panel-section profile-totp">
      <div className="profile-panel-section-title"><LockKeyhole size={15} /><span>Código automático no Safari</span></div>
      {!enabled && !setup && (
        <div className="profile-totp-status">
          <div><span>APP SENHAS</span><strong>Não configurado</strong></div>
          <button type="button" onClick={() => void beginSetup()} disabled={busy}>Ativar</button>
        </div>
      )}
      {setup && (
        <div className="profile-totp-setup">
          <img src={setup.qr_code_data_url} alt="QR Code para configurar o código no app Senhas" />
          <div>
            <strong>Escaneie com a câmera do iPhone</strong>
            <p>Ou abra Senhas no Mac, selecione o C3PO e use a chave abaixo.</p>
            <code>{setup.secret}</code>
            <div className="profile-totp-code">
              <input aria-label="Código de confirmação" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" />
              <button type="button" onClick={() => void submitCode("confirm")} disabled={busy || code.length !== 6}>Confirmar</button>
            </div>
          </div>
        </div>
      )}
      {enabled && !setup && (
        <div className="profile-totp-enabled">
          <div><i /><span><strong>Ativo</strong><small>O Safari pode preencher o código salvo no app Senhas.</small></span></div>
          <button type="button" onClick={() => void beginSetup(true)} disabled={busy}>Configurar novo autenticador</button>
          <div className="profile-totp-code">
            <input aria-label="Código para desativar" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="Código atual" />
            <button type="button" onClick={() => void submitCode("disable")} disabled={busy || code.length !== 6}>Desativar</button>
          </div>
        </div>
      )}
      {error && <p className="profile-totp-error">{error}</p>}
    </section>
  );
}

function normalizeCompanyLogoUrl(value?: string | null) {
  const clean = value?.trim();
  if (!clean) return "";
  if (clean.startsWith("//")) return `https:${clean}`;
  if (clean.startsWith("/")) return `https://eodhd.com${clean}`;
  return clean;
}

function CompanyLogo({ logoUrl, symbol, market }: { logoUrl?: string | null; symbol: string; market?: string }) {
  const normalizedSymbol = symbol.trim().toUpperCase();
  const isB3 = market?.trim().toUpperCase() === "B3";
  const sources = useMemo(() => Array.from(new Set([
    normalizeCompanyLogoUrl(logoUrl),
    isB3 ? `https://financialmodelingprep.com/image-stock/${encodeURIComponent(normalizedSymbol)}.SA.png` : "",
    `/api/v1/company-logo/${encodeURIComponent(normalizedSymbol)}`,
    `https://eodhd.com/img/logos/US/${normalizedSymbol.toLowerCase()}.png`,
    `https://financialmodelingprep.com/image-stock/${encodeURIComponent(normalizedSymbol)}.png`
  ].filter(Boolean))), [isB3, logoUrl, normalizedSymbol]);
  const [sourceIndex, setSourceIndex] = useState(0);
  useEffect(() => setSourceIndex(0), [sources.join("|")]);
  return sources[sourceIndex]
    ? <img src={sources[sourceIndex]} alt="" onError={() => setSourceIndex((current) => current + 1)} />
    : <span>{symbol.slice(0, 2)}</span>;
}

function ProfilePanel({
  session,
  items,
  onClose,
  onLogout
}: {
  session: AuthSession;
  items: typeof navItems;
  onClose: () => void;
  onLogout: () => void;
}) {
  const roleLabel = session.is_admin ? "Proprietário · Administrador" : "Usuário autorizado";
  const sessionPolicy = session.is_admin
    ? "Expiração diária"
    : `Expira após ${Math.round((session.idle_timeout_seconds ?? 3600) / 60)} min de inatividade`;

  return (
    <>
      <button className="profile-panel-backdrop" type="button" onClick={onClose} aria-label="Fechar perfil" />
      <aside className="profile-panel" role="dialog" aria-modal="true" aria-labelledby="profile-panel-title">
        <header className="profile-panel-head">
          <UserAvatar className="profile-panel-avatar" displayName={session.display_name} email={session.email} />
          <div>
            <span>ACTIVE SESSION</span>
            <h2 id="profile-panel-title">{session.display_name || session.email}</h2>
            <p>{session.email}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar perfil"><X size={18} /></button>
        </header>

        <div className="profile-status-strip">
          <span><i />Sessão autenticada</span>
          <strong>{roleLabel}</strong>
        </div>

        <section className="profile-panel-section">
          <div className="profile-panel-section-title"><Users size={15} /><span>Identidade e sessão</span></div>
          <div className="profile-detail-grid">
            <div><span>Perfil</span><strong>{roleLabel}</strong></div>
            <div><span>Política da sessão</span><strong>{sessionPolicy}</strong></div>
            <div><span>Início da sessão</span><strong>{session.session_started_at ? formatRecordDate(session.session_started_at) : "Não disponível"}</strong></div>
            <div><span>Última atividade</span><strong>{session.last_activity_at || session.session_started_at ? formatRecordDate(session.last_activity_at || session.session_started_at || "") : "Não disponível"}</strong></div>
            <div><span>Validade</span><strong>{session.expires_at ? formatRecordDate(session.expires_at) : "Sessão local"}</strong></div>
            <div><span>Endereço IP</span><strong>{session.ip_address || "Não identificado"}</strong></div>
          </div>
        </section>

        <section className="profile-panel-section">
          <div className="profile-panel-section-title"><Cpu size={15} /><span>Dispositivo conectado</span></div>
          <div className="profile-device-list">
            <div><span>Tipo de máquina</span><strong>{session.device_type || "Não identificado"}</strong></div>
            <div><span>Sistema operacional</span><strong>{session.operating_system || "Não identificado"}</strong></div>
            <div><span>Navegador</span><strong>{session.browser || "Não identificado"}</strong></div>
          </div>
        </section>

        <section className="profile-panel-section">
          <div className="profile-panel-section-title"><Command size={15} /><span>Abas autorizadas · {items.length}</span></div>
          <div className="profile-permission-list">
            {items.map((item) => <span key={item.key}>{item.label}</span>)}
          </div>
        </section>

        <section className="profile-panel-section">
          <div className="profile-panel-section-title"><ShieldCheck size={15} /><span>Permissões operacionais</span></div>
          <div className="profile-capability-list">
            {session.capabilities.map((capability) => (
              <div key={capability}><ShieldCheck size={14} /><span>{capabilityLabels[capability]}</span></div>
            ))}
          </div>
        </section>

        <TotpSecurityPanel initiallyEnabled={session.totp_enabled} />

        <div className="profile-panel-actions">
          <button type="button" onClick={() => { onClose(); onLogout(); }}>
            <LogOut size={16} />
            <span>Sair do C3PO</span>
          </button>
        </div>

        <footer className="profile-panel-foot">
          O navegador informa a categoria do dispositivo, sistema e versão. O modelo exato do equipamento pode ser ocultado pelo próprio sistema por privacidade.
        </footer>
      </aside>
    </>
  );
}

interface InstrumentPreviewContextValue {
  activeKey: string | null;
  open: (instrument: InstrumentPreviewDescriptor, anchor: HTMLElement, pinned: boolean) => void;
  scheduleClose: () => void;
  cancelClose: () => void;
}

const InstrumentPreviewContext = createContext<InstrumentPreviewContextValue | null>(null);

function instrumentPreviewKey(instrument: InstrumentPreviewDescriptor) {
  return `${instrument.market ?? "AUTO"}:${instrument.symbol}`.toUpperCase();
}

function InstrumentPreviewProvider({ children }: { children: ReactNode }) {
  const [preview, setPreview] = useState<{
    instrument: InstrumentPreviewDescriptor;
    left: number;
    top: number;
    width: number;
    pinned: boolean;
  } | null>(null);
  const [cache, setCache] = useState<Record<string, RealtimePortfolioIntradayResponse>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const popoverRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<number | null>(null);
  const pendingRef = useRef<Set<string>>(new Set());

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const loadIntraday = useCallback(async (instrument: InstrumentPreviewDescriptor) => {
    const key = instrumentPreviewKey(instrument);
    if (cache[key] || pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    setLoading((current) => ({ ...current, [key]: true }));
    setErrors((current) => ({ ...current, [key]: "" }));
    try {
      const params = new URLSearchParams({ symbol: instrument.symbol, name: instrument.name });
      if (instrument.market) params.set("market", instrument.market);
      const response = await fetch(`${API_URL}/api/v1/market-data/intraday?${params.toString()}`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload: RealtimePortfolioIntradayResponse & { detail?: string } = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setCache((current) => ({ ...current, [key]: payload }));
    } catch (requestError) {
      setErrors((current) => ({
        ...current,
        [key]: requestError instanceof Error ? requestError.message : "Gráfico intradiário indisponível"
      }));
    } finally {
      pendingRef.current.delete(key);
      setLoading((current) => ({ ...current, [key]: false }));
    }
  }, [cache]);

  const open = useCallback((instrument: InstrumentPreviewDescriptor, anchor: HTMLElement, pinned: boolean) => {
    cancelClose();
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(390, window.innerWidth - 24);
    const estimatedHeight = 326;
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const top = window.innerHeight - rect.bottom >= estimatedHeight + 12
      ? rect.bottom + 9
      : Math.max(10, rect.top - estimatedHeight - 9);
    setPreview({ instrument, left, top, width, pinned });
    void loadIntraday(instrument);
  }, [cancelClose, loadIntraday]);

  const scheduleClose = useCallback(() => {
    if (preview?.pinned) return;
    cancelClose();
    closeTimerRef.current = window.setTimeout(() => setPreview(null), 140);
  }, [cancelClose, preview?.pinned]);

  useEffect(() => {
    const closePinnedPreview = (event: PointerEvent) => {
      if (!preview?.pinned) return;
      const target = event.target as Element;
      if (popoverRef.current?.contains(target) || target.closest(".instrument-preview-target")) return;
      setPreview(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreview(null);
    };
    const closeOnViewportChange = () => {
      if (!preview?.pinned) setPreview(null);
    };
    window.addEventListener("pointerdown", closePinnedPreview);
    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("resize", closeOnViewportChange);
    window.addEventListener("scroll", closeOnViewportChange, true);
    return () => {
      window.removeEventListener("pointerdown", closePinnedPreview);
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("resize", closeOnViewportChange);
      window.removeEventListener("scroll", closeOnViewportChange, true);
      if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current);
    };
  }, [preview?.pinned]);

  const activeKey = preview ? instrumentPreviewKey(preview.instrument) : null;
  const contextValue = useMemo(() => ({ activeKey, open, scheduleClose, cancelClose }), [activeKey, cancelClose, open, scheduleClose]);

  return (
    <InstrumentPreviewContext.Provider value={contextValue}>
      {children}
      {preview && typeof document !== "undefined" && createPortal(
        <RealtimePortfolioIntradayPreview
          ref={popoverRef}
          item={preview.instrument}
          data={cache[activeKey ?? ""]}
          loading={!!loading[activeKey ?? ""]}
          error={errors[activeKey ?? ""]}
          position={{ left: preview.left, top: preview.top, width: preview.width }}
          pinned={preview.pinned}
          onClose={() => setPreview(null)}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        />,
        document.body
      )}
    </InstrumentPreviewContext.Provider>
  );
}

function InstrumentPreviewTarget({
  instrument,
  children,
  className = "",
  showIcon = true,
  nested = false,
  pinOnClick = true,
  as = "span"
}: {
  instrument: InstrumentPreviewDescriptor;
  children: ReactNode;
  className?: string;
  showIcon?: boolean;
  nested?: boolean;
  pinOnClick?: boolean;
  as?: "span" | "div" | "article";
}) {
  const preview = useContext(InstrumentPreviewContext);
  const key = instrumentPreviewKey(instrument);
  const interactiveProps = nested ? {} : { role: "button", tabIndex: 0 };
  const Tag = as;
  return (
    <Tag
      {...interactiveProps}
      className={`instrument-preview-target ${className}`.trim()}
      onMouseEnter={(event) => preview?.open(instrument, event.currentTarget, false)}
      onMouseLeave={() => preview?.scheduleClose()}
      onFocus={(event) => preview?.open(instrument, event.currentTarget, false)}
      onBlur={() => preview?.scheduleClose()}
      onClick={pinOnClick ? (event) => preview?.open(instrument, event.currentTarget, true) : undefined}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          preview?.open(instrument, event.currentTarget, true);
        }
      }}
      aria-label={`Ver gráfico intradiário de ${instrument.symbol}`}
      aria-expanded={preview?.activeKey === key}
    >
      {children}
      {showIcon && <LineChart className="instrument-preview-icon" size={13} aria-hidden="true" />}
    </Tag>
  );
}

function AppShell({ session, onLogout, onSessionExpired }: { session: AuthSession; onLogout: () => void; onSessionExpired: () => void }) {
  const [data, setData] = useState<CommandCenterData | null>(null);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [marketProviders, setMarketProviders] = useState<MarketDataProvider[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealthData | null>(null);
  const visibleNavItems = useMemo(() => {
    const allowed = new Set(session.permissions);
    const items = navItems.filter((item) => allowed.has(item.key));
    const authorizedItems = session.is_admin ? [...items, helmNavItem] : items;
    return authorizedItems.sort((left, right) => {
      if (left.key === "command") return -1;
      if (right.key === "command") return 1;
      return left.label.localeCompare(right.label, "pt-BR", { sensitivity: "base" });
    });
  }, [session.is_admin, session.permissions]);
  const [activeView, setActiveView] = useState<ViewKey>(() => {
    if (typeof window === "undefined") return "command";
    const requested = new URLSearchParams(window.location.search).get("view");
    if (requested === "home") return "home";
    if (visibleNavItems.some((item) => item.key === requested)) return requested as ViewKey;
    if (visibleNavItems.some((item) => item.key === "command")) return "command";
    return visibleNavItems[0]?.key ?? "home";
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [viewRevision, setViewRevision] = useState(0);
  const [pageLoadStats, setPageLoadStats] = useState<PageLoadPerformanceStats>({
    totalMs: 0,
    apiWaitMs: 0,
    backendMs: 0,
    renderMs: 0,
    requestCount: 0,
    count: 0
  });
  const pageLoadTrackerRef = useRef<{
    startedAt: number;
    inFlight: number;
    quietTimer: number | null;
    apiIntervals: { startedAt: number; endedAt: number }[];
    backendTotalMs: number;
    requestCount: number;
  } | null>(null);
  const [financeRefreshKey, setFinanceRefreshKey] = useState(0);
  const [activeAlertCount, setActiveAlertCount] = useState(0);
  const [navigationIndicators, setNavigationIndicators] = useState<NavigationIndicatorsData | null>(null);
  const ActiveViewIcon = viewIcons[activeView];

  const completePageLoadMeasurement = useCallback((tracker: NonNullable<typeof pageLoadTrackerRef.current>) => {
    if (pageLoadTrackerRef.current !== tracker) return;
    const durationMs = Math.max(0, window.performance.now() - tracker.startedAt);
    const intervals = [...tracker.apiIntervals].sort((left, right) => left.startedAt - right.startedAt);
    let apiWaitMs = 0;
    let intervalStart = intervals[0]?.startedAt ?? 0;
    let intervalEnd = intervals[0]?.endedAt ?? 0;
    intervals.slice(1).forEach((interval) => {
      if (interval.startedAt <= intervalEnd) intervalEnd = Math.max(intervalEnd, interval.endedAt);
      else {
        apiWaitMs += intervalEnd - intervalStart;
        intervalStart = interval.startedAt;
        intervalEnd = interval.endedAt;
      }
    });
    if (intervals.length) apiWaitMs += intervalEnd - intervalStart;
    const renderMs = Math.max(0, durationMs - apiWaitMs);
    pageLoadTrackerRef.current = null;
    setPageLoadStats((current) => ({
      totalMs: current.totalMs + durationMs,
      apiWaitMs: current.apiWaitMs + apiWaitMs,
      backendMs: current.backendMs + (tracker.requestCount ? tracker.backendTotalMs / tracker.requestCount : 0),
      renderMs: current.renderMs + renderMs,
      requestCount: current.requestCount + tracker.requestCount,
      count: current.count + 1
    }));
  }, []);

  const schedulePageLoadCompletion = useCallback((tracker: NonNullable<typeof pageLoadTrackerRef.current>) => {
    if (pageLoadTrackerRef.current !== tracker || tracker.inFlight > 0) return;
    if (tracker.quietTimer !== null) window.clearTimeout(tracker.quietTimer);
    tracker.quietTimer = window.setTimeout(() => completePageLoadMeasurement(tracker), 250);
  }, [completePageLoadMeasurement]);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (async (...args: Parameters<typeof window.fetch>) => {
      const tracker = pageLoadTrackerRef.current;
      const requestStartedAt = window.performance.now();
      let response: Response | undefined;
      if (tracker) {
        if (tracker.quietTimer !== null) window.clearTimeout(tracker.quietTimer);
        tracker.quietTimer = null;
        tracker.inFlight += 1;
      }
      try {
        response = await originalFetch(...args);
        return response;
      } finally {
        if (tracker && pageLoadTrackerRef.current === tracker) {
          const requestEndedAt = window.performance.now();
          tracker.apiIntervals.push({ startedAt: requestStartedAt, endedAt: requestEndedAt });
          tracker.requestCount += 1;
          const backendMs = Number.parseFloat(response?.headers.get("X-Response-Time-Ms") ?? "");
          if (Number.isFinite(backendMs)) tracker.backendTotalMs += backendMs;
          tracker.inFlight = Math.max(0, tracker.inFlight - 1);
          schedulePageLoadCompletion(tracker);
        }
      }
    }) as typeof window.fetch;

    return () => {
      window.fetch = originalFetch;
      const tracker = pageLoadTrackerRef.current;
      if (tracker?.quietTimer !== null && tracker?.quietTimer !== undefined) window.clearTimeout(tracker.quietTimer);
      pageLoadTrackerRef.current = null;
    };
  }, [schedulePageLoadCompletion]);

  useEffect(() => {
    if (!session.idle_timeout_seconds) return;

    const idleTimeoutMs = session.idle_timeout_seconds * 1000;
    const heartbeatIntervalMs = 5 * 60 * 1000;
    let idleTimer = 0;
    let lastHeartbeatAt = 0;
    let heartbeatInFlight = false;

    const expireLocalSession = () => onSessionExpired();
    const sendActivityHeartbeat = async () => {
      if (heartbeatInFlight) return;
      heartbeatInFlight = true;
      lastHeartbeatAt = Date.now();
      try {
        const response = await fetch(`${API_URL}/api/v1/auth/activity`, {
          method: "POST",
          cache: "no-store",
          credentials: "include"
        });
        if (response.status === 401) expireLocalSession();
      } catch {
        // A transient network failure must not log out an otherwise valid session.
      } finally {
        heartbeatInFlight = false;
      }
    };
    const registerActivity = () => {
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(expireLocalSession, idleTimeoutMs);
      if (Date.now() - lastHeartbeatAt >= heartbeatIntervalMs) void sendActivityHeartbeat();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") registerActivity();
    };
    const activityEvents: (keyof WindowEventMap)[] = ["pointerdown", "keydown", "touchstart", "scroll"];
    activityEvents.forEach((eventName) => window.addEventListener(eventName, registerActivity, { passive: true }));
    document.addEventListener("visibilitychange", handleVisibility);
    registerActivity();

    return () => {
      window.clearTimeout(idleTimer);
      activityEvents.forEach((eventName) => window.removeEventListener(eventName, registerActivity));
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [onSessionExpired, session.idle_timeout_seconds]);

  useEffect(() => {
    if (!profileOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setProfileOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [profileOpen]);

  const refreshNotificationState = useCallback(async () => {
    const allowed = new Set(session.permissions);
    const needsAlerts = allowed.has("alerts");
    const needsFeedIndicators = allowed.has("relations") || allowed.has("intelligence");
    try {
      const [alertsResponse, indicators…55198 tokens truncated… 18} textAnchor="middle">{formatWeatherHour(hour.time)}</text> : null)}
      <text className="weather-chart-rain-label" x={width - right} y={top - 10} textAnchor="end">CHUVA 0–100%</text>
    </svg>
  );
}

function WeatherConditionIcon({ code, size = 20 }: { code: number | null; size?: number }) {
  if (code === 0) return <Sun size={size} />;
  if (code === 1 || code === 2) return <CloudSun size={size} />;
  if (code === 3) return <Cloud size={size} />;
  if (code === 45 || code === 48) return <CloudFog size={size} />;
  if (code !== null && [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return <CloudRain size={size} />;
  if (code !== null && [71, 73, 75, 77, 85, 86].includes(code)) return <Snowflake size={size} />;
  if (code !== null && [95, 96, 99].includes(code)) return <CloudLightning size={size} />;
  return <CloudSun size={size} />;
}

function WeatherLoading() {
  return <div className="weather-loading"><div /><div /><div /></div>;
}

function formatTemperature(value: number | null) {
  return value === null ? "N/D" : `${value.toFixed(1).replace(".", ",")}°C`;
}

function formatProbability(value: number | null) {
  return value === null ? "N/D" : `${Math.round(value)}%`;
}

function formatKnots(value: number | null) {
  return value === null ? "N/D" : `${value.toFixed(1).replace(".", ",")} kts`;
}

function formatWind(value: number | null, direction: string) {
  return `${direction} · ${formatKnots(value)}`;
}

function formatRain(value: number | null) {
  return value === null ? "N/D" : `${value.toFixed(1).replace(".", ",")} mm`;
}

function formatWeatherHour(value: string) {
  const match = value.match(/T(\d{2}:\d{2})/);
  return match?.[1] ?? value;
}

function FinanceView({ refreshKey }: { refreshKey: number }) {
  const [snapshot, setSnapshot] = useState<OpenFinanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadFinance = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/open-finance?hours=36&refresh=true`, {
        cache: "no-store",
        credentials: "include"
      });
      if (response.status === 401) {
        window.location.reload();
        return;
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Pluggy API ${response.status}`);
      }
      setSnapshot(await response.json());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível consultar o Pluggy.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFinance();
  }, [loadFinance, refreshKey]);

  if (loading && !snapshot) {
    return <div className="open-finance-loading"><div /><div /><div /><div /></div>;
  }

  return (
    <div className="content-stack">
      <section className="panel open-finance-overview">
        <div className="open-finance-overview-head">
          <div>
            <span className="table-kicker">OPEN FINANCE SYNC</span>
            <strong>Pluggy Banking Snapshot</strong>
            <small>{snapshot ? `Consultado ${formatDate(snapshot.generated_at)} · janela móvel de ${snapshot.window_hours} horas` : "Fonte indisponível"}</small>
          </div>
          <button className="open-finance-refresh" onClick={loadFinance} disabled={loading}>
            <RefreshCw size={16} className={loading ? "spin" : ""} />
            <span>{loading ? "Atualizando" : "Atualizar agora"}</span>
          </button>
        </div>
        {error && <div className="open-finance-error"><AlertTriangle size={16} /><span>{error}</span></div>}
        {snapshot && (
          <div className="open-finance-summary">
            <FinanceMetric label="Instituições" value={`${snapshot.banks.filter((bank) => bank.connection_status !== "offline").length}/3`} detail="BTG · Santander · Itaú" />
            <FinanceMetric label="Saldo em contas" value={formatBrl(snapshot.cash_total_brl)} detail="Contas correntes em BRL" negative={snapshot.cash_total_brl < 0} />
            <FinanceMetric label="Investimentos" value={formatBrl(snapshot.investments_total_brl)} detail="Posição bruta informada" />
            <FinanceMetric label="Faturas abertas" value={formatBrl(snapshot.credit_balance_brl)} detail="Separadas do saldo em conta" />
          </div>
        )}
      </section>

      {snapshot?.banks.map((bank) => <OpenFinanceBankSection key={bank.code} bank={bank} />)}

      {snapshot && (
        <div className="open-finance-footnote">
          <ShieldCheck size={15} />
          <span>{snapshot.methodology.refresh}</span>
          <small>{snapshot.methodology.privacy}</small>
        </div>
      )}
    </div>
  );
}

function FinanceMetric({ label, value, detail, negative = false }: { label: string; value: string; detail: string; negative?: boolean }) {
  return <div><span>{label}</span><strong className={negative ? "money-negative" : ""}>{value}</strong><small>{detail}</small></div>;
}

function OpenFinanceBankSection({ bank }: { bank: OpenFinanceBank }) {
  const bankAccounts = bank.accounts.filter((account) => account.product === "BANK");
  const creditAccounts = bank.accounts.filter((account) => account.product === "CREDIT");
  const statusLabels: Record<OpenFinanceConnectionStatus, string> = {
    healthy: "Conectado",
    syncing: "Sincronizando",
    attention: "Requer atenção",
    offline: "Indisponível"
  };
  return (
    <section className="panel open-finance-bank">
      <header className="open-finance-bank-head">
        <div className={`open-finance-bank-logo bank-logo-${bank.code}`} aria-label={`Logo ${bank.name}`}>
          {bank.code === "btg" ? "BTG" : bank.code === "santander" ? "S" : "itaú"}
        </div>
        <div className="open-finance-bank-title">
          <span>{bank.name}</span>
          <strong>{formatBrl(bank.cash_total_brl)} em contas · {formatBrl(bank.investments_total_brl)} investidos</strong>
          <small>
            {bank.refresh_detail} Última sincronização: {formatDate(bank.last_sync_at ?? undefined)}.
            {bank.connector_name ? ` Conector: ${bank.connector_name}${bank.is_open_finance ? " · Open Finance direto" : " · conexão intermediária"}.` : ""}
          </small>
        </div>
        <span className={`open-finance-status finance-status-${bank.connection_status}`}><i />{statusLabels[bank.connection_status]}</span>
      </header>

      <div className="open-finance-account-grid">
        <div className="open-finance-product-group">
          <div className="open-finance-section-title"><Building2 size={15} /><strong>Contas e saldos</strong><span>{bankAccounts.length}</span></div>
          <div className="open-finance-account-list">
            {bankAccounts.map((account) => (
              <div className="open-finance-account-row" key={account.id}>
                <div><strong>{account.name}</strong><span>{account.display_number} · Conta corrente</span></div>
                <strong className={account.balance < 0 ? "money-negative" : ""}>{formatCurrency(account.balance, account.currency)}</strong>
              </div>
            ))}
            {!bankAccounts.length && <EmptyLine label="Nenhuma conta corrente retornada" />}
          </div>
        </div>
        <div className="open-finance-product-group">
          <div className="open-finance-section-title"><WalletCards size={15} /><strong>Cartões e faturas</strong><span>{creditAccounts.length}</span></div>
          <div className="open-finance-account-list">
            {creditAccounts.map((account) => (
              <div className="open-finance-account-row" key={account.id}>
                <div><strong>{account.name}</strong><span>{account.display_number}{account.due_date ? ` · vence ${formatShortDate(account.due_date)}` : ""}</span></div>
                <strong>{formatCurrency(account.balance, account.currency)}</strong>
              </div>
            ))}
            {!creditAccounts.length && <EmptyLine label="Nenhum cartão retornado" />}
          </div>
        </div>
      </div>

      <div className="open-finance-block">
        <div className="open-finance-section-title"><BriefcaseBusiness size={15} /><strong>Investimentos</strong><span>{bank.investments.length}</span></div>
        <div className="open-finance-investment-head"><span>Ativo</span><span>Tipo</span><span>Data-base</span><span>Posição bruta</span><span>Posição líquida</span></div>
        {bank.investments.map((investment) => (
          <div className="open-finance-investment-row" key={investment.id}>
            <div><strong>{investment.name}</strong><small>{investment.status}</small></div>
            <span data-label="Tipo">{formatFinanceProduct(investment.type)}</span>
            <span data-label="Data-base">{investment.as_of ? formatDate(investment.as_of) : "N/D"}</span>
            <strong data-label="Posição bruta">{formatCurrency(investment.gross_value, investment.currency)}</strong>
            <span data-label="Posição líquida">{investment.net_value === null ? "N/D" : formatCurrency(investment.net_value, investment.currency)}</span>
          </div>
        ))}
        {!bank.investments.length && <EmptyLine label="O Pluggy não retornou posições ativas para esta conexão" />}
      </div>

      <div className="open-finance-block open-finance-statement">
        <div className="open-finance-section-title"><Activity size={15} /><strong>Extrato das últimas 36 horas</strong><span>{bank.transactions.length}</span></div>
        <div className="open-finance-transaction-head"><span>Data e hora</span><span>Conta</span><span>Descrição</span><span>Status</span><span>Valor</span></div>
        {bank.transactions.map((transaction) => (
          <div className="open-finance-transaction-row" key={transaction.id}>
            <span data-label="Data e hora">{formatFinanceTimestamp(transaction.transaction_at)}</span>
            <div data-label="Conta"><strong>{transaction.account_name}</strong><small>{transaction.account_number}</small></div>
            <div className="open-finance-transaction-description" data-label="Descrição"><strong>{transaction.description}</strong><small>{transaction.category}</small></div>
            <span data-label="Status" className={`transaction-status status-${transaction.status.toLowerCase()}`}>{formatFinanceStatus(transaction.status)}</span>
            <strong data-label="Valor" className={transaction.amount < 0 ? "money-negative" : transaction.amount > 0 ? "money-positive" : ""}>{formatCurrency(transaction.amount, transaction.currency)}</strong>
          </div>
        ))}
        {!bank.transactions.length && <EmptyLine label="Sem movimentações nesta conexão nas últimas 36 horas" />}
      </div>
    </section>
  );
}

function formatShortDate(value: string) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(date);
}

function formatFinanceTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatFinanceProduct(value: string) {
  const labels: Record<string, string> = { EQUITY: "Ações", FIXED_INCOME: "Renda fixa", MUTUAL_FUND: "Fundos", SECURITY: "Títulos" };
  return labels[value] ?? value.replaceAll("_", " ");
}

function formatFinanceStatus(value: string) {
  const labels: Record<string, string> = { POSTED: "Efetivada", PENDING: "Pendente", ACTIVE: "Ativo" };
  return labels[value] ?? value;
}

function AlertsView({ onRead }: { onRead: (count: number) => void }) {
  const [data, setData] = useState<AlertsData | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const dataRef = useRef<AlertsData | null>(null);
  const pendingReadIds = useRef(new Set<string>());

  const commitData = useCallback((nextData: AlertsData) => {
    dataRef.current = nextData;
    setData(nextData);
    onRead(nextData.unread_count);
  }, [onRead]);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/v1/alerts`, { cache: "no-store", credentials: "include" })
      .then(async (response) => {
        const payload: AlertsData = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
        if (!active) return;
        commitData({
          ...payload,
          unread_count: payload.items.filter((item) => !item.is_read).length
        });
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "Alerts unavailable");
      });
    return () => { active = false; };
  }, [commitData]);

  const markAlertRead = useCallback(async (alertId: string) => {
    const current = dataRef.current;
    const target = current?.items.find((item) => item.id === alertId);
    if (!current || !target || target.is_read || pendingReadIds.current.has(alertId)) return;

    pendingReadIds.current.add(alertId);
    setReadError("");
    const optimisticItems = current.items.map((item) => item.id === alertId ? { ...item, is_read: true } : item);
    commitData({
      ...current,
      unread_count: optimisticItems.filter((item) => !item.is_read).length,
      items: optimisticItems
    });

    try {
      const response = await fetch(`${API_URL}/api/v1/alerts/read`, {
        method: "POST",
        cache: "no-store",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_ids: [alertId] })
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
    } catch (requestError) {
      const latest = dataRef.current;
      if (latest) {
        const restoredItems = latest.items.map((item) => item.id === alertId ? { ...item, is_read: false } : item);
        commitData({
          ...latest,
          unread_count: restoredItems.filter((item) => !item.is_read).length,
          items: restoredItems
        });
      }
      setReadError(requestError instanceof Error ? `Não foi possível registrar a leitura: ${requestError.message}` : "Não foi possível registrar a leitura.");
    } finally {
      pendingReadIds.current.delete(alertId);
    }
  }, [commitData]);

  const toggleAlert = useCallback((item: AlertItem) => {
    const opening = expandedId !== item.id;
    setExpandedId(opening ? item.id : null);
    if (opening && !item.is_read) void markAlertRead(item.id);
  }, [expandedId, markAlertRead]);

  if (error) return <div className="error-banner"><AlertTriangle size={18} /><span>{error}</span></div>;
  if (!data) return <LoadingState />;
  const stale = data.status !== "fresh";
  const staleAlert: AlertItem | null = stale ? {
    id: "stale-snapshot",
    severity: "High",
    subject: "Legacy snapshot is stale",
    context: "A fonte principal não foi atualizada dentro da janela esperada.",
    action: `Last source update: ${formatDate(data.generated_at)}`,
    source: "Legacy Summary Adapter",
    occurred_at: data.generated_at,
    metadata: {},
    is_read: true
  } : null;
  const displayedAlerts = [...data.items, ...(staleAlert ? [staleAlert] : [])]
    .sort((left, right) => Date.parse(right.occurred_at ?? "") - Date.parse(left.occurred_at ?? ""));
  const totalPages = Math.max(1, Math.ceil(displayedAlerts.length / ALERTS_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const firstAlert = displayedAlerts.length ? ((currentPage - 1) * ALERTS_PAGE_SIZE) + 1 : 0;
  const lastAlert = Math.min(currentPage * ALERTS_PAGE_SIZE, displayedAlerts.length);
  const paginatedAlerts = displayedAlerts.slice(firstAlert ? firstAlert - 1 : 0, lastAlert);
  const changePage = (nextPage: number) => {
    setExpandedId(null);
    setPage(Math.max(1, Math.min(totalPages, nextPage)));
  };
  return (
    <section className="panel">
      <PanelHeader title="Active Alerts" icon={RadarAlertsIcon} />
      {readError && <div className="screen-error"><AlertTriangle size={16} /><span>{readError}</span></div>}
      <div className="alert-list">
        {paginatedAlerts.map((item) => <AlertRow key={item.id} item={item} expanded={expandedId === item.id} onToggle={() => toggleAlert(item)} />)}
        {!displayedAlerts.length && <EmptyLine label="No active alerts" />}
      </div>
      {displayedAlerts.length > ALERTS_PAGE_SIZE && (
        <footer className="iq-records-pagination" aria-label="Paginação dos alertas">
          <div>
            <strong>{firstAlert}–{lastAlert}</strong>
            <span>de {displayedAlerts.length} alertas</span>
          </div>
          <div className="iq-pagination-controls">
            <button type="button" onClick={() => changePage(currentPage - 1)} disabled={currentPage === 1} aria-label="Página anterior" title="Página anterior">
              <ChevronLeft size={16} />
            </button>
            <span>Página <strong>{currentPage}</strong> de {totalPages}</span>
            <button type="button" onClick={() => changePage(currentPage + 1)} disabled={currentPage === totalPages} aria-label="Próxima página" title="Próxima página">
              <ChevronRight size={16} />
            </button>
          </div>
        </footer>
      )}
    </section>
  );
}

function InvestorRelationsView({ canManage }: { canManage: boolean }) {
  const [feed, setFeed] = useState<InvestorRelationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [market, setMarket] = useState<"all" | "B3" | "US">("all");
  const [source, setSource] = useState<"all" | InvestorRelationsSource>("all");
  const [eventType, setEventType] = useState("all");
  const [scope, setScope] = useState<"coverage" | "all">("coverage");
  const [search, setSearch] = useState(() => currentViewQuery());
  const [watchSymbol, setWatchSymbol] = useState("");
  const [watchMarket, setWatchMarket] = useState<"B3" | "US">("B3");
  const [watchName, setWatchName] = useState("");
  const [watchUrl, setWatchUrl] = useState("");
  const [feedPage, setFeedPage] = useState(1);
  const [expandedFeedEventId, setExpandedFeedEventId] = useState<string | null>(null);
  const pageSize = 30;

  const feedUrl = useMemo(() => {
    const params = new URLSearchParams({ limit: "300" });
    params.set("scope", scope);
    if (market !== "all") params.set("market", market);
    if (source !== "all") params.set("source", source);
    if (eventType !== "all") params.set("event_type", eventType);
    if (search.trim()) params.set("q", search.trim());
    return `${API_URL}/api/v1/investor-relations?${params.toString()}`;
  }, [eventType, market, scope, search, source]);

  useEffect(() => setFeedPage(1), [eventType, market, scope, search, source]);

  const visibleFeedItems = useMemo(
    () => (feed?.items ?? []).slice((feedPage - 1) * pageSize, feedPage * pageSize),
    [feed, feedPage],
  );
  const feedPageCount = Math.max(1, Math.ceil((feed?.items.length ?? 0) / pageSize));

  const loadFeed = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError("");
    try {
      const response = await fetch(feedUrl, { cache: "no-store", credentials: "include" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setFeed(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar o feed oficial.");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [feedUrl]);

  useEffect(() => {
    const debounce = window.setTimeout(() => loadFeed(), 220);
    const interval = window.setInterval(() => loadFeed(true), 60_000);
    return () => {
      window.clearTimeout(debounce);
      window.clearInterval(interval);
    };
  }, [loadFeed]);

  const syncNow = async () => {
    if (!canManage) return;
    setSyncing(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/investor-relations/sync`, {
        method: "POST",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "A sincronização não foi concluída.");
      await loadFeed(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "A sincronização não foi concluída.");
    } finally {
      setSyncing(false);
    }
  };

  const addWatch = async (event: FormEvent) => {
    event.preventDefault();
    if (!canManage) return;
    if (!watchSymbol.trim()) return;
    setSyncing(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/investor-relations/watchlist`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: watchSymbol.trim().toUpperCase(),
          market: watchMarket,
          company_name: watchName.trim(),
          ri_url: watchUrl.trim() || null
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível adicionar a empresa.");
      setFeed(payload);
      setWatchSymbol("");
      setWatchName("");
      setWatchUrl("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível adicionar a empresa.");
    } finally {
      setSyncing(false);
    }
  };

  const reviewEvent = async (id: string) => {
    if (!canManage) return;
    setSyncing(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/investor-relations/events/${id}/review`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: "Reviewed in C3PO Tatooine Updates" })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível concluir a revisão.");
      setFeed(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível concluir a revisão.");
    } finally {
      setSyncing(false);
    }
  };

  const reportUrl = useMemo(() => {
    const params = new URLSearchParams();
    params.set("scope", scope);
    if (market !== "all") params.set("market", market);
    if (source !== "all") params.set("source", source);
    if (eventType !== "all") params.set("event_type", eventType);
    if (search.trim()) params.set("q", search.trim());
    return `${API_URL}/api/v1/investor-relations/report.pdf${params.size ? `?${params.toString()}` : ""}`;
  }, [eventType, market, scope, search, source]);

  const eventTypes = [
    "Material Fact", "Financial Results", "Market Notice", "Shareholder Notice",
    "Board Decision", "Material Filing", "Issuer Material Update"
  ];

  return (
    <div className="content-stack investor-relations-view">
      <section className="panel ir-command-panel">
        <div className="ir-summary-grid">
          <div><span>Official events</span><strong>{feed?.total_events ?? "—"}</strong><small>historical disclosures collected</small></div>
          <div><span>Today</span><strong>{feed?.today_events ?? "—"}</strong><small>new filings and issuer updates</small></div>
          <div className={feed?.pending_reviews ? "ir-summary-alert" : ""}><span>Pending review</span><strong>{feed?.pending_reviews ?? "—"}</strong><small>TP validation temporarily restricted</small></div>
          <div><span>High materiality</span><strong>{feed?.high_materiality ?? "—"}</strong><small>results and material filings</small></div>
          <div><span>Companies</span><strong>{feed?.monitored_companies ?? "—"}</strong><small>CVM, SEC and RI issuer registry</small></div>
        </div>
        <div className="ir-toolbar">
          <div className="ir-filter-group" aria-label="Coverage scope">
            <button className={scope === "coverage" ? "ir-filter-active" : ""} onClick={() => setScope("coverage")}>C3PO coverage</button>
            <button className={scope === "all" ? "ir-filter-active" : ""} onClick={() => setScope("all")}>All filings</button>
          </div>
          <div className="ir-filter-group" aria-label="Market filter">
            {(["all", "B3", "US"] as const).map((item) => (
              <button key={item} className={market === item ? "ir-filter-active" : ""} onClick={() => setMarket(item)}>{item === "all" ? "All markets" : item}</button>
            ))}
          </div>
          <div className="ir-filter-group" aria-label="Source filter">
            {(["all", "cvm", "sec", "ri"] as const).map((item) => (
              <button key={item} className={source === item ? "ir-filter-active" : ""} onClick={() => setSource(item)}>{item === "all" ? "All sources" : item.toUpperCase()}</button>
            ))}
          </div>
          <select value={eventType} onChange={(event) => setEventType(event.target.value)} aria-label="Event type">
            <option value="all">All event types</option>
            {eventTypes.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <div className="ir-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Company, ticker or filing" /></div>
          {canManage && <button className="ir-action ir-action-secondary" onClick={syncNow} disabled={syncing}><RefreshCw size={15} className={syncing ? "spin" : ""} /><span>{syncing ? "Syncing" : "Sync now"}</span></button>}
          <a className="ir-action ir-action-primary" href={reportUrl} target="_blank" rel="noreferrer"><FileDown size={15} /><span>PDF briefing</span></a>
        </div>
      </section>

      {error && <div className="screen-error"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => loadFeed()}>Retry</button></div>}

      <section className="ir-source-strip" aria-label="Tatooine Updates source health">
        {(feed?.sources ?? []).map((item) => (
          <article key={item.code}>
            <span className={`status-dot ${item.status === "healthy" ? "dot-good" : item.status === "attention" ? "dot-warning" : ""}`} />
            <div><strong>{item.name}</strong><span>{item.detail}</span></div>
            <small>{item.last_success_at ? formatDate(item.last_success_at) : item.status === "unconfigured" ? "Configure RI URL" : "Awaiting first sync"}</small>
          </article>
        ))}
      </section>

      <section className="panel ir-feed-panel">
        <PanelHeader title="Official disclosure feed" icon={TatooineNewsIcon} action={feed ? `${feed.items.length} records` : "Loading"} />
        <div className="ir-feed-head">
          <span>Source</span><span>Company</span><span>Disclosure</span><span>Published</span><span>CVM First</span><span>Document</span>
        </div>
        <div className="ir-feed-body">
          {loading && !feed ? <div className="ir-feed-loading" /> : visibleFeedItems.map((item) => (
            <article className={`ir-event-row${expandedFeedEventId === item.id ? " ir-event-row-expanded" : ""}`} key={item.id}>
              <div><span className={`ir-source-badge ir-source-${item.source}`}>{item.source.toUpperCase()}</span><small>{item.market}</small></div>
              <div className="ir-company-cell">{item.symbol ? <InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.company_name, market: item.market }}><strong>{item.symbol}</strong></InstrumentPreviewTarget> : <strong>{item.regulator_id ?? "Issuer"}</strong>}<span>{item.company_name}</span></div>
              <div className="ir-disclosure-cell"><strong>{item.title}</strong><span>{item.event_type}{item.form ? ` · ${item.form}` : ""}</span><small className={`ir-materiality ir-materiality-${item.materiality}`}>{item.materiality} materiality</small></div>
              <div className="ir-date-cell"><strong>{formatIrEventDate(item)}</strong><span>{item.reference_date ? `Ref. ${new Date(`${item.reference_date}T12:00:00`).toLocaleDateString("pt-BR")}` : "No reference period"}</span></div>
              <div className="ir-status-cell">
                <span className={`ir-valuation-status ir-valuation-${item.valuation_status}`}>{item.valuation_status.replace("_", " ")}</span>
                {canManage && item.valuation_status === "pending_review" && <button onClick={() => reviewEvent(item.id)} disabled={syncing}>Mark reviewed</button>}
              </div>
              <div className="ir-document-cell">
                {item.document_url ? (
                  <a href={item.document_url} target="_blank" rel="noreferrer" title="Open official filing" aria-label={`Open document for ${item.symbol ?? item.company_name}`}><ExternalLink size={15} /></a>
                ) : (
                  <button type="button" onClick={() => setExpandedFeedEventId((current) => current === item.id ? null : item.id)} title="Show collected information" aria-label={`Show collected information for ${item.symbol ?? item.company_name}`} aria-expanded={expandedFeedEventId === item.id}><FileChartColumn size={15} /></button>
                )}
              </div>
              {expandedFeedEventId === item.id && (
                <div className="ir-event-detail">
                  <strong>Collected information</strong>
                  <p>{item.summary || "No additional summary was returned by the provider."}</p>
                  <span>Source: {item.source.toUpperCase()} · collected {formatDate(item.collected_at)}</span>
                </div>
              )}
            </article>
          ))}
          {!loading && feed && !feed.items.length && <EmptyLine label="No official disclosures match these filters" />}
        </div>
        {feedPageCount > 1 && (
          <footer className="iq-records-pagination" aria-label="Paginação dos comunicados oficiais">
            <div><strong>{(feedPage - 1) * pageSize + 1}–{Math.min(feedPage * pageSize, feed?.items.length ?? 0)}</strong><span>de {feed?.items.length ?? 0} registros</span></div>
            <div className="iq-pagination-controls">
              <button type="button" onClick={() => setFeedPage((page) => Math.max(1, page - 1))} disabled={feedPage === 1} aria-label="Página anterior" title="Página anterior"><ChevronLeft size={16} /></button>
              <span>Página <strong>{feedPage}</strong> de {feedPageCount}</span>
              <button type="button" onClick={() => setFeedPage((page) => Math.min(feedPageCount, page + 1))} disabled={feedPage === feedPageCount} aria-label="Próxima página" title="Próxima página"><ChevronRight size={16} /></button>
            </div>
          </footer>
        )}
      </section>

      <section className="panel ir-watch-panel">
        <PanelHeader title="Issuer monitoring" icon={Target} />
        {canManage ? <form className="ir-watch-form" onSubmit={addWatch}>
          <label><span>Ticker</span><input value={watchSymbol} onChange={(event) => setWatchSymbol(event.target.value.toUpperCase())} placeholder="PRNR3 or AMZN" required /></label>
          <label><span>Market</span><select value={watchMarket} onChange={(event) => setWatchMarket(event.target.value as "B3" | "US")}><option>B3</option><option>US</option></select></label>
          <label><span>Company name</span><input value={watchName} onChange={(event) => setWatchName(event.target.value)} placeholder="Optional" /></label>
          <label><span>Official RI page</span><input value={watchUrl} onChange={(event) => setWatchUrl(event.target.value)} placeholder="https://ri.company.com" type="url" /></label>
          <button type="submit" disabled={syncing}><Plus size={15} /><span>Add monitoring</span></button>
        </form> : <div className="ir-readonly-note"><LockKeyhole size={16} /><span>Acesso para leitura: alterações na cobertura são exclusivas do proprietário.</span></div>}
        <div className="ir-method-note"><ShieldCheck size={16} /><p>Official filings can suspend TP validation. Financial periods reconcile automatically; qualitative material events require review before the model is considered current again.</p></div>
      </section>
    </div>
  );
}

function formatIrEventDate(event: InvestorRelationsEvent) {
  const date = new Date(event.published_at);
  if (event.published_time_precision === "date") {
    return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric", timeZone: "America/Sao_Paulo" }).format(date);
  }
  const formatted = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" }).format(date);
  return event.published_time_precision === "collected" ? `First seen ${formatted}` : formatted;
}

const SERVER_CHART = { width: 1000, height: 330, left: 56, right: 22, top: 22, bottom: 42 };

function serverChartX(index: number, length: number) {
  const width = SERVER_CHART.width - SERVER_CHART.left - SERVER_CHART.right;
  return SERVER_CHART.left + (length <= 1 ? 0 : index / (length - 1) * width);
}

function serverChartY(value: number) {
  const height = SERVER_CHART.height - SERVER_CHART.top - SERVER_CHART.bottom;
  return SERVER_CHART.top + (100 - Math.max(0, Math.min(100, value))) / 100 * height;
}

function serverChartSegments(points: ServerUsagePoint[], value: (point: ServerUsagePoint) => number | null) {
  const segments: string[] = [];
  let path = "";
  points.forEach((point, index) => {
    const current = value(point);
    if (current === null) {
      if (path) segments.push(path);
      path = "";
      return;
    }
    const command = path ? "L" : "M";
    path += `${command}${serverChartX(index, points.length).toFixed(2)},${serverChartY(current).toFixed(2)} `;
  });
  if (path) segments.push(path);
  return segments;
}

function formatServerTime(value: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo"
  }).format(new Date(value));
}

function formatPerformanceDuration(value: number | null) {
  if (value === null) return "N/D";
  return value < 1_000 ? `${Math.round(value)} ms` : `${(value / 1_000).toFixed(2).replace(".", ",")} s`;
}

function ServerUsageView({ pageLoadStats }: { pageLoadStats: PageLoadPerformanceStats }) {
  const [data, setData] = useState<ServerUsageResponse | null>(null);
  const [selectedServerId, setSelectedServerId] = useState("");
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/server-usage?hours=24`, {
        cache: "no-store",
        credentials: "include"
      });
      if (!response.ok) throw new Error(`API ${response.status}`);
      const payload: ServerUsageResponse = await response.json();
      setData(payload);
      setSelectedServerId((current) => current || payload.servers[0]?.server_id || "");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Telemetry unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const server = data?.servers.find((item) => item.server_id === selectedServerId) ?? data?.servers[0];
  const pageLoadAverageMs = pageLoadStats.count ? pageLoadStats.totalMs / pageLoadStats.count : null;
  const apiWaitAverageMs = pageLoadStats.count ? pageLoadStats.apiWaitMs / pageLoadStats.count : null;
  const backendAverageMs = pageLoadStats.count ? pageLoadStats.backendMs / pageLoadStats.count : null;
  const renderAverageMs = pageLoadStats.count ? pageLoadStats.renderMs / pageLoadStats.count : null;
  const requestsPerPage = pageLoadStats.count ? pageLoadStats.requestCount / pageLoadStats.count : null;
  const points = server?.history ?? [];
  const cpuPeak = points.reduce(
    (peak, point) => point.cpu_percent === null ? peak : Math.max(peak, point.cpu_percent),
    0
  );
  const cpuSegments = useMemo(
    () => serverChartSegments(points, (point) => point.cpu_moving_average_5m),
    [points]
  );
  const diskSegments = useMemo(
    () => serverChartSegments(points, (point) => point.disk_percent),
    [points]
  );
  const latestDiskIndex = points.reduce((latest, point, index) => point.disk_percent !== null ? index : latest, -1);
  const hovered = hoveredIndex === null ? null : points[hoveredIndex];
  const timeMarkers = points.length
    ? [0, .25, .5, .75, 1].map((ratio) => Math.min(points.length - 1, Math.round((points.length - 1) * ratio)))
    : [];

  if (loading && !data) {
    return <div className="server-usage-loading"><div /><div /><div /></div>;
  }

  if (!server) {
    return (
      <section className="panel server-usage-empty">
        <Server size={24} />
        <strong>{error ? "AWS telemetry unavailable" : "Waiting for the first server sample"}</strong>
        <button onClick={() => load()}><RefreshCw size={15} />Refresh</button>
      </section>
    );
  }

  return (
    <div className="content-stack server-usage-view">
      {error && <div className="error-banner"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => load()}>Retry</button></div>}

      <section className="panel server-usage-console">
        <header className="server-usage-head">
          <div className="server-usage-identity">
            <div className="server-usage-mark"><TieFighterUsageIcon size={30} /></div>
            <div><strong>{server.server_name}</strong><span>{server.region} · {server.cpu_count} vCPU</span></div>
          </div>
          <div className="server-usage-actions">
            {data && data.servers.length > 1 && (
              <div className="server-usage-tabs">
                {data.servers.map((item) => <button className={item.server_id === server.server_id ? "active" : ""} onClick={() => setSelectedServerId(item.server_id)} key={item.server_id}>{item.server_name}</button>)}
              </div>
            )}
            <span className={`server-status server-status-${server.status}`}><i />{server.status}</span>
            <button className="server-refresh" onClick={() => load()} disabled={loading} title="Refresh server telemetry"><RefreshCw size={16} className={loading ? "spin" : ""} /></button>
          </div>
        </header>

        <div className="server-usage-metrics">
          <div><span><Cpu size={15} />CPU now</span><strong>{server.current.cpu_percent === null ? "N/D" : `${server.current.cpu_percent.toFixed(1).replace(".", ",")}%`}</strong><small>Host aggregate</small></div>
          <div><span><Activity size={15} />CPU Peak</span><strong>{points.length ? `${cpuPeak.toFixed(1).replace(".", ",")}%` : "N/D"}</strong><small>Highest · last 24 hours</small></div>
          <div><span><HardDrive size={15} />Disk used</span><strong>{server.current.disk_percent === null ? "N/D" : `${server.current.disk_percent.toFixed(1).replace(".", ",")}%`}</strong><small>{formatBytes(server.current.disk_used_bytes)} of {formatBytes(server.current.disk_total_bytes)}</small></div>
          <div><span><HardDrive size={15} />Disk free</span><strong>{formatBytes(server.current.disk_free_bytes)}</strong><small>Project filesystem</small></div>
          <div><span><Gauge size={15} />Load Page Time</span><strong>{formatPerformanceDuration(pageLoadAverageMs)}</strong><small>{pageLoadStats.count ? `Average of ${pageLoadStats.count} internal page${pageLoadStats.count === 1 ? "" : "s"}` : "Opening presentation excluded"}</small></div>
          <div><span><Activity size={15} />API wait</span><strong>{formatPerformanceDuration(apiWaitAverageMs)}</strong><small>{requestsPerPage === null ? "No page samples" : `${requestsPerPage.toFixed(1).replace(".", ",")} requests per page`}</small></div>
          <div><span><Server size={15} />Backend work</span><strong>{formatPerformanceDuration(backendAverageMs)}</strong><small>Average processing time per response</small></div>
          <div><span><PanelsTopLeft size={15} />Render & UI</span><strong>{formatPerformanceDuration(renderAverageMs)}</strong><small>Total minus active API wait</small></div>
        </div>

        <section className="server-api-performance">
          <header>
            <div><span>API PERFORMANCE</span><strong>Slowest endpoints</strong></div>
            <small>Rolling {data?.api_window_minutes ?? 15} min · ordered by p95</small>
          </header>
          <div className="server-api-table">
            <div className="server-api-row server-api-row-head"><span>Endpoint</span><span>Requests</span><span>Average</span><span>P95</span><span>Errors</span></div>
            {(data?.api_endpoints ?? []).slice(0, 8).map((endpoint) => (
              <div className="server-api-row" key={`${endpoint.method}-${endpoint.route}`}>
                <strong><em>{endpoint.method}</em>{endpoint.route}</strong>
                <span>{endpoint.request_count.toLocaleString("pt-BR")}</span>
                <span>{formatPerformanceDuration(endpoint.average_ms)}</span>
                <span>{formatPerformanceDuration(endpoint.p95_ms)}</span>
                <span className={endpoint.error_percent > 0 ? "error" : ""}>{endpoint.error_percent.toFixed(1).replace(".", ",")}%</span>
              </div>
            ))}
            {!data?.api_endpoints.length && <div className="server-api-empty">Collecting the first API samples.</div>}
          </div>
        </section>

        <div className="server-chart-head">
          <div><span>INFRASTRUCTURE LOAD</span><strong>Last 24 hours</strong></div>
          <div className="server-chart-legend"><span><i className="cpu" />CPU · MA 5 min</span><span><i className="disk" />Disk used</span></div>
        </div>

        <div className="server-chart-wrap">
          <svg
            className="server-chart"
            viewBox={`0 0 ${SERVER_CHART.width} ${SERVER_CHART.height}`}
            role="img"
            aria-label="CPU moving average and disk usage over the last 24 hours"
            onPointerMove={(event) => {
              if (!points.length) return;
              const bounds = event.currentTarget.getBoundingClientRect();
              const relative = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
              setHoveredIndex(Math.round(relative * (points.length - 1)));
            }}
            onPointerLeave={() => setHoveredIndex(null)}
          >
            {[0, 25, 50, 75, 100].map((value) => (
              <g key={value}>
                <line className="server-chart-grid" x1={SERVER_CHART.left} x2={SERVER_CHART.width - SERVER_CHART.right} y1={serverChartY(value)} y2={serverChartY(value)} />
                <text className="server-chart-y-label" x={SERVER_CHART.left - 12} y={serverChartY(value) + 4} textAnchor="end">{value}%</text>
              </g>
            ))}
            {timeMarkers.map((index) => (
              <text className="server-chart-x-label" key={`${points[index].collected_at}-${index}`} x={serverChartX(index, points.length)} y={SERVER_CHART.height - 10} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}>{formatServerTime(points[index].collected_at)}</text>
            ))}
            {cpuSegments.map((path, index) => <path className="server-chart-line server-chart-line-cpu" d={path} key={`cpu-${index}`} />)}
            {diskSegments.map((path, index) => <path className="server-chart-line server-chart-line-disk" d={path} key={`disk-${index}`} />)}
            {latestDiskIndex >= 0 && points[latestDiskIndex].disk_percent !== null && (
              <circle className="server-chart-point disk" cx={serverChartX(latestDiskIndex, points.length)} cy={serverChartY(points[latestDiskIndex].disk_percent as number)} r="4" />
            )}
            {hovered && hoveredIndex !== null && (
              <g>
                <line className="server-chart-cursor" x1={serverChartX(hoveredIndex, points.length)} x2={serverChartX(hoveredIndex, points.length)} y1={SERVER_CHART.top} y2={SERVER_CHART.height - SERVER_CHART.bottom} />
                {hovered.cpu_moving_average_5m !== null && <circle className="server-chart-point cpu" cx={serverChartX(hoveredIndex, points.length)} cy={serverChartY(hovered.cpu_moving_average_5m)} r="5" />}
                {hovered.disk_percent !== null && <circle className="server-chart-point disk" cx={serverChartX(hoveredIndex, points.length)} cy={serverChartY(hovered.disk_percent)} r="5" />}
              </g>
            )}
          </svg>
          {hovered && hoveredIndex !== null && (
            <div className="server-chart-tooltip" style={{ left: `${Math.max(8, Math.min(82, hoveredIndex / Math.max(1, points.length - 1) * 100))}%` }}>
              <span>{formatServerTime(hovered.collected_at)}</span>
              <strong>CPU {hovered.cpu_moving_average_5m === null ? "N/D" : `${hovered.cpu_moving_average_5m.toFixed(1).replace(".", ",")}%`}</strong>
              <strong>Disk {hovered.disk_percent === null ? "collecting" : `${hovered.disk_percent.toFixed(1).replace(".", ",")}%`}</strong>
            </div>
          )}
        </div>

        <footer className="server-usage-foot">
          <span><ShieldCheck size={15} />{points.length.toLocaleString("pt-BR")} samples · 60-second refresh</span>
          <small>Last sample {formatDate(server.current.collected_at ?? undefined)}</small>
        </footer>
      </section>
    </div>
  );
}

function HealthView({ data }: { data: SystemHealthData | null }) {
  if (!data) return <LoadingState />;
  const apiUsage = data.api_usage ?? [];
  const groupIcons: Record<SystemHealthGroupKey, ComponentType<{ size?: number }>> = {
    apis: Activity,
    external_services: Cloud,
    open_finance: WalletCards,
    aws: Server,
    controls: ShieldCheck,
    quotes: LineChart,
    official_sources: Building2,
    automations: RefreshCw
  };
  const headline = data.status === "healthy"
    ? "All services operational"
    : data.status === "offline"
      ? "Service interruption detected"
      : "Conditions require attention";
  const qualityTone = data.quality >= 100
    ? "good"
    : data.quality >= 80
      ? "warning"
      : "critical";
  const orderedGroups = [...data.groups].sort((left, right) => {
    const order: Record<SystemHealthGroupKey, number> = {
      aws: 0,
      controls: 1,
      apis: 2,
      external_services: 3,
      open_finance: 4,
      quotes: 5,
      official_sources: 6,
      automations: 7
    };
    return order[left.key] - order[right.key];
  });
  const renderHealthGroup = (group: SystemHealthGroup) => {
    const GroupIcon = groupIcons[group.key];
    const visibleItems = group.items.filter((item) => item.name !== "Daily API Usage");
    return (
      <section className={`panel system-health-group system-health-group-${group.key}`} key={group.key}>
        <PanelHeader title={`${group.label} · ${group.healthy_count}/${group.total_count}`} icon={GroupIcon} />
        <div className={`health-list health-list-large health-list-horizontal health-list-${visibleItems.length}`}>
          {visibleItems.map((item) => <HealthRow key={`${group.key}-${item.name}`} item={item} groupKey={group.key} />)}
        </div>
      </section>
    );
  };
  return (
    <div className="content-stack">
      <div className={`quality-banner quality-${qualityTone}`}>
        <div className="quality-score">{data.quality}%</div>
        <div><span>Storm Troops Readiness</span><strong>{headline}</strong><small>{data.healthy_count}/{data.total_count} services operational · {formatDate(data.generated_at)}</small></div>
        <div className="quality-meter"><span style={{ width: `${data.quality}%` }} /></div>
      </div>
      <div className="system-health-group-grid system-health-infrastructure-grid">
        {orderedGroups.filter((group) => group.key === "aws").map(renderHealthGroup)}
      </div>
      <section className="panel api-usage-panel">
        <PanelHeader title="Daily API Usage" icon={Gauge} />
        {apiUsage.length ? (
          <div className="api-usage-grid">
            {apiUsage.map((metric) => (
              <article className={`api-usage-card api-usage-${metric.status}`} key={metric.provider}>
                <header>
                  <div className="api-usage-provider">
                    <span className="health-status-mark health-status-healthy" title={`${metric.provider} API operational`} aria-label={`${metric.provider} API operational`}>
                      <Check size={15} strokeWidth={3} />
                    </span>
                    <ServiceLogo name={metric.provider} groupKey="quotes" />
                  </div>
                  <div className="api-usage-consumption"><span>Daily consumption</span><strong>{metric.percent_used.toFixed(1).replace(".", ",")}%</strong></div>
                </header>
                <div className="api-usage-meter"><span style={{ width: `${Math.min(100, metric.percent_used)}%` }} /></div>
                <div className="api-usage-numbers"><strong>{metric.used.toLocaleString("pt-BR")}</strong><span>of {metric.limit.toLocaleString("pt-BR")} calls</span></div>
                <small>{metric.detail} · {metric.measured_at}</small>
              </article>
            ))}
          </div>
        ) : <div className="api-usage-empty">No provider exposes an official usage counter right now.</div>}
      </section>
      <div className="system-health-group-grid">
        {orderedGroups.filter((group) => group.key !== "aws").map(renderHealthGroup)}
      </div>
    </div>
  );
}

function MetricCard({ metric }: { metric: Metric }) {
  const icons = { Decisions: BookOpenCheck, "Follow-ups": Clock3, Agenda: CalendarDays, WhatsApp: Inbox };
  const Icon = icons[metric.label as keyof typeof icons] ?? Activity;
  return (
    <article className={`metric-card metric-${metric.tone}`}>
      <div className="metric-icon"><Icon size={18} /></div>
      <div><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></div>
    </article>
  );
}

function PanelHeader({ title, icon: Icon, action, onAction }: { title: string; icon: ComponentType<{ size?: number }>; action?: string; onAction?: () => void }) {
  return (
    <header className="panel-header"><div><Icon size={18} /><h2>{title}</h2></div>{action && <button onClick={onAction}>{action}<ChevronRight size={15} /></button>}</header>
  );
}

function PortfolioRow({ item }: { item: PortfolioItem }) {
  return (
    <div className="portfolio-row"><div className="company-monogram">{item.symbol.slice(0, 2)}</div><InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.symbol }}><strong>{item.symbol}</strong></InstrumentPreviewTarget><span>{item.price}</span><span className={`change-${item.direction}`}><DirectionIcon direction={item.direction} />{item.change}</span></div>
  );
}

type ServiceLogoKind =
  | "c3po"
  | "postgresql"
  | "cloudflare"
  | "github"
  | "intermedia"
  | "weather"
  | "pluggy"
  | "btg"
  | "santander"
  | "itau"
  | "aws"
  | "brapi"
  | "eodhd"
  | "finnhub"
  | "fmp"
  | "backblaze"
  | "massive"
  | "openai"
  | "anthropic"
  | "cvm"
  | "sec"
  | "issuer"
  | "summary"
  | "pdf"
  | "generic";

function serviceLogoKind(name: string, groupKey: SystemHealthGroupKey): ServiceLogoKind {
  const normalized = name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (normalized.includes("c3po")) return "c3po";
  if (normalized.includes("postgres")) return "postgresql";
  if (normalized.includes("cloudflare")) return "cloudflare";
  if (normalized.includes("github")) return "github";
  if (normalized.includes("intermedia") || normalized.includes("exchange") || normalized === "email") return "intermedia";
  if (normalized.includes("meteo") || normalized.includes("weather")) return "weather";
  if (normalized.includes("pluggy")) return "pluggy";
  if (normalized.includes("btg")) return "btg";
  if (normalized.includes("santander")) return "santander";
  if (normalized.includes("itau")) return "itau";
  if (normalized.includes("brapi")) return "brapi";
  if (normalized.includes("eodhd")) return "eodhd";
  if (normalized.includes("finnhub")) return "finnhub";
  if (normalized.includes("fmp") || normalized.includes("financial modeling")) return "fmp";
  if (normalized.includes("backblaze") || normalized.includes("b2")) return "backblaze";
  if (normalized.includes("massive")) return "massive";
  if (normalized.includes("openai") || normalized.includes("codex")) return "openai";
  if (normalized.includes("anthropic") || normalized.includes("claude")) return "anthropic";
  if (normalized.includes("cvm")) return "cvm";
  if (normalized.includes("sec") || normalized.includes("edgar")) return "sec";
  if (normalized.includes("issuer") || normalized === "ri") return "issuer";
  if (normalized.includes("summary") || normalized.includes("scheduler")) return "summary";
  if (normalized.includes("pdf")) return "pdf";
  if (normalized.includes("aws") || normalized.includes("lightsail") || normalized.includes("cron") || groupKey === "aws") return "aws";
  return "generic";
}

function ServiceLogo({ name, groupKey = "apis" }: { name: string; groupKey?: SystemHealthGroupKey }) {
  const kind = serviceLogoKind(name, groupKey);
  const officialAssets: Partial<Record<ServiceLogoKind, string>> = {
    postgresql: "/postgresql-mark.png",
    weather: "/open-meteo-mark.svg",
    pluggy: "/pluggy-mark.svg",
    brapi: "/brapi-mark.svg",
    fmp: "/fmp-mark.svg",
    intermedia: "/intermedia-exchange-logo.png",
    finnhub: "/service-finnhub.png",
    cvm: "/cvm-mark.png",
    sec: "/sec-mark.gif",
    backblaze: "/backblaze-mark.svg",
    massive: "/massive-mark.svg",
  };
  const officialAsset = officialAssets[kind];
  if (officialAsset) {
    return <span className={`service-logo service-logo-${kind}`} aria-hidden="true"><img src={officialAsset} alt="" /></span>;
  }
  if (kind === "c3po") {
    return <span className="service-logo service-logo-c3po"><img src="/c3po-protocol-mark.svg" alt="" /></span>;
  }
  if (kind === "cloudflare") {
    return (
      <span className="service-logo service-logo-cloudflare" aria-hidden="true">
        <svg viewBox="0 0 36 26"><path d="M11 20h19.5c3 0 4.5-1.7 4.5-3.8 0-2.3-1.9-4-4.7-4.1-.8-4.3-4.1-7-8.3-7-3.7 0-6.8 2.1-8 5.5a5.8 5.8 0 0 0-8.4 4.5C2.4 15.5 1 17.1 1 19c0 1.7 1.3 3 3.2 3H11v-2Z" /><path className="service-logo-highlight" d="M15 22h16.5c2.2 0 3.5-1 3.5-2.5 0-1.4-1.2-2.4-3-2.5H18.2L15 22Z" /></svg>
      </span>
    );
  }
  if (kind === "github") return <span className="service-logo service-logo-github" aria-hidden="true"><Github size={23} /></span>;
  if (kind === "santander") {
    return (
      <span className="service-logo service-logo-santander" aria-hidden="true">
        <svg viewBox="0 0 28 32"><path d="M15.2 2.5c.8 4.8-2.8 6.2-2.8 10.1 0 2.4 1.4 4.2 3.5 5.2-4.2-.4-7-2.9-7-6.2 0-3.7 4-5.1 6.3-9.1Zm3.1 7.2c3.7 3.2 5.4 6 5.4 9.1 0 5.8-4.4 10.2-10.3 10.2-5.5 0-9.8-3.7-10.3-8.8 1.8 2.3 4.5 3.6 7.5 3.6 5.3 0 9.1-3.2 9.1-7.6 0-2.2-.7-4.2-1.4-6.5Z" /></svg>
      </span>
    );
  }
  if (kind === "aws") return <span className="service-logo service-logo-aws" aria-hidden="true"><b>aws</b><i /></span>;
  if (kind === "btg") return <span className="service-logo service-logo-btg service-logo-word" aria-hidden="true"><b>BTG</b></span>;
  if (kind === "itau") return <span className="service-logo service-logo-itau service-logo-word" aria-hidden="true"><b>itaú</b></span>;
  if (kind === "eodhd") return <span className="service-logo service-logo-eodhd service-logo-word" aria-hidden="true"><i /><i /><i /><b>EOD</b></span>;
  if (kind === "openai") return <span className="service-logo service-logo-openai service-logo-word" aria-hidden="true"><b>AI</b></span>;
  if (kind === "anthropic") return <span className="service-logo service-logo-anthropic service-logo-word" aria-hidden="true"><b>CL</b></span>;
  if (kind === "issuer") return <span className="service-logo service-logo-issuer service-logo-word" aria-hidden="true"><b>RI</b></span>;
  if (kind === "summary") return <span className="service-logo service-logo-summary" aria-hidden="true"><Clock3 size={22} /></span>;
  if (kind === "pdf") return <span className="service-logo service-logo-pdf" aria-hidden="true"><FileChartColumn size={21} /><b>PDF</b></span>;
  return <span className="service-logo service-logo-generic service-logo-word" aria-hidden="true"><b>{name.slice(0, 2).toUpperCase()}</b></span>;
}

function HealthRow({ item, groupKey = "apis" }: { item: Integration; groupKey?: SystemHealthGroupKey }) {
  const statusLabel = item.status === "healthy" ? "Operational" : item.status === "attention" ? "Needs attention" : "Offline";
  return (
    <div className="health-row">
      <span className={`health-status-mark health-status-${item.status}`} aria-label={statusLabel} title={statusLabel}>
        {item.status === "healthy" ? <Check size={15} strokeWidth={3} /> : item.status === "offline" ? <span aria-hidden="true">×</span> : null}
      </span>
      <ServiceLogo name={item.name} groupKey={groupKey} />
      <div><strong>{item.name}</strong><span>{item.detail}</span></div>
    </div>
  );
}

function AlertRow({ item, expanded, onToggle }: { item: AlertItem; expanded: boolean; onToggle: () => void }) {
  const metadata = Object.entries(item.metadata ?? {}).filter(([, value]) => value);
  return (
    <article className={`alert-row${expanded ? " alert-row-expanded" : ""}${item.is_read ? "" : " alert-row-unread"}`}>
      <button className="alert-row-summary" type="button" onClick={onToggle} aria-expanded={expanded}>
        <div className="alert-mark"><AlertTriangle size={18} /></div>
        <div className="alert-row-copy"><span>{item.severity ?? "Review"}</span><strong>{item.subject}</strong><p>{item.action}</p></div>
        <ChevronRight className="alert-row-chevron" size={17} />
      </button>
      {expanded && (
        <div className="alert-row-details">
          <div className="alert-detail-grid">
            <div><span>Origem</span><strong>{item.source ?? "C3PO"}</strong></div>
            <div><span>Data e hora</span><strong>{item.occurred_at ? formatDate(item.occurred_at) : "Não informado"}</strong></div>
            <div><span>Status</span><strong>{item.is_read ? "Visualizado" : "Novo"}</strong></div>
          </div>
          {item.context && <div className="alert-detail-copy"><span>Contexto</span><p>{item.context}</p></div>}
          <div className="alert-detail-copy"><span>Ação recomendada</span><p>{item.action}</p></div>
          {metadata.length > 0 && <div className="alert-metadata">{metadata.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>}
          {item.source_url && <a className="alert-source-link" href={item.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /><span>Abrir fonte original</span></a>}
        </div>
      )}
    </article>
  );
}

function EmptyLine({ label }: { label: string }) {
  return <div className="empty-line"><ShieldCheck size={18} /><span>{label}</span></div>;
}

function HelmChairView({ session }: { session: AuthSession }) {
  const [access, setAccess] = useState<AccessUserListResponse | null>(null);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [permissions, setPermissions] = useState<ViewKey[]>([]);
  const [capabilities, setCapabilities] = useState<AccessCapabilityKey[]>(["read"]);
  const [editingEmail, setEditingEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadAccess = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/admin/access-users`, { cache: "no-store", credentials: "include" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível carregar os acessos.");
      setAccess(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar os acessos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAccess();
  }, [loadAccess]);

  const resetForm = () => {
    setEmail("");
    setDisplayName("");
    setIsActive(true);
    setPermissions([]);
    setCapabilities(["read"]);
    setEditingEmail(null);
    setError("");
  };

  const editUser = (user: AccessUser) => {
    setEmail(user.email);
    setDisplayName(user.display_name);
    setIsActive(user.is_active);
    setPermissions(user.permissions);
    setCapabilities(user.capabilities?.length ? user.capabilities : ["read"]);
    setEditingEmail(user.email);
    setMessage("");
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const togglePermission = (key: ViewKey) => {
    setPermissions((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  };

  const selectAll = () => {
    const all = access?.available_permissions.map((item) => item.key) ?? [];
    setPermissions(permissions.length === all.length ? [] : all);
  };

  const toggleCapability = (key: AccessCapabilityKey) => {
    if (key === "read") return;
    setCapabilities((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
    if (key === "onepager_generate" && !capabilities.includes(key)) {
      setPermissions((current) => current.includes("onepager") ? current : [...current, "onepager"]);
    }
  };

  const saveUser = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const editing = Boolean(editingEmail);
      const response = await fetch(
        editing ? `${API_URL}/api/v1/admin/access-users/${encodeURIComponent(editingEmail ?? "")}` : `${API_URL}/api/v1/admin/access-users`,
        {
          method: editing ? "PUT" : "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...(editing ? {} : { email }), display_name: displayName, is_active: isActive, permissions, capabilities })
        }
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível salvar o acesso.");
      setAccess(payload);
      setMessage(editing ? "Permissões atualizadas imediatamente." : "E-mail autorizado. O usuário já pode solicitar o código de acesso.");
      resetForm();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível salvar o acesso.");
    } finally {
      setSaving(false);
    }
  };

  const deleteUser = async (user: AccessUser) => {
    if (!window.confirm(`Remover o acesso de ${user.email}?`)) return;
    setError("");
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/api/v1/admin/access-users/${encodeURIComponent(user.email)}`, {
        method: "DELETE",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível remover o acesso.");
      setAccess(payload);
      setMessage("Acesso removido e sessões encerradas.");
      if (editingEmail === user.email) resetForm();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível remover o acesso.");
    }
  };

  const users = access?.items ?? [];
  const activeUsers = users.filter((user) => user.is_active).length;
  const restrictedUsers = users.filter((user) => user.role === "member" && (
    user.permissions.length < (access?.available_permissions.length ?? 0)
    || user.capabilities.length < (access?.available_capabilities.length ?? 0)
  )).length;
  const capabilityDescriptions: Record<AccessCapabilityKey, string> = {
    read: "Visualizar as abas liberadas sem alterar dados.",
    onepager_generate: "Criar novos relatórios na aba Laser Pager.",
    delete: "Excluir registros nas abas liberadas, como My Portfolio."
  };
  const capabilityIcons: Record<AccessCapabilityKey, ComponentType<{ size?: number }>> = {
    read: BookOpenCheck,
    onepager_generate: FilePlus2,
    delete: Trash2
  };

  return (
    <div className="helm-view">
      <section className="panel helm-summary">
        <PanelHeader title="Secure Access Registry" icon={DeathStarIcon} action="Refresh" onAction={loadAccess} />
        <div className="helm-summary-grid">
          <div><span>Authorized emails</span><strong>{users.length}</strong><small>including the protected owner</small></div>
          <div><span>Active access</span><strong>{activeUsers}</strong><small>able to request a login code</small></div>
          <div><span>Restricted profiles</span><strong>{restrictedUsers}</strong><small>limited to selected modules</small></div>
          <div><span>Security owner</span><strong>{session.email}</strong><small>cannot be removed or suspended</small></div>
        </div>
      </section>

      {error && <div className="screen-error"><AlertTriangle size={17} /><span>{error}</span></div>}
      {message && <div className="helm-success"><ShieldCheck size={17} /><span>{message}</span></div>}

      <div className="helm-grid">
        <section className="panel helm-editor">
          <PanelHeader title={editingEmail ? "Edit Crew Access" : "Authorize Email"} icon={Mail} />
          <form onSubmit={saveUser}>
            <label htmlFor="helm-email">E-mail</label>
            <div className="helm-input"><Mail size={17} /><input id="helm-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} disabled={Boolean(editingEmail)} placeholder="nome@empresa.com" required /></div>

            <label htmlFor="helm-name">Nome</label>
            <div className="helm-input"><Users size={17} /><input id="helm-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Nome exibido no C3PO" /></div>

            <div className="helm-toggle-row">
              <div><strong>Acesso ativo</strong><span>Desativar encerra as sessões existentes.</span></div>
              <label className="helm-switch"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /><span /></label>
            </div>

            <div className="helm-permission-head">
              <div><strong>Abas liberadas</strong><span>O bloqueio também é aplicado diretamente na API.</span></div>
              <button type="button" onClick={selectAll}>{permissions.length === (access?.available_permissions.length ?? -1) ? "Limpar" : "Todas"}</button>
            </div>
            <div className="helm-permission-grid">
              {access?.available_permissions.map((permission) => (
                <label key={permission.key} className={permissions.includes(permission.key) ? "helm-permission helm-permission-active" : "helm-permission"}>
                  <input type="checkbox" checked={permissions.includes(permission.key)} onChange={() => togglePermission(permission.key)} />
                  <span><ShieldCheck size={14} />{permission.label}</span>
                </label>
              ))}
            </div>

            <div className="helm-permission-head helm-capability-head">
              <div><strong>Permissões de ação</strong><span>Leitura é obrigatória; ações elevadas são validadas pela API.</span></div>
            </div>
            <div className="helm-capability-grid">
              {access?.available_capabilities.map((capability) => {
                const CapabilityIcon = capabilityIcons[capability.key];
                const active = capabilities.includes(capability.key);
                return (
                  <label key={capability.key} className={active ? "helm-capability helm-capability-active" : "helm-capability"}>
                    <input
                      type="checkbox"
                      checked={active}
                      disabled={capability.key === "read"}
                      onChange={() => toggleCapability(capability.key)}
                    />
                    <i><CapabilityIcon size={16} /></i>
                    <span><strong>{capability.label}</strong><small>{capabilityDescriptions[capability.key]}</small></span>
                    <em>{active ? "Ativa" : "Bloqueada"}</em>
                  </label>
                );
              })}
            </div>

            <div className="helm-form-actions">
              <button className="helm-save" type="submit" disabled={saving || !email || (isActive && !permissions.length)}><Save size={16} />{saving ? "Salvando..." : editingEmail ? "Salvar alterações" : "Autorizar e-mail"}</button>
              {editingEmail && <button className="helm-cancel" type="button" onClick={resetForm}>Cancelar</button>}
            </div>
          </form>
        </section>

        <section className="panel helm-roster">
          <PanelHeader title="Authorized Crew" icon={Users} />
          {loading && !access ? <div className="candidate-loading">{Array.from({ length: 4 }).map((_, index) => <span key={index} />)}</div> : (
            <div className="helm-user-list">
              {users.map((user) => (
                <article className="helm-user" key={user.email}>
                  <div className="helm-user-identity">
                    <UserAvatar displayName={user.display_name} email={user.email} />
                    <span><strong>{user.display_name || user.email}</strong><small>{user.email}</small></span>
                  </div>
                  <div className="helm-user-state">
                    <span className={user.is_active ? "helm-status helm-status-active" : "helm-status helm-status-suspended"}>{user.is_active ? "Active" : "Suspended"}</span>
                    <small>{user.role === "owner" ? "Protected owner" : user.last_login_at ? `Last login ${formatRecordDate(user.last_login_at)}` : "Never logged in"}</small>
                  </div>
                  <div className="helm-user-permissions">
                    {user.role === "owner" ? <span className="helm-capability-badge">Full control</span> : user.capabilities.map((capability) => <span className="helm-capability-badge" key={capability}>{access?.available_capabilities.find((item) => item.key === capability)?.label ?? capability}</span>)}
                    {user.role === "owner" ? <span>All modules + Death Star</span> : user.permissions.map((permission) => <span key={permission}>{access?.available_permissions.find((item) => item.key === permission)?.label ?? permission}</span>)}
                  </div>
                  <div className="helm-user-actions">
                    {user.role === "owner" ? <ShieldCheck size={18} aria-label="Protected owner" /> : <>
                      <button type="button" onClick={() => editUser(user)}>Editar</button>
                      <button className="helm-delete" type="button" onClick={() => deleteUser(user)} title="Remover acesso" aria-label={`Remover ${user.email}`}><Trash2 size={16} /></button>
                    </>}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function LoadingState() {
  return <div className="loading-grid">{Array.from({ length: 8 }).map((_, index) => <div className="loading-block" key={index} />)}</div>;
}

function LoginScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [requestedDelivery, setRequestedDelivery] = useState<"auto" | "email">("auto");

  const requestCode = async (deliveryMethod: "auto" | "email" = "auto") => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/request-code`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, delivery_method: deliveryMethod })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível enviar o código.");
      setChallengeId(payload.challenge_id);
      setRequestedDelivery(deliveryMethod);
      setMessage(`O código vale por ${Math.round(payload.expires_in_seconds / 60)} minutos.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível enviar o código.");
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async () => {
    setLoading(true);
    setError("");
    try {
      const browserNavigator = navigator as Navigator & { userAgentData?: { platform?: string } };
      const response = await fetch(`${API_URL}/api/v1/auth/verify-code`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: challengeId,
          code,
          platform: browserNavigator.userAgentData?.platform || navigator.platform || "",
          max_touch_points: navigator.maxTouchPoints || 0
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Código inválido ou expirado.");
      onAuthenticated();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Código inválido ou expirado.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <div className="login-mark" role="img" aria-label="C3PO protocol droid emblem" />
          <div><strong>C3PO</strong><span>Chief of Staff Intelligence</span></div>
        </div>
        <div className="login-rule" />
        <div className="login-heading">
          <span>Secure command access</span>
          <h1 id="login-title">{challengeId ? "Digite o código" : "Acesse seu command center"}</h1>
          <p>{challengeId
            ? "Use seu código de seis dígitos. Ele pode estar no autenticador ou no e-mail autorizado."
            : "Use seu e-mail autorizado. Nenhuma senha é necessária."}</p>
        </div>

        {!challengeId ? (
          <form onSubmit={(event) => { event.preventDefault(); void requestCode(); }} className="login-form">
            <label htmlFor="login-email">E-mail</label>
            <div className="login-input"><Mail size={18} /><input id="login-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></div>
            <button className="login-primary" type="submit" disabled={loading}>{loading ? "Signing in..." : "Sign In"}</button>
          </form>
        ) : (
          <form onSubmit={(event) => { event.preventDefault(); verifyCode(); }} className="login-form">
            <label htmlFor="login-code">Código de acesso</label>
            <div className="login-input login-code-input"><LockKeyhole size={18} /><input id="login-code" name="one-time-code" type="text" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" pattern="\d{6}" required autoFocus /></div>
            {message && <p className="login-message">{message}</p>}
            <button className="login-primary" type="submit" disabled={loading || code.length !== 6}>{loading ? "Validando..." : "Entrar no C3PO"}</button>
            {requestedDelivery !== "email" && <button className="login-secondary" type="button" disabled={loading} onClick={() => void requestCode("email")}>Receber código por e-mail</button>}
          </form>
        )}
        {error && <div className="login-error"><AlertTriangle size={16} /><span>{error}</span></div>}
        <footer className="login-foot"><ShieldCheck size={15} /><span>Código de uso único. Sessão criptografada e acesso privado.</span></footer>
      </section>
    </main>
  );
}

function C3POGate() {
  const [authState, setAuthState] = useState<"checking" | "anonymous" | "authenticated">("checking");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [previewOpening, setPreviewOpening] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV !== "production" && new URLSearchParams(window.location.search).get("preview") === "opening") {
      setPreviewOpening(true);
    }
  }, []);

  const refreshSession = useCallback(() => {
    setAuthState("checking");
    return fetch(`${API_URL}/api/v1/auth/session`, { cache: "no-store", credentials: "include" })
      .then((response) => response.json())
      .then((payload: AuthSession) => {
        setSession(payload.authenticated ? payload : null);
        setAuthState(payload.authenticated ? "authenticated" : "anonymous");
      })
      .catch(() => {
        setSession(null);
        setAuthState("anonymous");
      });
  }, []);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  const logout = async () => {
    await fetch(`${API_URL}/api/v1/auth/logout`, { method: "POST", credentials: "include" }).catch(() => undefined);
    setSession(null);
    setAuthState("anonymous");
  };

  const completeLogin = () => {
    const params = new URLSearchParams(window.location.search);
    params.set("view", "command");
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    void refreshSession();
  };

  if (previewOpening) return <C3POOpeningView onEnter={() => setPreviewOpening(false)} />;

  if (authState === "checking") {
    return <main className="login-shell"><div className="login-loading"><div className="login-mark" /><span>Estabelecendo canal seguro...</span></div></main>;
  }
  if (authState === "anonymous") return <LoginScreen onAuthenticated={completeLogin} />;
  if (!session) return <main className="login-shell"><div className="login-loading"><div className="login-mark" /><span>Validando autorização...</span></div></main>;
  return <AppShell session={session} onLogout={logout} onSessionExpired={() => { setSession(null); setAuthState("anonymous"); }} />;
}

export default function Page() {
  return <C3POGate />;
}
