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
  | "onepager"
  | "intelligence"
  | "finance"
  | "alerts"
  | "health"
  | "serverusage"
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

type SystemHealthGroupKey = "apis" | "external_services" | "open_finance" | "aws" | "quotes" | "official_sources" | "automations";

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
  methodology_version: string;
  start_date: string;
  checkpoint_date: string;
  checkpoint_reached: boolean;
  checkpoint_days: number;
  operating_days_elapsed: number;
  starting_capital_usd: number;
  nav_usd: number;
  cash_usd: number;
  gross_exposure_usd: number;
  total_return_percent: number;
  daily_pnl_usd: number;
  daily_return_percent: number;
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
  methodology: Record<string, string>;
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
  { key: "onepager", label: "Laser Pager", icon: LaserPagerIcon },
  { key: "intelligence", label: "Ben Kenobi Records", icon: BenKenobiRecordsIcon },
  { key: "finance", label: "Midi-Chlorians Finance", icon: MidiChloriansFinanceIcon },
  { key: "alerts", label: "Radar Alerts", icon: RadarAlertsIcon },
  { key: "health", label: "Storm Troops", icon: StormTroopsIcon },
  { key: "serverusage", label: "TIE Fighter Usage", icon: TieFighterUsageIcon }
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
  onepager: LaserPagerIcon,
  intelligence: BenKenobiRecordsIcon,
  finance: MidiChloriansFinanceIcon,
  alerts: RadarAlertsIcon,
  health: StormTroopsIcon,
  serverusage: TieFighterUsageIcon,
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
  onepager: { title: "Laser Pager", eyebrow: "Protocol intelligence · On-demand equity research" },
  intelligence: { title: "Ben Kenobi Records", eyebrow: "Valuation intelligence · Permanent audit trail" },
  finance: { title: "Midi-Chlorians Finance", eyebrow: "Protocol intelligence · Banking and investments" },
  alerts: { title: "Radar Alerts", eyebrow: "Protocol intelligence · Exceptions requiring attention" },
  health: { title: "Storm Troops", eyebrow: "Operational readiness · Services, sources and scheduled jobs" },
  serverusage: { title: "TIE Fighter Usage", eyebrow: "AWS telemetry · Lightsail infrastructure" },
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

function normalizeCompanyLogoUrl(value?: string | null) {
  const clean = value?.trim();
  if (!clean) return "";
  if (clean.startsWith("//")) return `https:${clean}`;
  if (clean.startsWith("/")) return `https://eodhd.com${clean}`;
  return clean;
}

function CompanyLogo({ logoUrl, symbol }: { logoUrl?: string | null; symbol: string }) {
  const normalizedSymbol = symbol.trim().toUpperCase();
  const sources = useMemo(() => Array.from(new Set([
    `/api/v1/company-logo/${encodeURIComponent(normalizedSymbol)}`,
    normalizeCompanyLogoUrl(logoUrl),
    `https://eodhd.com/img/logos/US/${normalizedSymbol.toLowerCase()}.png`,
    `https://financialmodelingprep.com/image-stock/${encodeURIComponent(normalizedSymbol)}.png`
  ].filter(Boolean))), [logoUrl, normalizedSymbol]);
  const [sourceIndex, setSourceIndex] = useState(0);
  useEffect(() => setSourceIndex(0), [sources.join("|")]);
  return sources[sourceIndex]
    ? <img src={sources[sourceIndex]} alt="" onError={() => setSourceIndex((current) => current + 1)} />
    : <span>{symbol.slice(0, 2)}</span>;
}

function ProfilePanel({
  session,
  items,
  onClose
}: {
  session: AuthSession;
  items: typeof navItems;
  onClose: () => void;
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
    if (typeof window === "undefined") return "home";
    const requested = new URLSearchParams(window.location.search).get("view");
    if (requested === "home") return "home";
    if (visibleNavItems.some((item) => item.key === requested)) return requested as ViewKey;
    return "home";
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [viewRevision, setViewRevision] = useState(0);
  const [financeRefreshKey, setFinanceRefreshKey] = useState(0);
  const [activeAlertCount, setActiveAlertCount] = useState(0);
  const [navigationIndicators, setNavigationIndicators] = useState<NavigationIndicatorsData | null>(null);
  const ActiveViewIcon = viewIcons[activeView];

  useEffect(() => {
    if (session.is_admin || !session.idle_timeout_seconds) return;

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
  }, [onSessionExpired, session.idle_timeout_seconds, session.is_admin]);

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
      const [alertsResponse, indicatorsResponse] = await Promise.all([
        needsAlerts ? fetch(`${API_URL}/api/v1/alerts`, { cache: "no-store", credentials: "include" }) : Promise.resolve(null),
        needsFeedIndicators ? fetch(`${API_URL}/api/v1/navigation-indicators`, { cache: "no-store", credentials: "include" }) : Promise.resolve(null)
      ]);
      if (alertsResponse?.status === 401 || indicatorsResponse?.status === 401) {
        onSessionExpired();
        return;
      }
      if (alertsResponse?.ok) {
        const alertsPayload: AlertsData = await alertsResponse.json();
        setActiveAlertCount(alertsPayload.unread_count ?? alertsPayload.items.filter((item) => !item.is_read).length);
      }
      if (indicatorsResponse?.ok) setNavigationIndicators(await indicatorsResponse.json());
    } catch {
      // Badge refresh is best effort and must not interrupt the active workspace.
    }
  }, [onSessionExpired, session.permissions]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const allowed = new Set(session.permissions);
      const needsCommand = allowed.has("command");
      const needsReports = allowed.has("command") || allowed.has("candidates");
      const needsProviders = allowed.has("markets") || allowed.has("realtime") || allowed.has("candidates") || allowed.has("health");
      const [commandResponse, reportsResponse, providersResponse, systemHealthResponse] = await Promise.all([
        needsCommand ? fetch(`${API_URL}/api/v1/command-center`, { cache: "no-store", credentials: "include" }) : Promise.resolve(null),
        needsReports ? fetch(`${API_URL}/api/v1/reports`, { cache: "no-store", credentials: "include" }) : Promise.resolve(null),
        needsProviders ? fetch(`${API_URL}/api/v1/market-data/providers`, { cache: "no-store", credentials: "include" }) : Promise.resolve(null),
        fetch(`${API_URL}/api/v1/system-health`, { cache: "no-store", credentials: "include" })
      ]);
      if ([commandResponse, reportsResponse, providersResponse, systemHealthResponse].some((response) => response?.status === 401)) {
        onSessionExpired();
        return;
      }
      if (commandResponse && !commandResponse.ok) throw new Error(`API ${commandResponse.status}`);
      if (commandResponse) setData(await commandResponse.json());
      if (reportsResponse?.ok) {
        const reportPayload = await reportsResponse.json();
        setReports(reportPayload.items ?? []);
      }
      if (providersResponse?.ok) setMarketProviders(await providersResponse.json());
      if (systemHealthResponse.ok) setSystemHealth(await systemHealthResponse.json());
      await refreshNotificationState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }, [onSessionExpired, refreshNotificationState, session.permissions]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshNotificationState();
    };
    const interval = window.setInterval(refreshWhenVisible, 60_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [refreshNotificationState]);

  const markNavigationFeedSeen = useCallback(async (view: NavigationFeedKey) => {
    const seenAt = new Date().toISOString();
    setNavigationIndicators((current) => current ? {
      ...current,
      feeds: {
        ...current.feeds,
        [view]: {
          ...(current.feeds[view] ?? { latest_at: null }),
          has_new: false,
          unseen_count: 0,
          last_seen_at: seenAt
        }
      }
    } : current);
    try {
      const response = await fetch(`${API_URL}/api/v1/navigation-seen`, {
        method: "POST",
        cache: "no-store",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ view })
      });
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error(`API ${response.status}`);
    } catch {
      void refreshNotificationState();
    }
  }, [onSessionExpired, refreshNotificationState]);

  useEffect(() => {
    if (activeView === "relations" || activeView === "intelligence") {
      void markNavigationFeedSeen(activeView);
    }
  }, [activeView, markNavigationFeedSeen, viewRevision]);

  const selectView = (view: ViewKey, realtimeTab?: RealtimeTabKey, viewQuery?: string) => {
    if (view !== "home" && !visibleNavItems.some((item) => item.key === view)) return;
    if (view === "finance") setFinanceRefreshKey((value) => value + 1);
    setActiveView(view);
    setViewRevision((value) => value + 1);
    setMenuOpen(false);
    const params = new URLSearchParams(window.location.search);
    params.set("view", view);
    if (view === "realtime" && realtimeTab) params.set("market", realtimeTab.toLowerCase());
    else params.delete("market");
    if (viewQuery?.trim()) params.set("q", viewQuery.trim());
    else params.delete("q");
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  };

  return (
    <InstrumentPreviewProvider>
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <button className="brand-home-link" type="button" onClick={() => selectView("home")} aria-label="Abrir apresentação do C3PO">
            <div className="brand-mark" role="img" aria-label="C3PO protocol droid emblem" />
            <div>
              <strong>C3PO</strong>
              <span>Chief of Staff Intelligence</span>
            </div>
          </button>
          <button className="icon-button sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="Primary navigation">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const iconSize = item.key === "command" || item.key === "realtime" || item.key === "weather" || item.key === "relations" || item.key === "matrix" || item.key === "alerts" || item.key === "health" || item.key === "helm" ? 22 : 18;
            const hasNew = item.key === "alerts"
              ? activeAlertCount > 0
              : (item.key === "relations" || item.key === "intelligence")
                ? Boolean(navigationIndicators?.feeds[item.key]?.has_new)
                : false;
            return (
              <button
                key={item.key}
                className={activeView === item.key ? "nav-item nav-item-active" : "nav-item"}
                onClick={() => selectView(item.key)}
              >
                <span className="nav-item-icon-wrap">
                  <Icon size={iconSize} />
                  {hasNew && <span className="nav-notification-dot" aria-hidden="true" />}
                </span>
                <span className="nav-item-label">{item.label}</span>
                {item.key === "health" && systemHealth && (
                  <span className={`nav-health-percent nav-health-${systemHealth.status}`}>
                    {systemHealth.quality}%
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <button className="profile-row" type="button" onClick={() => { setProfileOpen(true); setMenuOpen(false); }} aria-expanded={profileOpen} aria-haspopup="dialog">
            <UserAvatar className="avatar" displayName={session.display_name} email={session.email} />
            <div><strong>{session.display_name || session.email}</strong><span>{session.is_admin ? "Owner · Death Star" : "Authorized command access"}</span></div>
            <ChevronRight size={16} />
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Open navigation">
            <Menu size={20} />
          </button>
          <GlobalSearch
            session={session}
            items={visibleNavItems}
            onNavigate={selectView}
            onSessionExpired={onSessionExpired}
          />
          <div className="topbar-actions">
            <div className="as-of">
              <Clock3 size={15} />
              <span>{activeView === "home" ? "C3PO protocol online" : activeView === "relations" ? "Regulatory feed live" : activeView === "news" ? "Headlines live" : activeView === "r2d2" ? "Paper portfolio ready" : activeView === "intelligence" ? "Valuation audit live" : activeView === "health" ? "Consolidated checks live" : activeView === "serverusage" ? "AWS telemetry live" : activeView === "weather" ? "Dagobah models live" : `As of ${formatDate(data?.generated_at)}`}</span>
            </div>
            <button className="icon-button" onClick={loadData} disabled={loading} aria-label="Refresh data" title="Refresh data">
              <RefreshCw size={18} className={loading ? "spin" : ""} />
            </button>
            {session.permissions.includes("alerts") && <button className="icon-button" onClick={() => selectView("alerts")} aria-label="Open Radar Alerts" title="Radar Alerts">
              <Bell size={18} />
              {activeAlertCount > 0 && <span className="notification-dot" />}
            </button>}
            <button className="icon-button" onClick={onLogout} aria-label="Sair do C3PO" title="Sair">
              <LogOut size={18} />
            </button>
          </div>
        </header>

        <section className={activeView === "home" ? "page-frame page-frame-home" : "page-frame"}>
          {activeView !== "home" && <div className="page-heading">
            <div className="page-heading-copy">
              <span className="eyebrow">{viewTitles[activeView].eyebrow}</span>
              <h1>{viewTitles[activeView].title}</h1>
              <p>
                {activeView === "command"
                  ? "Controle executivo do R2D2, índices globais e prontidão operacional em uma única tela."
                  : activeView === "relations"
                  ? "Official disclosures, issuer updates and valuation-review status in one audit trail."
                  : activeView === "news"
                    ? "As cinco notícias mais recentes e relevantes de cada fonte, reunidas em um briefing único."
                  : activeView === "r2d2"
                    ? "Laboratório de execução virtual para validar a inteligência do C3PO com capital simulado, governança e track record auditável."
                  : activeView === "intelligence"
                    ? "Histórico permanente das alterações de valuation, com gatilho, fonte e metodologia."
                  : activeView === "serverusage"
                    ? "CPU and storage telemetry for the infrastructure running C3PO."
                    : activeView === "health"
                      ? "Cloudflare, APIs, Open Finance, AWS, market data, official sources and automatic routines in one operational view."
                    : activeView === "weather"
                      ? "Previsão operacional das próximas 24 horas para os locais fixos e qualquer lugar do mundo."
                  : data
                    ? `${data.greeting}, Eduardo. ${data.report_title}.`
                  : "Connecting to your intelligence layer."}
              </p>
            </div>
            <div className={`page-heading-mark page-heading-mark-${activeView}`} role="img" aria-label={`${viewTitles[activeView].title} logo`}>
              <ActiveViewIcon size={98} />
            </div>
            <div className={`freshness freshness-${activeView === "relations" || activeView === "news" || activeView === "r2d2" || activeView === "intelligence" || activeView === "health" || activeView === "serverusage" || activeView === "weather" ? "current" : data?.provenance.status ?? "unavailable"}`}>
              <ShieldCheck size={16} />
              <span>{activeView === "command" ? "R2D2 + Master Luke + Storm Troops" : activeView === "relations" ? "CVM / SEC official sources" : activeView === "news" ? "Globo + UOL + Bloomberg + CNBC" : activeView === "r2d2" ? "Paper strategy enabled · real brokerage disabled" : activeView === "intelligence" ? "C3PO valuation audit trail" : activeView === "health" ? "Cloudflare + APIs + Pluggy + AWS + data sources" : activeView === "serverusage" ? "60-second host samples" : activeView === "weather" ? "Open-Meteo multi-model" : data?.provenance.source ?? "Source pending"}</span>
            </div>
          </div>}

          {activeView !== "home" && error && (
            <div className="error-banner"><AlertTriangle size={18} /><span>API unavailable: {error}</span><button onClick={loadData}>Retry</button></div>
          )}
          {loading && !data && activeView === "command" ? <LoadingState /> : (
            <ViewRouter
              key={`${activeView}-${viewRevision}`}
              activeView={activeView}
              data={data}
              reports={reports}
              portfolio={data?.portfolio ?? []}
              marketProviders={marketProviders}
              systemHealth={systemHealth}
              financeRefreshKey={financeRefreshKey}
              onNavigate={selectView}
              onAlertsRead={setActiveAlertCount}
              session={session}
            />
          )}
        </section>
      </main>
      {profileOpen && <ProfilePanel session={session} items={visibleNavItems} onClose={() => setProfileOpen(false)} />}
      {menuOpen && <button className="mobile-overlay" onClick={() => setMenuOpen(false)} aria-label="Close navigation overlay" />}
    </div>
    </InstrumentPreviewProvider>
  );
}

function ViewRouter({
  activeView,
  data,
  reports,
  portfolio,
  marketProviders,
  systemHealth,
  financeRefreshKey,
  onNavigate,
  onAlertsRead,
  session
}: {
  activeView: ViewKey;
  data: CommandCenterData | null;
  reports: ReportItem[];
  portfolio: PortfolioItem[];
  marketProviders: MarketDataProvider[];
  systemHealth: SystemHealthData | null;
  financeRefreshKey: number;
  onNavigate: (view: ViewKey, realtimeTab?: RealtimeTabKey, query?: string) => void;
  onAlertsRead: (count: number) => void;
  session: AuthSession;
}) {
  const canGenerateOnePagers = session.is_admin || session.capabilities.includes("onepager_generate");
  const canDeleteData = session.is_admin || session.capabilities.includes("delete");
  if (activeView === "home") return <C3POOpeningView onEnter={() => onNavigate("command")} />;
  if (activeView === "helm") return <HelmChairView session={session} />;
  if (activeView === "portfolio" && data) return <PortfolioView data={data} portfolio={portfolio} />;
  if (activeView === "relations") return <InvestorRelationsView canManage={session.is_admin} />;
  if (activeView === "news") return <RebellionNewsView />;
  if (activeView === "r2d2") return <R2D2RisingView />;
  if (activeView === "markets") return <MarketsView />;
  if (activeView === "realtime") return <RealTimeView canManage={session.is_admin} canDelete={canDeleteData} />;
  if (activeView === "weather") return <WeatherView />;
  if (activeView === "intelligence") return <IQRecordsView />;
  if (activeView === "health") return <HealthView data={systemHealth} />;
  if (activeView === "serverusage") return <ServerUsageView />;
  if (activeView === "alerts") return <AlertsView onRead={onAlertsRead} />;
  if (activeView === "finance") return <FinanceView refreshKey={financeRefreshKey} />;
  if (activeView === "candidates") return <CandidatesView reports={reports} marketProviders={marketProviders} />;
  if (activeView === "matrix") return <MatrixPowerView />;
  if (activeView === "onepager") return <OnePagerView canGenerate={canGenerateOnePagers} />;
  if (activeView === "command") return <MillenniumFalconView systemHealth={systemHealth} />;
  return <LoadingState />;
}

function R2D2RisingView() {
  const [data, setData] = useState<R2D2DashboardData | null>(null);
  const [error, setError] = useState("");
  const requestInFlight = useRef(false);
  const [hoveredAllocation, setHoveredAllocation] = useState<{
    label: string;
    name: string;
    detail: string;
    value: number;
    percent: number;
    x: number;
    y: number;
  } | null>(null);
  const learningScrollRef = useRef<HTMLDivElement | null>(null);
  const [learningContainerWidth, setLearningContainerWidth] = useState(900);

  useEffect(() => {
    const node = learningScrollRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setLearningContainerWidth(width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const load = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const response = await fetch(`${API_URL}/api/v1/r2d2`, { cache: "no-store", credentials: "include" });
      if (!response.ok) throw new Error(`API ${response.status}`);
      setData(await response.json());
      setError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "R2D2 data unavailable");
    } finally {
      requestInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 2_000);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [load]);

  if (!data) return error ? <div className="error-banner"><AlertTriangle size={16} />{error}</div> : <LoadingState />;

  const money = (value: number) => new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0
  }).format(value).replace("$", "US$ ");
  const moneyExact = (value: number) => new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2
  }).format(value).replace("$", "US$ ");
  const signedMoney = (value: number) => `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`;
  const signedPercent = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  const cashPercent = data.nav_usd > 0 ? data.cash_usd / data.nav_usd * 100 : 100;
  const saoPauloDateKey = (value: string | Date) => new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(new Date(value));
  const todayKey = saoPauloDateKey(new Date());
  const todayTrades = data.trades.filter((trade) => saoPauloDateKey(trade.executed_at) === todayKey);
  const todayPositiveTrades = todayTrades.filter((trade) => (trade.realized_pnl_usd ?? 0) > 0).length;
  const todayNegativeTrades = todayTrades.filter((trade) => (trade.realized_pnl_usd ?? 0) < 0).length;
  const lifetimeClosedTrades = data.stats.positive_transactions + data.stats.negative_transactions;
  const lifetimePositiveShare = lifetimeClosedTrades > 0 ? data.stats.positive_transactions / lifetimeClosedTrades * 100 : 0;
  const lifetimeNegativeShare = lifetimeClosedTrades > 0 ? data.stats.negative_transactions / lifetimeClosedTrades * 100 : 0;
  const intelligenceLog = [
    ...todayTrades.map((trade) => ({
      id: `trade-${trade.id}`,
      timestamp: trade.executed_at,
      action: trade.side,
      symbol: trade.symbol,
      name: trade.name,
      market: trade.market,
      rationale: trade.reason,
      detail: trade.side === "BUY"
        ? `${trade.quantity.toLocaleString("en-US", { maximumFractionDigits: 3 })} shares acquired at ${trade.currency} ${trade.fill_price_local.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.`
        : `${trade.quantity.toLocaleString("en-US", { maximumFractionDigits: 3 })} shares sold · ${trade.realized_pnl_usd === null ? "P&L pending" : `${signedMoney(trade.realized_pnl_usd)} realized`}.`,
      tone: trade.side === "BUY" ? "buy" : (trade.realized_pnl_usd ?? 0) >= 0 ? "sell-positive" : "sell-negative"
    })),
    ...data.positions
      .filter((position) => saoPauloDateKey(position.updated_at) === todayKey)
      .map((position) => ({
        id: `position-${position.market}-${position.symbol}`,
        timestamp: position.updated_at,
        action: position.decision_state || "MONITOR",
        symbol: position.symbol,
        name: position.name,
        market: position.market,
        rationale: `Motor state: ${position.decision_state || "monitoring"}. Technical score ${position.technical_score.toFixed(1)}; trend ${position.trend_state}; flow ${position.volume_state}.`,
        detail: `Position ${signedPercent(position.unrealized_return_percent)} · stop ${position.currency} ${position.stop_price_local.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · quote ${position.quote_status}.`,
        tone: "monitor"
      }))
  ].sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());
  const launchChecks = [
    { label: "Market feeds", detail: "EODHD live · Nasdaq + NYSE · B3 execution disabled", state: "ready" },
    { label: "Canonical valuation", detail: "Dark Side + Last Jedi + Laser Pager", state: "ready" },
    { label: "Risk mandate", detail: "No leverage · failed-entry defense -0.3% · hard stop -0.65%", state: "ready" },
    { label: "Paper execution", detail: `20-second risk monitor · one-minute opportunity scan · ${data.status}`, state: data.status === "paused" ? "pending" : "ready" },
    { label: "Turnover policy", detail: "20-80 qualified orders/session · 120 hard cap · costs included", state: "ready" },
    { label: "Daily learning loop", detail: `Version ${data.learning.version} · ${data.learning.sample_days} sessions · ${data.learning.sample_trades} completed exits`, state: "ready" }
  ];
  const points = data.track_record.length ? data.track_record : [{
    session_date: data.start_date, nav_usd: data.starting_capital_usd,
    daily_pnl_usd: 0, daily_return_percent: 0, is_final: false
  }];
  const values = points.map((point) => point.nav_usd);
  const center = data.starting_capital_usd;
  const spread = Math.max(center * 0.01, Math.max(...values) - Math.min(...values), 1);
  const chartMin = Math.min(...values, center) - spread * 0.35;
  const chartMax = Math.max(...values, center) + spread * 0.35;
  const chartPath = points.map((point, index) => {
    const x = points.length === 1 ? 706 : index / (points.length - 1) * 706;
    const y = 158 - ((point.nav_usd - chartMin) / (chartMax - chartMin)) * 146;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const lastY = 158 - ((values[values.length - 1] - chartMin) / (chartMax - chartMin)) * 146;
  const counters = [
    { label: "Positive days", value: data.stats.positive_days, detail: `${data.stats.win_rate_percent.toFixed(1)}% win rate`, tone: "positive" },
    { label: "Days ≥ +0.5%", value: data.stats.above_half_percent_days, detail: "Measured target, never forced", tone: "positive" },
    { label: "Negative days", value: data.stats.negative_days, detail: `${data.stats.closed_days} closed sessions`, tone: "critical" },
    { label: "Days ≤ -0.5%", value: data.stats.below_minus_half_percent_days, detail: "Material down sessions", tone: "critical" }
  ];
  const allocationPalette = ["#316fbb", "#2c9b70", "#7b61c9", "#d99b38", "#d45b55", "#4f9fb3", "#96733d", "#6b7b91", "#c35f99", "#9baf48", "#d1aa2f"];
  const allocationTotal = data.positions.reduce((sum, position) => sum + position.market_value_usd, 0) + data.cash_usd;
  const allocationItems = [
    ...[...data.positions]
      .sort((left, right) => right.market_value_usd - left.market_value_usd)
      .map((position, index) => ({
        label: position.symbol,
        name: position.name,
        logoUrl: position.logo_url,
        detail: position.market,
        value: position.market_value_usd,
        color: allocationPalette[index % (allocationPalette.length - 1)]
      })),
    { label: "Cash", name: "Available cash", logoUrl: "/market-marks/usd.svg", detail: "Available", value: data.cash_usd, color: allocationPalette[allocationPalette.length - 1] }
  ].map((item) => ({
    ...item,
    percent: allocationTotal > 0 ? item.value / allocationTotal * 100 : 0
  }));
  const donutRadius = 68;
  const donutCircumference = 2 * Math.PI * donutRadius;
  let allocationCursor = 0;
  const allocationSlices = allocationItems.map((item) => {
    const start = allocationCursor;
    allocationCursor += item.percent / 100;
    return { ...item, start };
  });
  const learningCurve = data.learning_curve;
  const LEARNING_MOVING_AVERAGE_WINDOW = 5;
  const learningMovingAverage = learningCurve.map((_, index) => {
    const window = learningCurve.slice(Math.max(0, index - (LEARNING_MOVING_AVERAGE_WINDOW - 1)), index + 1);
    return window.reduce((sum, point) => sum + point.positive_percent, 0) / window.length;
  });
  const learningLastMovingAverage = learningMovingAverage.length
    ? learningMovingAverage[learningMovingAverage.length - 1]
    : 0;
  const learningLastActual = learningCurve.length
    ? learningCurve[learningCurve.length - 1].positive_percent
    : 0;
  const learningTrendDelta = learningLastActual - learningLastMovingAverage;
  const learningTrendTone = learningTrendDelta > 1 ? "positive" : learningTrendDelta < -1 ? "negative" : "neutral";
  const learningTrendLabel = learningCurve.length < 2
    ? "Aguardando mais dias"
    : learningTrendDelta > 1
      ? `Melhorando · ${learningTrendDelta >= 0 ? "+" : ""}${learningTrendDelta.toFixed(1)}pp vs média móvel`
      : learningTrendDelta < -1
        ? `Piorando · ${learningTrendDelta.toFixed(1)}pp vs média móvel`
        : "Estável vs média móvel";
  const LEARNING_MIN_SLOT = 32;
  const LEARNING_MAX_BAR_WIDTH = 34;
  const LEARNING_GAP = 12;
  const LEARNING_PLOT_LEFT = 34;
  const LEARNING_PLOT_TOP = 26;
  const LEARNING_PLOT_HEIGHT = 150;
  const LEARNING_CHART_HEIGHT = LEARNING_PLOT_TOP + LEARNING_PLOT_HEIGHT + 28;
  // Bars stretch to fill the panel's full width (growing toward the right edge as
  // days are added) as long as they stay legible; once there are too many days to
  // fit at a comfortable minimum width, the chart switches to a fixed bar width and
  // scrolls horizontally instead of squeezing bars unreadably thin.
  const learningPlotWidth = Math.max(0, learningContainerWidth - LEARNING_PLOT_LEFT - LEARNING_GAP);
  const learningFitSlot = learningCurve.length > 0 ? learningPlotWidth / learningCurve.length : LEARNING_MIN_SLOT;
  const learningFillsContainer = learningFitSlot >= LEARNING_MIN_SLOT;
  const learningSlot = learningFillsContainer ? learningFitSlot : LEARNING_MIN_SLOT;
  const learningBarWidth = Math.max(6, Math.min(LEARNING_MAX_BAR_WIDTH, learningSlot - LEARNING_GAP));
  const learningChartWidth = learningFillsContainer
    ? learningContainerWidth
    : LEARNING_PLOT_LEFT + learningCurve.length * learningSlot + LEARNING_GAP;
  const learningMovingAveragePoints = learningMovingAverage.map((value, index) => ({
    x: LEARNING_PLOT_LEFT + index * learningSlot + learningSlot / 2,
    y: LEARNING_PLOT_TOP + LEARNING_PLOT_HEIGHT - (value / 100) * LEARNING_PLOT_HEIGHT
  }));
  const learningMovingAveragePath = learningMovingAveragePoints
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
  const showAllocationTooltip = (
    event: ReactPointerEvent<SVGCircleElement>,
    item: (typeof allocationSlices)[number]
  ) => {
    const bounds = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!bounds) return;
    setHoveredAllocation({
      ...item,
      x: Math.min(Math.max(event.clientX - bounds.left, 18), bounds.width - 18),
      y: Math.min(Math.max(event.clientY - bounds.top, 18), bounds.height - 18)
    });
  };

  return (
    <div className="r2d2-view">
      {error ? <div className="error-banner"><AlertTriangle size={16} />{error}</div> : null}
      <section className="r2d2-capital-band" aria-label="Paper portfolio capital">
        <div className="r2d2-capital-identity">
          <R2D2RisingIcon size={38} />
          <div>
            <span>SIMULATION STATUS</span>
            <strong>{data.status === "scheduled" ? "Launch scheduled" : data.status === "running" ? "Continuous paper run" : data.status}</strong>
            <small>From {data.start_date} · {data.checkpoint_days}-day checkpoint {data.checkpoint_date}{data.checkpoint_reached ? " reached" : ""}</small>
          </div>
        </div>
        <div><span>Starting capital</span><strong>{money(data.starting_capital_usd)}</strong><small>Virtual capital · paper only</small></div>
        <div><span>Net asset value</span><strong>{money(data.nav_usd)}</strong><small>{signedPercent(data.total_return_percent)} since launch</small></div>
        <div><span>Daily P&amp;L</span><strong className={data.daily_pnl_usd > 0 ? "r2d2-up" : data.daily_pnl_usd < 0 ? "r2d2-down" : "r2d2-flat"}>{signedMoney(data.daily_pnl_usd)}</strong><small>{signedPercent(data.daily_return_percent)}</small></div>
        <div><span>Open positions</span><strong>{data.open_positions}</strong><small>{money(data.cash_usd)} cash · {cashPercent.toFixed(1)}%</small></div>
      </section>

      <section className="r2d2-scoreboard" aria-label="Daily performance scoreboard">
        {counters.map((counter) => (
          <div key={counter.label} className={`r2d2-counter r2d2-counter-${counter.tone}`}>
            <span>{counter.label}</span><strong>{counter.value}</strong><small>{counter.detail}</small>
          </div>
        ))}
      </section>

      <div className="r2d2-primary-grid">
        <section className="panel r2d2-track-panel">
          <header className="panel-header r2d2-track-header">
            <div><LineChart size={18} /><h2>Track Record</h2></div>
            <div className="r2d2-track-totals">
              <span className="r2d2-track-positive">Positive <strong>{data.stats.positive_transactions}</strong><em>{lifetimePositiveShare.toFixed(1)}%</em></span>
              <span className="r2d2-track-negative">Negative <strong>{data.stats.negative_transactions}</strong><em>{lifetimeNegativeShare.toFixed(1)}%</em></span>
              <small>{lifetimeClosedTrades} closed trades</small>
            </div>
          </header>
          <div className="r2d2-chart" role="img" aria-label="R2D2 Rising paper portfolio track record">
            <div className="r2d2-chart-scale"><span>{money(chartMax)}</span><span>{money((chartMax + chartMin) / 2)}</span><span>{money(chartMin)}</span></div>
            <div className="r2d2-chart-field">
              <i /><i /><i />
              <svg viewBox="0 0 720 170" preserveAspectRatio="none" aria-hidden="true">
                <path d={`M0 ${158 - ((center - chartMin) / (chartMax - chartMin)) * 146}H720`} className="r2d2-chart-baseline" />
                <path d={chartPath} className="r2d2-chart-line" />
                <circle cx="706" cy={lastY} r="5" />
              </svg>
              <div className="r2d2-chart-axis"><span>{data.start_date}</span><span>{data.operating_days_elapsed} days live</span><span>Continuous</span></div>
            </div>
          </div>
        </section>

        <section className="panel r2d2-intelligence-panel">
          <PanelHeader title="Intelligence Log" icon={Activity} />
          <div className="r2d2-intelligence-list">
            {intelligenceLog.length ? intelligenceLog.map((entry) => (
              <article className={`r2d2-intelligence-entry r2d2-intelligence-${entry.tone}`} key={entry.id}>
                <time>{new Date(entry.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "America/Sao_Paulo" })}</time>
                <span className="r2d2-intelligence-action">{entry.action}</span>
                <div>
                  <header><R2D2Ticker symbol={entry.symbol} name={entry.name} /><small>{entry.market}</small></header>
                  <p>{entry.rationale}</p>
                  <small>{entry.detail}</small>
                </div>
              </article>
            )) : <div className="r2d2-intelligence-empty"><Activity size={24} /><strong>No intelligence events today</strong><span>Trades and live position decisions will appear here as the engine evaluates the session.</span></div>}
          </div>
        </section>
      </div>

      <section className="panel r2d2-ledger-panel">
        <PanelHeader title="Virtual Positions" icon={WalletCards} />
        <div className="r2d2-ledger-head">
          <span>Asset</span><span>Price</span><span>Allocation</span><span>Position value</span><span>P&amp;L</span><span>Technical</span><span>Trend / Flow</span><span>Stop</span><span>Decision</span>
        </div>
        {data.positions.length ? data.positions.map((position) => (
          <div className="r2d2-ledger-row" key={`${position.market}-${position.symbol}`}>
            <div className="r2d2-asset-cell">
              <div className="r2d2-company-logo"><CompanyLogo logoUrl={position.logo_url} symbol={position.symbol} /></div>
              <R2D2Ticker symbol={position.symbol} name={position.name} />
            </div>
            <span className="r2d2-last-price">{formatCurrency(position.last_price_local, position.currency)}</span>
            <span>{position.allocation_percent.toFixed(1)}%</span>
            <strong className="r2d2-position-value">{moneyExact(position.market_value_usd)}</strong>
            <div className="r2d2-live-pnl">
              <strong className={position.unrealized_pnl_usd >= 0 ? "positive" : "negative"}>{signedPercent(position.unrealized_return_percent)}</strong>
              <span className={position.unrealized_pnl_usd >= 0 ? "positive" : "negative"}>
                {`${position.unrealized_pnl_usd >= 0 ? "+" : "-"}${moneyExact(Math.abs(position.unrealized_pnl_usd))}`}
              </span>
              <small className={position.quote_status === "live" ? "positive" : "muted"}>
                {position.quote_status === "live" ? "LIVE" : "LAST MARK"}
                {position.quote_as_of ? ` · ${new Date(position.quote_as_of).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : ""}
              </small>
            </div>
            <div><strong>{position.technical_score.toFixed(0)}/100</strong><small>{position.data_status}</small></div>
            <div><strong>{position.trend_state}</strong><small>{position.volume_state}</small></div>
            <span>{formatCurrency(position.stop_price_local, position.currency)}</span>
            <div><strong>{position.decision_state}</strong><small>{position.quantity.toLocaleString("en-US", { maximumFractionDigits: 3 })} shares</small></div>
          </div>
        )) : <div className="r2d2-ledger-empty"><Target size={24} /><div><strong>No paper positions yet</strong><span>The first eligible cycle begins when the exchanges open on 17/08/2026.</span></div></div>}
      </section>

      <section className="panel r2d2-allocation-panel">
        <PanelHeader title="Portfolio Allocation" icon={ChartPie} />
        <div className="r2d2-allocation-content">
          <div className="r2d2-donut-wrap">
            <svg className="r2d2-donut" viewBox="0 0 180 180" role="img" aria-label="Virtual portfolio allocation by asset and cash">
              <circle className="r2d2-donut-track" cx="90" cy="90" r={donutRadius} />
              {allocationSlices.map((item) => (
                <circle
                  key={`${item.label}-${item.detail}`}
                  className={`r2d2-donut-slice${hoveredAllocation?.label === item.label ? " r2d2-donut-slice-active" : ""}${hoveredAllocation && hoveredAllocation.label !== item.label ? " r2d2-donut-slice-muted" : ""}`}
                  cx="90"
                  cy="90"
                  r={donutRadius}
                  stroke={item.color}
                  strokeDasharray={`${item.percent / 100 * donutCircumference} ${donutCircumference}`}
                  strokeDashoffset={-item.start * donutCircumference}
                  tabIndex={0}
                  aria-label={`${item.label}, ${item.name}, ${item.percent.toFixed(1)}% da carteira, ${moneyExact(item.value)}`}
                  onPointerEnter={(event) => showAllocationTooltip(event, item)}
                  onPointerMove={(event) => showAllocationTooltip(event, item)}
                  onPointerLeave={() => setHoveredAllocation(null)}
                  onFocus={(event) => {
                    const bounds = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
                    if (!bounds) return;
                    setHoveredAllocation({ ...item, x: bounds.width / 2, y: 28 });
                  }}
                  onBlur={() => setHoveredAllocation(null)}
                >
                  <title>{`${item.label} · ${item.name} · ${item.percent.toFixed(1)}% · ${moneyExact(item.value)}`}</title>
                </circle>
              ))}
            </svg>
            <div className="r2d2-donut-center"><span>NAV</span><strong>{money(data.nav_usd)}</strong><small>{data.open_positions} positions + cash</small></div>
            {hoveredAllocation ? (
              <div
                className="r2d2-donut-tooltip"
                role="tooltip"
                style={{ left: hoveredAllocation.x, top: hoveredAllocation.y }}
              >
                <strong>{hoveredAllocation.label}</strong>
                <span>{hoveredAllocation.name}</span>
                <small>{hoveredAllocation.detail} · {moneyExact(hoveredAllocation.value)} · {hoveredAllocation.percent.toFixed(1)}%</small>
              </div>
            ) : null}
          </div>
          <div className="r2d2-allocation-legend">
            {allocationItems.map((item) => (
              <div
                key={`${item.label}-${item.detail}`}
                className={hoveredAllocation?.label === item.label ? "r2d2-allocation-legend-active" : undefined}
              >
                <i style={{ backgroundColor: item.color }} />
                <span className="r2d2-allocation-logo">
                  {item.label === "Cash"
                    ? <img src={item.logoUrl ?? "/market-marks/usd.svg"} alt="USD" />
                    : <CompanyLogo logoUrl={item.logoUrl} symbol={item.label} />}
                </span>
                <div>{item.label === "Cash" ? <strong>Cash</strong> : <R2D2Ticker symbol={item.label} name={item.name} />}<small>{item.detail}</small></div>
                <span>{moneyExact(item.value)}</span>
                <b>{item.percent.toFixed(1)}%</b>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel r2d2-learning-panel">
        <header className="panel-header r2d2-learning-header">
          <div><Brain size={18} /><h2>Learning Curve</h2></div>
          {learningCurve.length ? (
            <div className="r2d2-learning-summary">
              <span>Média móvel (5d)<strong>{learningLastMovingAverage.toFixed(1)}%</strong></span>
              <span>Dias operados<strong>{learningCurve.length}</strong></span>
              <small className={`r2d2-learning-trend-${learningTrendTone}`}>{learningTrendLabel}</small>
            </div>
          ) : null}
        </header>
        <div className="r2d2-learning-scroll" ref={learningScrollRef}>
          {learningCurve.length ? (
            <svg
              className="r2d2-learning-svg"
              viewBox={`0 0 ${learningChartWidth} ${LEARNING_CHART_HEIGHT}`}
              width={learningChartWidth}
              height={LEARNING_CHART_HEIGHT}
              role="img"
              aria-label="Curva de aprendizado: percentual diário de operações positivas, com linha de média móvel de 5 dias"
            >
              {[0, 25, 50, 75, 100].map((tick) => {
                const y = LEARNING_PLOT_TOP + LEARNING_PLOT_HEIGHT - (tick / 100) * LEARNING_PLOT_HEIGHT;
                return (
                  <g key={tick}>
                    <line x1={LEARNING_PLOT_LEFT} x2={learningChartWidth} y1={y} y2={y} className="r2d2-learning-grid" />
                    <text x={LEARNING_PLOT_LEFT - 6} y={y + 3} textAnchor="end" className="r2d2-learning-tick">{tick}%</text>
                  </g>
                );
              })}
              {learningCurve.map((point, index) => {
                const x = LEARNING_PLOT_LEFT + index * learningSlot + (learningSlot - learningBarWidth) / 2;
                const barHeight = Math.max((point.positive_percent / 100) * LEARNING_PLOT_HEIGHT, 1.5);
                const y = LEARNING_PLOT_TOP + LEARNING_PLOT_HEIGHT - barHeight;
                const label = new Date(`${point.session_date}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
                return (
                  <g key={point.session_date}>
                    <rect
                      x={x}
                      y={y}
                      width={learningBarWidth}
                      height={barHeight}
                      rx={2}
                      className="r2d2-learning-bar-positive"
                    >
                      <title>{`${label} · ${point.positive_percent.toFixed(1)}% positivas (${point.positive_trades}/${point.positive_trades + point.negative_trades} operações)`}</title>
                    </rect>
                    <text x={x + learningBarWidth / 2} y={LEARNING_PLOT_TOP + LEARNING_PLOT_HEIGHT + 15} textAnchor="middle" className="r2d2-learning-axis-label">{label}</text>
                  </g>
                );
              })}
              {learningMovingAveragePoints.length > 1 ? (
                <path d={learningMovingAveragePath} className="r2d2-learning-ma-line" />
              ) : null}
              {learningMovingAveragePoints.map((point, index) => (
                <circle key={`ma-${learningCurve[index].session_date}`} cx={point.x} cy={point.y} r={2.5} className="r2d2-learning-ma-dot">
                  <title>{`Média móvel 5 dias em ${learningCurve[index].session_date}: ${learningMovingAverage[index].toFixed(1)}%`}</title>
                </circle>
              ))}
              {learningMovingAveragePoints.length ? (
                <g>
                  <rect x={learningChartWidth - 104} y={4} width={100} height={18} rx={9} className="r2d2-learning-ma-badge" />
                  <circle cx={learningChartWidth - 92} cy={13} r={3.5} className="r2d2-learning-ma-dot" />
                  <text x={learningChartWidth - 84} y={13} className="r2d2-learning-ma-label">{`MM5 ${learningLastMovingAverage.toFixed(1)}%`}</text>
                </g>
              ) : null}
            </svg>
          ) : (
            <div className="r2d2-ledger-empty"><Brain size={24} /><div><strong>Sem dias operados ainda</strong><span>A curva de aprendizado aparece após o primeiro dia com vendas encerradas.</span></div></div>
          )}
        </div>
      </section>

      <section className="panel r2d2-trades-panel">
        <header className="panel-header r2d2-trades-header">
          <div><BookOpenCheck size={18} /><h2>Daily Buy / Sell Log</h2></div>
          <div className="r2d2-trade-summary" aria-label="Resumo das transações">
            <span className="positive" title="Vendas encerradas hoje com P&L realizado positivo"><b>{todayPositiveTrades}</b> positivas</span>
            <span className="negative" title="Vendas encerradas hoje com P&L realizado negativo"><b>{todayNegativeTrades}</b> negativas</span>
          </div>
        </header>
        <div className="r2d2-trade-head"><span>Time</span><span>Side</span><span>Asset</span><span>Market</span><span>Quantity</span><span>Cash transaction</span><span>Realized P&amp;L</span><span>Decision rationale</span></div>
        {todayTrades.length ? todayTrades.map((trade) => {
          const sideTone = trade.side === "BUY"
            ? "buy"
            : trade.realized_pnl_usd !== null && trade.realized_pnl_usd > 0
              ? "sell-positive"
              : trade.realized_pnl_usd !== null && trade.realized_pnl_usd < 0
                ? "sell-negative"
                : "sell-flat";
          const cashTransaction = trade.side === "BUY"
            ? -(trade.gross_value_usd + trade.fees_usd)
            : trade.gross_value_usd - trade.fees_usd;

          return (
            <div className="r2d2-trade-row" key={trade.id}>
              <time>{new Date(trade.executed_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>
              <b className={`r2d2-side r2d2-side-${sideTone}`}>{trade.side}</b>
              <R2D2Ticker symbol={trade.symbol} name={trade.name} /><span>{trade.market}</span>
              <span>{trade.quantity.toLocaleString("en-US", { maximumFractionDigits: 3 })}</span>
              <strong className={`r2d2-cash-transaction r2d2-cash-${sideTone}`} title={trade.side === "BUY" ? "Saída líquida de caixa" : "Entrada líquida de caixa"}>
                {`${cashTransaction >= 0 ? "+" : "-"}${moneyExact(Math.abs(cashTransaction))}`}
              </strong>
              <span className={`r2d2-realized-pnl ${trade.realized_pnl_usd === null ? "r2d2-pnl-open" : trade.realized_pnl_usd > 0 ? "positive" : trade.realized_pnl_usd < 0 ? "negative" : "r2d2-pnl-flat"}`}>
                {trade.realized_pnl_usd === null ? <b>—</b> : <><strong>{`${trade.realized_pnl_usd >= 0 ? "+" : "-"}${moneyExact(Math.abs(trade.realized_pnl_usd))}`}</strong><small>{trade.realized_return_percent === null ? "—" : signedPercent(trade.realized_return_percent)}</small></>}
              </span>
              <p>{trade.reason}</p>
            </div>
          );
        }) : <div className="r2d2-ledger-empty"><BookOpenCheck size={24} /><div><strong>No executions today</strong><span>Today&apos;s virtual fills and rationales will appear here.</span></div></div>}
      </section>

      <footer className="r2d2-cycle-strip">
        <ShieldCheck size={15} />
        <span>Last cycle: <strong>{data.last_cycle?.status ?? "initialized"}</strong></span>
        <span>Scanned: <strong>{data.last_cycle?.scanned_count ?? 0}</strong></span>
        <span>Signals: <strong>{data.last_cycle?.signal_count ?? 0}</strong></span>
        <span>Trades: <strong>{data.last_cycle?.trade_count ?? 0}</strong></span>
        <span>Method: <strong>{data.methodology_version}</strong></span>
        <span>Learning: <strong>v{data.learning.version} · {data.learning.effective_date}</strong></span>
      </footer>

      <section className="panel r2d2-gates-panel r2d2-gates-horizontal">
        <PanelHeader title="Launch Gates" icon={ShieldCheck} />
        <div className="r2d2-gates-horizontal-body">
          <div className="r2d2-gate-list">
            {launchChecks.map((check) => (
              <div key={check.label}>
                <span className={`r2d2-gate-dot r2d2-gate-${check.state}`} />
                <div><strong>{check.label}</strong><small>{check.detail}</small></div>
                <b>{check.state === "ready" ? "READY" : "REVIEW"}</b>
              </div>
            ))}
          </div>
          <footer className="r2d2-gates-foot">
            <LockKeyhole size={14} />
            <span>Live brokerage execution remains technically absent and locked.</span>
          </footer>
        </div>
      </section>
    </div>
  );
}

function R2D2Ticker({ symbol, name }: { symbol: string; name: string }) {
  return (
    <span className="r2d2-ticker" tabIndex={0} aria-label={`${symbol}: ${name}`}>
      <strong>{symbol}</strong>
      <span className="r2d2-ticker-tooltip" role="tooltip">{name}</span>
    </span>
  );
}

function C3POOpeningView({ onEnter }: { onEnter: () => void }) {
  const stars = useMemo(() => Array.from({ length: 96 }, (_, index) => {
    const size = 1 + ((index * 17) % 3);
    return {
      left: `${(index * 47 + 11) % 100}%`,
      top: `${(index * 83 + 7) % 100}%`,
      width: `${size}px`,
      height: `${size}px`,
      opacity: 0.28 + ((index * 13) % 58) / 100,
      animationDelay: `${-((index * 0.37) % 4).toFixed(2)}s`
    };
  }), []);

  useEffect(() => {
    const skipOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onEnter();
    };
    const autoEnter = window.setTimeout(onEnter, 67_000);
    window.addEventListener("keydown", skipOnEscape);
    return () => {
      window.clearTimeout(autoEnter);
      window.removeEventListener("keydown", skipOnEscape);
    };
  }, [onEnter]);

  return (
    <section className="c3po-opening" aria-labelledby="c3po-opening-title">
      <div className="c3po-opening-stars" aria-hidden="true">
        {stars.map((style, index) => <i key={index} style={style} />)}
      </div>
      <button className="c3po-opening-skip" type="button" onClick={onEnter} aria-label="Pular introdução e entrar no Falcon CAPCOM">
        <span>Pular introdução</span>
        <ChevronRight size={17} />
      </button>

      <p className="c3po-opening-distance">Há muito tempo, numa galáxia muito, muito distante...</p>

      <div className="c3po-opening-logo" aria-hidden="true">
        <C3POProtocolIcon size={154} />
        <strong>C3PO</strong>
        <span>Chief of Staff Intelligence</span>
      </div>

      <div className="c3po-opening-viewport">
        <article className="c3po-opening-crawl">
          <p className="c3po-opening-episode">EPISÓDIO I</p>
          <h1 id="c3po-opening-title">A INTELIGÊNCIA DESPERTA</h1>
          <p>
            Em uma realidade onde mercados, empresas, contas, notícias e decisões mudam a cada instante,
            nasce o C3PO: um Chief of Staff digital privado, criado para transformar sinais dispersos em
            clareza executiva.
          </p>
          <p>
            Conectado à B3, Nasdaq e NYSE, aos dados financeiros, aos comunicados oficiais, ao Open Finance
            e às rotinas do dia, o sistema observa, compara e registra cada movimento. Sua metodologia combina
            valuation, consenso, risco, fundamentos e inteligência acumulada para revelar oportunidades e
            proteger decisões.
          </p>
          <p>
            A cada nova informação, o C3PO aprende. Valuations são revistos, alertas ganham contexto e o
            histórico preserva o motivo de cada mudança. Morning, Lunch e Night Summaries permanecem como
            registros do tempo, enquanto a plataforma evolui continuamente.
          </p>
          <p>
            Sua missão é simples: entregar a Dudu uma visão única, confiável e acionável do que exige atenção
            agora, do que pode criar valor amanhã e de como cada decisão foi construída.
          </p>
          <p className="c3po-opening-mission">Este é o centro de comando.<br />A inteligência está online.</p>
        </article>
      </div>

    </section>
  );
}

function MillenniumFalconView({ systemHealth }: { systemHealth: SystemHealthData | null }) {
  const [r2d2, setR2d2] = useState<R2D2DashboardData | null>(null);
  const [indices, setIndices] = useState<LiveMarketItem[]>([]);
  const [health, setHealth] = useState<SystemHealthData | null>(systemHealth);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);
  const r2d2RequestInFlight = useRef(false);
  const marketRequestInFlight = useRef(false);

  const loadR2D2 = useCallback(async () => {
    if (r2d2RequestInFlight.current) return;
    r2d2RequestInFlight.current = true;
    try {
      const response = await fetch(`${API_URL}/api/v1/r2d2`, { cache: "no-store", credentials: "include" });
      if (!response.ok) throw new Error(`R2D2 API ${response.status}`);
      if (mountedRef.current) setR2d2(await response.json());
    } catch (requestError) {
      if (mountedRef.current) setError(requestError instanceof Error ? requestError.message : "R2D2 unavailable");
    } finally {
      r2d2RequestInFlight.current = false;
    }
  }, []);

  const loadIndices = useCallback(async () => {
    if (marketRequestInFlight.current) return;
    marketRequestInFlight.current = true;
    try {
      const [indexResponse, marketResponse] = await Promise.all([
        fetch(`${API_URL}/api/v1/markets/live/index`, { cache: "no-store", credentials: "include" }),
        fetch(`${API_URL}/api/v1/markets/live`, { cache: "no-store", credentials: "include" })
      ]);
      if (!indexResponse.ok || !marketResponse.ok) throw new Error(`Markets API ${indexResponse.ok ? marketResponse.status : indexResponse.status}`);
      const indexPayload: LiveMarketIndexResponse = await indexResponse.json();
      const marketPayload: LiveMarketsResponse = await marketResponse.json();
      const promotedSymbols = ["Nikkei", "Shanghai", "DAX"];
      const promoted = promotedSymbols
        .map((symbol) => (marketPayload.groups["Future Index"] ?? []).find((item) => item.symbol === symbol))
        .filter((item): item is LiveMarketItem => Boolean(item));
      if (mountedRef.current) setIndices([...indexPayload.items, ...promoted]);
    } catch (requestError) {
      if (mountedRef.current) setError(requestError instanceof Error ? requestError.message : "Indices unavailable");
    } finally {
      marketRequestInFlight.current = false;
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/system-health`, { cache: "no-store", credentials: "include" });
      if (response.ok && mountedRef.current) setHealth(await response.json());
    } catch {
      // The last valid readiness bar remains visible during transient failures.
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void loadR2D2();
    void loadIndices();
    void loadHealth();
    const r2d2Timer = window.setInterval(() => document.visibilityState === "visible" && void loadR2D2(), 2_000);
    const marketTimer = window.setInterval(() => document.visibilityState === "visible" && void loadIndices(), 10_000);
    const healthTimer = window.setInterval(() => document.visibilityState === "visible" && void loadHealth(), 60_000);
    return () => {
      mountedRef.current = false;
      window.clearInterval(r2d2Timer);
      window.clearInterval(marketTimer);
      window.clearInterval(healthTimer);
    };
  }, [loadHealth, loadIndices, loadR2D2]);

  const usd = (value: number) => new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2
  }).format(value).replace("$", "US$ ");
  const signedUsd = (value: number) => `${value >= 0 ? "+" : "-"}${usd(Math.abs(value))}`;
  const saoPauloDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });
  const todayKey = saoPauloDate.format(new Date());
  const todayTrades = r2d2?.trades.filter((trade) => saoPauloDate.format(new Date(trade.executed_at)) === todayKey) ?? [];
  const todayPositiveTransactions = todayTrades.filter((trade) => (trade.realized_pnl_usd ?? 0) > 0).length;
  const todayNegativeTransactions = todayTrades.filter((trade) => (trade.realized_pnl_usd ?? 0) < 0).length;
  const todayClosedTransactions = todayPositiveTransactions + todayNegativeTransactions;
  const todayPositiveShare = todayClosedTransactions > 0 ? todayPositiveTransactions / todayClosedTransactions * 100 : 0;
  const todayNegativeShare = todayClosedTransactions > 0 ? todayNegativeTransactions / todayClosedTransactions * 100 : 0;
  const healthHeadline = health?.status === "healthy"
    ? "All services operational"
    : health?.status === "offline"
      ? "Service interruption detected"
      : "Conditions require attention";
  const healthTone = !health ? "warning" : health.quality >= 100 ? "good" : health.quality >= 80 ? "warning" : "critical";
  const dailyConsumption = health?.api_usage?.[0] ?? null;

  return (
    <div className="falcon-view falcon-capcom-view">
      <section className="falcon-capcom-metrics" aria-label="R2D2 mission telemetry">
        <div className="falcon-capcom-identity">
          <MillenniumFalconIcon size={42} />
          <div><span>R2D2 live telemetry</span><strong>{r2d2?.experiment_code ?? "Connecting"}</strong><small>2-second mission refresh</small></div>
        </div>
        <FalconMetric label="Net Asset Value" value={r2d2 ? usd(r2d2.nav_usd) : "—"} detail={`${r2d2?.open_positions ?? 0} open positions`} tone="gold" />
        <FalconMetric label="Daily P&L" value={r2d2 ? signedUsd(r2d2.daily_pnl_usd) : "—"} detail={r2d2 ? `${r2d2.daily_return_percent >= 0 ? "+" : ""}${r2d2.daily_return_percent.toFixed(2)}% today` : "Waiting for R2D2"} tone={(r2d2?.daily_pnl_usd ?? 0) >= 0 ? "green" : "red"} />
        <FalconMetric label="Positive Transactions" value={`${todayPositiveTransactions}`} secondaryValue={`${todayPositiveShare.toFixed(1)}%`} detail={`of ${todayClosedTransactions} closed trades today`} tone="green" />
        <FalconMetric label="Negative Transactions" value={`${todayNegativeTransactions}`} secondaryValue={`${todayNegativeShare.toFixed(1)}%`} detail={`of ${todayClosedTransactions} closed trades today`} tone="red" />
      </section>

      {error && <div className="error-banner"><AlertTriangle size={18} /><span>{error}</span><button onClick={() => { setError(""); void loadR2D2(); void loadIndices(); }}>Retry</button></div>}

      <section className="panel live-market-panel live-market-panel-cards live-market-panel-index falcon-capcom-index">
        <div className="live-market-group-head">
          <div><span>Index</span><strong>{indices.length} instruments</strong></div>
          <small>Same canonical feed as Master Luke</small>
        </div>
        <div className="live-market-table">
          <div className="live-market-table-head"><span>Instrument</span><span>Price</span><span>Change</span><span>Session range</span><span>Quote</span></div>
          {indices.map((item) => <LiveMarketRow key={item.symbol} item={item} />)}
          {!indices.length && <div className="falcon-panel-loading" />}
        </div>
      </section>

      <div className={`quality-banner quality-${healthTone} falcon-capcom-readiness falcon-capcom-readiness-with-usage`}>
        <div className="quality-score">{health?.quality ?? 0}%</div>
        <div><span>Storm Troops Readiness</span><strong>{healthHeadline}</strong><small>{health ? `${health.healthy_count}/${health.total_count} services operational · ${formatDate(health.generated_at)}` : "Collecting service conditions"}</small></div>
        <div className="quality-meter"><span style={{ width: `${health?.quality ?? 0}%` }} /></div>
        <div className={`falcon-capcom-consumption api-usage-${dailyConsumption?.status ?? "healthy"}`}>
          <header>
            <div><ServiceLogo name={dailyConsumption?.provider ?? "EODHD"} groupKey="quotes" /><span>Daily Consumption</span></div>
            <strong>{dailyConsumption ? `${dailyConsumption.percent_used.toFixed(1).replace(".", ",")}%` : "—"}</strong>
          </header>
          <div className="api-usage-meter"><span style={{ width: `${Math.min(100, dailyConsumption?.percent_used ?? 0)}%` }} /></div>
          <small>{dailyConsumption ? `${dailyConsumption.used.toLocaleString("pt-BR")} of ${dailyConsumption.limit.toLocaleString("pt-BR")} calls` : "Collecting API usage"}</small>
        </div>
      </div>
    </div>
  );
}

function FalconMetric({ label, value, secondaryValue, detail, tone }: { label: string; value: string; secondaryValue?: string; detail: string; tone: "gold" | "blue" | "green" | "red" }) {
  return <div className={`falcon-flight-metric falcon-flight-${tone}`}><span>{label}</span><strong>{value}{secondaryValue ? <em> · {secondaryValue}</em> : null}</strong><small>{detail}</small></div>;
}

function MarketsView() {
  const [snapshot, setSnapshot] = useState<LiveMarketsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [indexError, setIndexError] = useState("");
  const mountedRef = useRef(true);
  const snapshotRef = useRef<LiveMarketsResponse | null>(null);
  const indexItemsRef = useRef<LiveMarketItem[] | null>(null);
  const indexRequestInFlight = useRef(false);

  const loadMarkets = useCallback(async () => {
    if (!snapshotRef.current) setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/markets/live`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      if (!mountedRef.current) return;
      const nextSnapshot = indexItemsRef.current
        ? { ...payload, groups: { ...payload.groups, Index: indexItemsRef.current } }
        : payload;
      snapshotRef.current = nextSnapshot;
      setSnapshot(nextSnapshot);
    } catch (requestError) {
      if (mountedRef.current) setError(requestError instanceof Error ? requestError.message : "Live markets unavailable");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const loadIndices = useCallback(async () => {
    if (indexRequestInFlight.current) return;
    indexRequestInFlight.current = true;
    try {
      const response = await fetch(`${API_URL}/api/v1/markets/live/index`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload: LiveMarketIndexResponse = await response.json();
      if (!response.ok) throw new Error(`API ${response.status}`);
      if (!mountedRef.current) return;
      setIndexError("");
      indexItemsRef.current = payload.items;
      setSnapshot((current) => {
        if (!current) return current;
        const nextSnapshot = {
          ...current,
          generated_at: payload.generated_at,
          groups: { ...current.groups, Index: payload.items }
        };
        snapshotRef.current = nextSnapshot;
        return nextSnapshot;
      });
    } catch (requestError) {
      if (mountedRef.current) setIndexError(requestError instanceof Error ? requestError.message : "Live indices unavailable");
    } finally {
      indexRequestInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    loadMarkets();
    loadIndices();
    const marketsInterval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadMarkets();
    }, 10_000);
    const indexInterval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadIndices();
    }, 10_000);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        loadMarkets();
        loadIndices();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      mountedRef.current = false;
      window.clearInterval(marketsInterval);
      window.clearInterval(indexInterval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [loadIndices, loadMarkets]);

  const groupOrder = ["Index", "Future Index", "Currencies", "Crypto"];
  const promotedIndexSymbols = ["Nikkei", "Shanghai", "DAX"];
  const futureItems = snapshot?.groups["Future Index"] ?? [];
  const promotedIndexItems = promotedIndexSymbols
    .map((symbol) => futureItems.find((item) => item.symbol === symbol))
    .filter((item): item is LiveMarketItem => Boolean(item));
  const displayGroups: Record<string, LiveMarketItem[]> = snapshot ? {
    ...snapshot.groups,
    Index: [...(snapshot.groups.Index ?? []), ...promotedIndexItems],
    "Future Index": futureItems.filter((item) => !promotedIndexSymbols.includes(item.symbol))
  } : {};
  const visibleMarketItems = groupOrder.flatMap((group) => displayGroups[group] ?? []);
  const itemCount = visibleMarketItems.length;
  const staleCount = visibleMarketItems.filter((item) => item.status === "stale").length;
  const latestQuote = visibleMarketItems.reduce<string | undefined>((latest, item) => {
    if (!latest || new Date(item.as_of) > new Date(latest)) return item.as_of;
    return latest;
  }, undefined);

  return (
    <div className="content-stack live-markets-view">
      {loading && !snapshot ? <LiveMarketsLoading /> : snapshot && (
        <div className="live-market-grid">
          {groupOrder.map((group) => {
            const items = displayGroups[group] ?? [];
            return (
              <section className={`panel live-market-panel live-market-panel-cards live-market-panel-${group.toLowerCase().replace(/\s+/g, "-")}`} key={group}>
                <div className="live-market-group-head">
                  <div><span>{group}</span><strong>{items.length} instruments</strong></div>
                  <small>{marketGroupSourceLabel(group)}</small>
                </div>
                <div className="live-market-table">
                  <div className="live-market-table-head"><span>Instrument</span><span>Price</span><span>Change</span><span>Session range</span><span>Quote</span></div>
                  {items.map((item) => <LiveMarketRow key={item.symbol} item={item} />)}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <section className="panel live-markets-control">
        <PanelHeader title="Live Market Feed" icon={MasterLukeIcon} />
        <div className="live-market-summary">
          <div><span>Coverage</span><strong>{itemCount}</strong><small>tracked instruments</small></div>
          <div><span>Refresh</span><strong>10s</strong><small>somente enquanto Master Luke estiver visível</small></div>
          <div><span>Sources</span><strong>2</strong><small>EODHD + global public feed</small></div>
          <div><span>Fallbacks</span><strong className={staleCount ? "negative-text" : "positive-text"}>{staleCount}</strong><small>stale quotes retained</small></div>
          <div className="live-market-clock"><span><i /> Feed active</span><strong>{formatDate(latestQuote ?? snapshot?.generated_at)}</strong><small>automatic · no page refresh</small></div>
        </div>
        {(error || indexError) && <div className="screen-error"><AlertTriangle size={17} /><span>{error || indexError}</span></div>}
        {!!snapshot?.errors.length && <div className="live-market-warning"><AlertTriangle size={14} /><span>{snapshot.errors.length} source exception(s); last valid prices remain visible.</span></div>}
      </section>

      {snapshot && (
        <section className="panel live-market-method">
          <PanelHeader title="Feed Discipline" icon={ShieldCheck} />
          <div><p>{snapshot.methodology.global}</p><p>{snapshot.methodology.refresh}</p><p>{snapshot.methodology.fallback}</p></div>
        </section>
      )}
    </div>
  );
}

function LiveMarketRow({ item }: { item: LiveMarketItem }) {
  const direction: Direction = (item.change_percent ?? 0) > 0 ? "up" : (item.change_percent ?? 0) < 0 ? "down" : "flat";
  const range = item.low !== null && item.high !== null && item.high > item.low
    ? Math.max(0, Math.min(100, ((item.price - item.low) / (item.high - item.low)) * 100))
    : 50;
  return (
    <article className="live-market-row">
      <div className="live-market-instrument">
        <MarketInstrumentMark symbol={item.symbol} name={item.name} />
        <div>
          <InstrumentPreviewTarget
            instrument={{ symbol: item.symbol, name: item.name, market: item.group }}
            className="live-market-ticker-preview"
          >
            <strong>{item.symbol}</strong>
          </InstrumentPreviewTarget>
          <span>{item.name}</span>
        </div>
      </div>
      <div className="live-market-price"><strong>{formatLiveMarketPrice(item)}</strong><span>{item.currency}</span></div>
      <div className={`live-market-change change-${direction}`}><DirectionIcon direction={direction} /><strong>{formatPercent(item.change_percent, 2)}</strong></div>
      <div className="live-market-range">
        <div><i style={{ left: `${range}%` }} /></div>
        <span>{item.low !== null ? formatLiveMarketPrice({ ...item, price: item.low }) : "N/D"}</span>
        <span>{item.high !== null ? formatLiveMarketPrice({ ...item, price: item.high }) : "N/D"}</span>
      </div>
      <div className="live-market-quote"><span className={`market-state market-state-${item.status}`}>{item.status}</span><strong>{formatDate(item.as_of)}</strong><small>{item.provider} · ~{item.delay_minutes}m</small></div>
    </article>
  );
}

const marketIndexMarks: Record<string, string> = {
  "S&P 500 Fut.": "/market-marks/sp500.svg",
  "Nasdaq Fut.": "/market-marks/nasdaq.svg",
  Nikkei: "/market-marks/nikkei.svg",
  DAX: "/market-marks/dax.svg",
  Shanghai: "/market-marks/shanghai.svg",
  US3Y: "/market-marks/us-treasury.svg",
  US10Y: "/market-marks/us-treasury.svg",
  IBOV: "/market-marks/b3.svg",
  NASDAQ: "/market-marks/nasdaq.svg",
  NYSE: "/market-marks/nyse.svg"
};

const marketInstrumentMarks: Record<string, string> = {
  ...marketIndexMarks,
  "USD/BRL": "/market-marks/usd.svg",
  "EUR/BRL": "/market-marks/euro.svg",
  "GBP/BRL": "/market-marks/pound.svg",
  BTC: "/market-marks/btc.svg",
  ETH: "/market-marks/eth.svg",
  SOL: "/market-marks/sol.svg",
  BONK: "/market-marks/bonk.svg",
  DOGE: "/market-marks/doge.svg"
};

function MarketInstrumentMark({ symbol, name }: { symbol: string; name: string }) {
  const source = marketInstrumentMarks[symbol] ?? "/market-marks/global-index.svg";
  return <span className="market-index-mark"><img src={source} alt={`${name} mark`} /></span>;
}

function marketGroupSourceLabel(group: string) {
  if (group === "Index") return "B3, Nasdaq, NYSE and global benchmarks · automatic 10-second refresh";
  if (group === "Future Index") return "US futures and Treasury yields";
  return "EODHD All-In-One";
}

function LiveMarketsLoading() {
  return <div className="live-market-loading">{Array.from({ length: 4 }).map((_, index) => <div key={index} />)}</div>;
}

function RealTimeView({ canManage, canDelete }: { canManage: boolean; canDelete: boolean }) {
  const [activeMarket, setActiveMarket] = useState<RealtimeTabKey>(() => {
    if (typeof window === "undefined") return "B3";
    const requested = new URLSearchParams(window.location.search).get("market")?.toUpperCase();
    return ["B3", "NASDAQ", "NYSE", "PORTFOLIO"].includes(requested ?? "") ? requested as RealtimeTabKey : "B3";
  });
  const [snapshots, setSnapshots] = useState<Partial<Record<RealtimeMarketKey, RealtimeMarketResponse>>>({});
  const [portfolio, setPortfolio] = useState<RealtimePortfolioResponse | null>(null);
  const [loadingMarket, setLoadingMarket] = useState<RealtimeTabKey | null>("B3");
  const [error, setError] = useState("");
  const mountedRef = useRef(true);
  const snapshot = activeMarket === "PORTFOLIO" ? null : snapshots[activeMarket];

  const selectRealtimeMarket = (market: RealtimeTabKey) => {
    setActiveMarket(market);
    const params = new URLSearchParams(window.location.search);
    params.set("view", "realtime");
    params.set("market", market.toLowerCase());
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  };

  const loadMarket = useCallback(async (market: RealtimeTabKey) => {
    setLoadingMarket(market);
    setError("");
    try {
      const endpoint = market === "PORTFOLIO" ? "portfolio/items" : market.toLowerCase();
      const response = await fetch(`${API_URL}/api/v1/realtime/${endpoint}`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      if (!mountedRef.current) return;
      if (market === "PORTFOLIO") setPortfolio(payload);
      else setSnapshots((current) => ({ ...current, [market]: payload }));
    } catch (requestError) {
      if (mountedRef.current) setError(requestError instanceof Error ? requestError.message : "Real-time market feed unavailable");
    } finally {
      if (mountedRef.current) setLoadingMarket(null);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    loadMarket(activeMarket);
    const refreshMilliseconds = activeMarket === "B3" ? 60_000 : 3_000;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadMarket(activeMarket);
    }, refreshMilliseconds);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") loadMarket(activeMarket);
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      mountedRef.current = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [activeMarket, loadMarket]);

  const tables: { key: keyof Pick<RealtimeMarketResponse, "gainers" | "losers" | "volume_leaders" | "cash_leaders">; title: string; detail: string; tone: string; metric: "volume" | "cash" }[] = [
    { key: "gainers", title: "Top Gainers", detail: "5 maiores altas da sessão", tone: "positive", metric: "volume" },
    { key: "losers", title: "Top Losers", detail: "5 maiores quedas da sessão", tone: "negative", metric: "volume" },
    { key: "volume_leaders", title: "Volume Leaders", detail: "Maior quantidade de ações negociadas", tone: "volume", metric: "volume" },
    { key: "cash_leaders", title: "Cash Leaders", detail: "Maior volume financeiro estimado", tone: "cash", metric: "cash" }
  ];

  return (
    <div className="content-stack realtime-view">
      <section className="panel realtime-control">
        <div className="realtime-tabs" role="tablist" aria-label="Hyperspace exchanges">
          {([
            { key: "B3", label: "B3", logo: "/market-marks/b3.svg" },
            { key: "NASDAQ", label: "NASDAQ", logo: "/market-marks/nasdaq.svg" },
            { key: "NYSE", label: "NYSE", logo: "/market-marks/nyse.svg" },
            { key: "PORTFOLIO", label: "My Portfolio", logo: "/market-marks/my-portfolio.svg" }
          ] as { key: RealtimeTabKey; label: string; logo: string }[]).map((market) => (
            <button
              key={market.key}
              role="tab"
              aria-selected={activeMarket === market.key}
              className={activeMarket === market.key ? "realtime-tab realtime-tab-active" : "realtime-tab"}
              onClick={() => selectRealtimeMarket(market.key)}
            >
              <img src={market.logo} alt="" className="realtime-tab-logo" />
              {market.label}
            </button>
          ))}
          <button className="realtime-refresh" onClick={() => loadMarket(activeMarket)} disabled={loadingMarket === activeMarket} title="Atualizar agora">
            <RefreshCw size={15} className={loadingMarket === activeMarket ? "spin" : ""} />
            <span>Atualizar</span>
          </button>
        </div>

        {snapshot && activeMarket !== "PORTFOLIO" && (
          <div className="realtime-index-band">
            <div className="realtime-index-mark"><LineChart size={22} /></div>
            <div className="realtime-index-name">
              <span>Índice de referência</span>
              <strong>{snapshot.index.name}</strong>
              <InstrumentPreviewTarget
                instrument={{ symbol: snapshot.index.symbol, name: snapshot.index.name, market: "Indices" }}
                className="realtime-index-ticker-preview"
              >
                <small>{snapshot.index.symbol}</small>
              </InstrumentPreviewTarget>
            </div>
            <div className="realtime-index-value"><span>Último</span><strong>{formatRealtimeNumber(snapshot.index.value)}</strong><small>{snapshot.index.currency}</small></div>
            <div className={`realtime-index-change ${(snapshot.index.change_percent ?? 0) >= 0 ? "positive-text" : "negative-text"}`}>
              <span>Variação</span><strong>{formatPercent(snapshot.index.change_percent, 2)}</strong><small>Sessão atual</small>
            </div>
            <div className="realtime-index-meta"><span className={`market-state market-state-${snapshot.index.status}`}>{snapshot.index.status}</span><strong>{formatDate(snapshot.index.as_of)}</strong><small>{snapshot.source} · ranking ~{snapshot.delay_minutes} min</small></div>
            <div className="realtime-universe"><span>Universo analisado</span><strong>{snapshot.universe_size.toLocaleString("pt-BR")}</strong><small>ações válidas</small></div>
          </div>
        )}
        {error && <div className="screen-error"><AlertTriangle size={17} /><span>{error}</span></div>}
      </section>

      {activeMarket === "PORTFOLIO" ? (
        portfolio || loadingMarket !== "PORTFOLIO"
          ? <MyRealtimePortfolio snapshot={portfolio} loading={loadingMarket === "PORTFOLIO"} onChanged={setPortfolio} canManage={canManage} canDelete={canDelete} />
          : <RealTimeLoading compact />
      ) : !snapshot && loadingMarket ? <RealTimeLoading /> : snapshot && (
        <div className="realtime-leader-grid">
          {tables.map((table) => (
            <RealtimeLeaderTable
              key={table.key}
              title={table.title}
              detail={table.detail}
              tone={table.tone}
              metric={table.metric}
              items={snapshot[table.key]}
              market={activeMarket}
            />
          ))}
        </div>
      )}

      {(snapshot || portfolio) && (
        <div className="realtime-footnote">
          <ShieldCheck size={14} />
          <span>Atualização automática a cada {(snapshot ?? portfolio)?.refresh_seconds ?? 60}s enquanto esta aba estiver visível.</span>
          <small>{activeMarket === "PORTFOLIO"
            ? "Carteira salva no C3PO; papéis dos EUA usam WebSocket quando marcados LIVE."
            : activeMarket === "B3"
              ? "Brapi Pro · melhor cotação disponível próxima de 5 min."
              : "Ranking amplo T-15; preços visíveis usam WebSocket quando marcados LIVE."}</small>
        </div>
      )}
    </div>
  );
}

function MyRealtimePortfolio({
  snapshot,
  loading,
  onChanged,
  canManage,
  canDelete
}: {
  snapshot: RealtimePortfolioResponse | null;
  loading: boolean;
  onChanged: (snapshot: RealtimePortfolioResponse) => void;
  canManage: boolean;
  canDelete: boolean;
}) {
  const [symbol, setSymbol] = useState("");
  const [mutating, setMutating] = useState("");
  const [error, setError] = useState("");
  const [symbolSuggestions, setSymbolSuggestions] = useState<RealtimePortfolioSymbolSuggestion[]>([]);
  const [searchingSymbols, setSearchingSymbols] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const symbolSearchRef = useRef<HTMLDivElement>(null);
  const symbolInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const closeSuggestions = (event: PointerEvent) => {
      if (!symbolSearchRef.current?.contains(event.target as Node)) setSuggestionsOpen(false);
    };
    window.addEventListener("pointerdown", closeSuggestions);
    return () => window.removeEventListener("pointerdown", closeSuggestions);
  }, []);

  useEffect(() => {
    const query = symbol.trim();
    if (!query) {
      setSymbolSuggestions([]);
      setSearchingSymbols(false);
      setSuggestionError("");
      return;
    }
    const controller = new AbortController();
    const debounce = window.setTimeout(async () => {
      setSearchingSymbols(true);
      setSuggestionError("");
      try {
        const params = new URLSearchParams({ q: query, limit: "8" });
        const response = await fetch(`${API_URL}/api/v1/realtime/portfolio/search?${params.toString()}`, {
          cache: "no-store",
          credentials: "include",
          signal: controller.signal
        });
        const payload: RealtimePortfolioSymbolSearchResponse & { detail?: string } = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
        setSymbolSuggestions(payload.items);
        setActiveSuggestionIndex(0);
        if (payload.errors.length && !payload.items.length) setSuggestionError("Não foi possível consultar todos os mercados.");
      } catch (requestError) {
        if (!(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setSymbolSuggestions([]);
          setSuggestionError("Busca de ativos temporariamente indisponível.");
        }
      } finally {
        if (!controller.signal.aborted) setSearchingSymbols(false);
      }
    }, 180);
    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [symbol]);

  const persistSymbol = async (rawSymbol: string) => {
    if (!canManage) return;
    const normalized = rawSymbol.trim().toUpperCase();
    if (!normalized || mutating) return;
    setMutating(normalized);
    setError("");
    setSuggestionsOpen(false);
    try {
      const response = await fetch(`${API_URL}/api/v1/realtime/portfolio/items`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: normalized })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      onChanged(payload);
      setSymbol("");
      setSymbolSuggestions([]);
      setSuggestionError("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível adicionar o ativo");
    } finally {
      setMutating("");
    }
  };

  const addSymbol = async (event: FormEvent) => {
    event.preventDefault();
    await persistSymbol(symbol);
  };

  const chooseSuggestion = (suggestion: RealtimePortfolioSymbolSuggestion) => {
    setSymbol(suggestion.symbol);
    setSuggestionsOpen(false);
    setActiveSuggestionIndex(0);
    setError("");
    symbolInputRef.current?.focus();
  };

  const handleSymbolKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setSuggestionsOpen(false);
      return;
    }
    if (!suggestionsOpen || !symbolSuggestions.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (index + 1) % symbolSuggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (index - 1 + symbolSuggestions.length) % symbolSuggestions.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      void persistSymbol(symbolSuggestions[activeSuggestionIndex]?.symbol ?? symbol);
    }
  };
  const exactSymbolSuggestion = symbolSuggestions.some((suggestion) => suggestion.symbol === symbol.trim().toUpperCase());

  const removeSymbol = async (ticker: string) => {
    if (!canDelete) return;
    setMutating(ticker);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/realtime/portfolio/items/${encodeURIComponent(ticker)}`, {
        method: "DELETE",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      onChanged(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível remover a ação");
    } finally {
      setMutating("");
    }
  };

  return (
    <section className="panel realtime-portfolio-panel">
      <div className="realtime-portfolio-toolbar">
        <div>
          <span>My Portfolio</span>
          <strong>{snapshot?.item_count ?? 0} ativos acompanhados</strong>
          <small>{snapshot?.sources.length ? snapshot.sources.join(" + ") : "Adicione o primeiro ticker para começar"}</small>
        </div>
        {canManage ? <form className="realtime-portfolio-form" onSubmit={addSymbol}>
          <label htmlFor="realtime-portfolio-symbol">Ticker</label>
          <div>
            <div className="realtime-portfolio-symbol-search" ref={symbolSearchRef}>
              <Search size={17} className="realtime-portfolio-symbol-icon" />
              <input
                ref={symbolInputRef}
                id="realtime-portfolio-symbol"
                value={symbol}
                onChange={(event) => {
                  setSymbol(event.target.value.toUpperCase());
                  setSuggestionsOpen(true);
                  setError("");
                }}
                onFocus={() => setSuggestionsOpen(true)}
                onKeyDown={handleSymbolKeyDown}
                placeholder="Digite ticker ou empresa"
                maxLength={80}
                autoComplete="off"
                spellCheck={false}
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={suggestionsOpen && !!symbol.trim()}
                aria-controls="realtime-portfolio-symbol-suggestions"
                aria-activedescendant={symbolSuggestions[activeSuggestionIndex] ? `portfolio-symbol-${symbolSuggestions[activeSuggestionIndex].market}-${symbolSuggestions[activeSuggestionIndex].symbol}` : undefined}
              />
              {searchingSymbols && <RefreshCw size={14} className="spin realtime-portfolio-symbol-spinner" />}
              {suggestionsOpen && !!symbol.trim() && (
                <div className="realtime-portfolio-suggestions" id="realtime-portfolio-symbol-suggestions" role="listbox">
                  {symbolSuggestions.map((suggestion, index) => (
                    <button
                      type="button"
                      id={`portfolio-symbol-${suggestion.market}-${suggestion.symbol}`}
                      className={index === activeSuggestionIndex ? "realtime-portfolio-suggestion realtime-portfolio-suggestion-active" : "realtime-portfolio-suggestion"}
                      key={`${suggestion.market}-${suggestion.symbol}`}
                      onClick={() => chooseSuggestion(suggestion)}
                      onMouseEnter={() => setActiveSuggestionIndex(index)}
                      role="option"
                      aria-selected={index === activeSuggestionIndex}
                    >
                      <span className="realtime-portfolio-suggestion-symbol">{suggestion.symbol}</span>
                      <span className="realtime-portfolio-suggestion-copy">
                        <strong>{suggestion.name}</strong>
                        <small>{suggestion.market} · {suggestion.security_type}</small>
                      </span>
                      {suggestion.already_tracked
                        ? <em><Check size={12} /> Acompanhado</em>
                        : <ChevronRight size={15} />}
                    </button>
                  ))}
                  {!symbolSuggestions.length && !searchingSymbols && (
                    <div className="realtime-portfolio-suggestion-empty">
                      <Search size={15} />
                      <span>{suggestionError || "Nenhum ativo encontrado"}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
            <button type="submit" disabled={!exactSymbolSuggestion || !!mutating} title="Selecione uma ação ou ETF válido">
              <Plus size={16} />
              <span>Adicionar</span>
            </button>
          </div>
        </form> : <div className="realtime-portfolio-readonly"><ShieldCheck size={17} /><div><strong>Carteira protegida</strong><span>Inclusões são exclusivas do proprietário.</span></div></div>}
      </div>

      {error && <div className="screen-error"><AlertTriangle size={17} /><span>{error}</span></div>}
      {!!snapshot?.errors.length && <div className="live-market-warning"><AlertTriangle size={14} /><span>{snapshot.errors.join(" · ")}</span></div>}

      {loading && !snapshot ? <div className="realtime-portfolio-skeleton" /> : snapshot?.items.length ? (
        <div className="realtime-portfolio-table">
          <div className="realtime-portfolio-head">
            <span>Asset</span><span>Market</span><span>Price</span><span>Change</span><span>Volume</span><span>Cash volume</span><span>Quote</span><span />
          </div>
          {snapshot.items.map((item) => (
            <div className="realtime-portfolio-row" key={item.symbol}>
              <div className="realtime-portfolio-company">
                <InstrumentPreviewTarget
                  instrument={{ symbol: item.symbol, name: item.name, market: item.market }}
                  className="realtime-portfolio-ticker-preview"
                >
                  <strong>{item.symbol}</strong>
                </InstrumentPreviewTarget>
                <span>{item.name}</span>
              </div>
              <span className="realtime-portfolio-market">{item.market}</span>
              <strong className="realtime-portfolio-price">{item.status === "stale" ? "N/D" : formatCurrency(item.price, item.currency)}</strong>
              {item.status === "stale" ? (
                <span className="realtime-portfolio-change">N/D</span>
              ) : (
                <span className={`realtime-portfolio-change ${item.change_percent >= 0 ? "change-up" : "change-down"}`}>
                  <DirectionIcon direction={item.change_percent >= 0 ? "up" : "down"} size={13} />{formatPercent(item.change_percent, 2)}
                </span>
              )}
              <span className="realtime-portfolio-volume">{item.status === "stale" ? "N/D" : formatCompact(item.volume)}</span>
              <span className="realtime-portfolio-cash">{item.status === "stale" ? "N/D" : formatCompact(item.cash_volume)}</span>
              <div className="realtime-portfolio-quote"><span className={`market-state market-state-${item.status}`}>{item.status}</span><small>{formatDate(item.as_of)} · ~{item.delay_minutes}m</small></div>
              {canDelete ? <button className="realtime-portfolio-delete" onClick={() => removeSymbol(item.symbol)} disabled={mutating === item.symbol} title={`Remover ${item.symbol}`} aria-label={`Remover ${item.symbol}`}>
                <Trash2 size={15} />
              </button> : <span className="realtime-portfolio-lock"><LockKeyhole size={14} /></span>}
            </div>
          ))}
        </div>
      ) : (
        <div className="realtime-portfolio-empty"><BriefcaseBusiness size={24} /><strong>Sua carteira em tempo real começa aqui</strong><span>Digite uma ação ou ETF da B3 ou dos mercados dos Estados Unidos, incluindo OTC.</span></div>
      )}
    </section>
  );
}

const RealtimePortfolioIntradayPreview = forwardRef<HTMLDivElement, {
  item: InstrumentPreviewDescriptor;
  data?: RealtimePortfolioIntradayResponse;
  loading: boolean;
  error?: string;
  position: { left: number; top: number; width: number };
  pinned: boolean;
  onClose: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}>(function RealtimePortfolioIntradayPreview({
  item,
  data,
  loading,
  error,
  position,
  pinned,
  onClose,
  onMouseEnter,
  onMouseLeave
}, ref) {
  const chart = useMemo(() => {
    if (!data?.points.length) return null;
    const width = 354;
    const height = 150;
    const padding = { top: 10, right: 8, bottom: 23, left: 44 };
    const prices = data.points.map((point) => point.price);
    const rawMin = Math.min(...prices);
    const rawMax = Math.max(...prices);
    const spread = Math.max(rawMax - rawMin, rawMax * 0.002);
    const min = rawMin - spread * 0.12;
    const max = rawMax + spread * 0.12;
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const coordinate = (point: RealtimePortfolioIntradayPoint, index: number) => ({
      x: padding.left + (data.points.length === 1 ? plotWidth / 2 : index * plotWidth / (data.points.length - 1)),
      y: padding.top + (max - point.price) * plotHeight / (max - min)
    });
    const coordinates = data.points.map(coordinate);
    const line = coordinates.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const area = `${padding.left},${padding.top + plotHeight} ${line} ${padding.left + plotWidth},${padding.top + plotHeight}`;
    const gridValues = [rawMax, (rawMax + rawMin) / 2, rawMin];
    const timeIndexes = Array.from(new Set([0, Math.floor((data.points.length - 1) / 2), data.points.length - 1]));
    return { width, height, padding, plotWidth, plotHeight, coordinates, line, area, gridValues, timeIndexes, rawMax, rawMin };
  }, [data]);

  return (
    <div
      ref={ref}
      className={`realtime-intraday-preview ${pinned ? "realtime-intraday-preview-pinned" : ""}`}
      style={position}
      role="dialog"
      aria-label={`Gráfico intradiário de ${item.symbol}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="realtime-intraday-head">
        <div>
          <span>{data ? (data.series_kind === "daily" ? "Últimos 30 fechamentos" : `Sessão ${new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(new Date(`${data.session_date}T12:00:00`))}`) : "Gráfico intradiário"}</span>
          <strong>{item.symbol}</strong>
          <small>{item.name}</small>
        </div>
        <button type="button" onClick={onClose} aria-label="Fechar gráfico"><X size={16} /></button>
      </div>
      {loading && !data ? (
        <div className="realtime-intraday-loading"><RefreshCw className="spin" size={18} /><span>Carregando pregão...</span></div>
      ) : error && !data ? (
        <div className="realtime-intraday-error"><AlertTriangle size={18} /><span>{error}</span></div>
      ) : data && chart ? (
        <>
          <div className="realtime-intraday-summary">
            <div><span>Último</span><strong>{formatIntradayPrice(data.current, data.currency, data.market)}</strong></div>
            <div className={data.change_percent >= 0 ? "change-up" : "change-down"}>
              <DirectionIcon direction={data.change_percent >= 0 ? "up" : "down"} size={15} />
              <strong>{formatPercent(data.change_percent, 2)}</strong><small>{data.series_kind === "daily" ? "vs. fechamento anterior" : "desde a abertura"}</small>
            </div>
          </div>
          <div className="realtime-intraday-chart">
            <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={`Evolução de ${item.symbol} ao longo do pregão`}>
              {chart.gridValues.map((value, index) => {
                const y = chart.padding.top + index * chart.plotHeight / 2;
                return <g key={`${value}-${index}`}>
                  <line x1={chart.padding.left} y1={y} x2={chart.padding.left + chart.plotWidth} y2={y} />
                  <text x={chart.padding.left - 6} y={y + 3} textAnchor="end">{value.toFixed(2)}</text>
                </g>;
              })}
              <polygon points={chart.area} />
              <polyline points={chart.line} />
              {chart.timeIndexes.map((index) => {
                const point = chart.coordinates[index];
                const time = new Intl.DateTimeFormat(
                  "pt-BR",
                  data.series_kind === "daily" ? { day: "2-digit", month: "2-digit" } : { hour: "2-digit", minute: "2-digit" }
                ).format(new Date(data.points[index].as_of));
                return <text className="realtime-intraday-time" key={`${time}-${index}`} x={point.x} y={chart.height - 5} textAnchor={index === 0 ? "start" : index === data.points.length - 1 ? "end" : "middle"}>{time}</text>;
              })}
              <circle cx={chart.coordinates.at(-1)?.x} cy={chart.coordinates.at(-1)?.y} r="4" />
            </svg>
          </div>
          <div className="realtime-intraday-metrics">
            <span>Low <strong>{formatIntradayPrice(data.low, data.currency, data.market)}</strong></span>
            <span>High <strong>{formatIntradayPrice(data.high, data.currency, data.market)}</strong></span>
            <span className={`market-state market-state-${data.status}`}>{data.status}</span>
          </div>
          <div className="realtime-intraday-source"><span>{data.source}</span><small>{data.series_kind === "daily" ? "diário · fechamento oficial" : `${data.interval_minutes}m · atraso ~${data.delay_minutes}m`}</small></div>
        </>
      ) : null}
    </div>
  );
});

function RealtimeLeaderTable({
  title,
  detail,
  tone,
  metric,
  items,
  market
}: {
  title: string;
  detail: string;
  tone: string;
  metric: "volume" | "cash";
  items: RealtimeMarketLeader[];
  market: RealtimeMarketKey;
}) {
  return (
    <section className={`panel realtime-leader-panel realtime-leader-${tone}`}>
      <div className="realtime-leader-head">
        <div><span>{title}</span><small>{detail}</small></div>
        {tone === "positive" ? <TrendingUp size={18} /> : tone === "negative" ? <TrendingDown size={18} /> : <Activity size={18} />}
      </div>
      <div className="realtime-table-wrap">
        <div className="realtime-table-head"><span>#</span><span>Company</span><span>Price</span><span>Change</span><span>{metric === "cash" ? "Cash" : "Volume"}</span></div>
        {items.map((item, index) => (
          <div className="realtime-table-row" key={item.symbol}>
            <span className="realtime-rank">{index + 1}</span>
            <div className="realtime-company">
              <div className="realtime-symbol-line"><InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.name, market }}><strong>{item.symbol}</strong></InstrumentPreviewTarget><span className={`market-state market-state-${item.status}`}>{item.status}</span></div>
              <span>{item.name}</span>
            </div>
            <strong className="realtime-price">{formatCurrency(item.price, item.currency)}</strong>
            <span className={item.change_percent >= 0 ? "change-up" : "change-down"}>
              <DirectionIcon direction={item.change_percent >= 0 ? "up" : "down"} size={13} />
              {formatPercent(item.change_percent, 2)}
            </span>
            <strong className="realtime-volume">{formatCompact(metric === "cash" ? item.cash_volume : item.volume)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatRealtimeNumber(value: number) {
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function RealTimeLoading({ compact = false }: { compact?: boolean }) {
  return <div className={`realtime-loading ${compact ? "realtime-loading-compact" : ""}`}>{Array.from({ length: compact ? 1 : 4 }).map((_, index) => <div key={index} />)}</div>;
}

function PortfolioView({ data, portfolio }: { data: CommandCenterData; portfolio: PortfolioItem[] }) {
  return (
    <div className="content-stack">
      <div className="feature-strip">
        <div><span>Billfish FIA</span><strong>{data.billfish.net_worth ?? "Not available"}</strong><small>Status {data.billfish.status ?? "pending"}</small></div>
        <div><span>Daily change</span><strong className={data.billfish.daily_change?.startsWith("-") ? "negative-text" : "positive-text"}>{data.billfish.daily_change ?? "N/D"}</strong><small>{data.billfish.source ?? "Source pending"}</small></div>
        <div><span>Net worth change</span><strong>{data.billfish.net_worth_change ?? "N/D"}</strong><small>Latest BTG snapshot</small></div>
      </div>
      <section className="panel">
        <PanelHeader title="Portfolio Stocks" icon={BriefcaseBusiness} />
        <div className="data-table">
          <div className="data-table-head"><span>Company</span><span>Price</span><span>Change</span><span>Signal</span></div>
          {portfolio.map((item) => (
            <div className="data-table-row" key={item.symbol}>
              <div className="company-cell"><div className="company-monogram">{item.symbol.slice(0, 2)}</div><InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.symbol }}><strong>{item.symbol}</strong></InstrumentPreviewTarget></div>
              <strong>{item.price}</strong>
              <span className={`change-${item.direction}`}><DirectionIcon direction={item.direction} />{item.change}</span>
              <span className="status-label status-observe">Observe</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function CandidatesView({ reports, marketProviders }: { reports: ReportItem[]; marketProviders: MarketDataProvider[] }) {
  const [activeMarket, setActiveMarket] = useState<ResearchMarket>("B3");
  const [screen, setScreen] = useState<B3CandidateResponse | null>(null);
  const [screenLoading, setScreenLoading] = useState(true);
  const [screenError, setScreenError] = useState("");
  const screenRequestRef = useRef(0);

  const loadScreen = useCallback(async (refresh = false) => {
    const requestId = ++screenRequestRef.current;
    setScreenLoading(true);
    setScreenError("");
    try {
      const request = () => fetch(`${API_URL}/api/v1/candidates/${activeMarket.toLowerCase()}?refresh=${refresh ? "true" : "false"}`, {
        cache: "no-store",
        credentials: "include"
      });
      let response = await request();
      if ([502, 503, 504].includes(response.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 1200));
        response = await request();
      }
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) {
        throw new Error("Last Jedi is reconnecting to the valuation service. Please retry in a moment.");
      }
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      if (requestId === screenRequestRef.current) setScreen(payload);
    } catch (requestError) {
      if (requestId === screenRequestRef.current) {
        setScreenError(requestError instanceof Error ? requestError.message : "Screening unavailable");
      }
    } finally {
      if (requestId === screenRequestRef.current) setScreenLoading(false);
    }
  }, [activeMarket]);

  useEffect(() => {
    setScreen(null);
    loadScreen(false);
  }, [loadScreen]);

  const providerStatus = (code: MarketDataProvider["code"]) => {
    const provider = marketProviders.find((item) => item.code === code);
    if (!provider || provider.status === "unconfigured") return "Awaiting credential";
    if (provider.status === "attention") return "Configured · validation pending";
    return `Operational · ${provider.plan}`;
  };
  const coverage = [
    { market: "B3", universe: "350", source: "Brapi Pro + BCB macro", status: providerStatus("brapi") },
    { market: "NASDAQ", universe: "300", source: "EODHD + public coverage", status: providerStatus("eodhd") },
    { market: "NYSE", universe: "300", source: "EODHD + public coverage", status: providerStatus("eodhd") },
    { market: "ETFs", universe: "50", source: "EODHD fund data", status: providerStatus("eodhd") }
  ];
  return (
    <div className="content-stack">
      <section className="panel candidate-ranking-panel">
        <div className="research-market-tabs" role="tablist" aria-label="Last Jedi markets">
          {(["B3", "NASDAQ", "NYSE"] as ResearchMarket[]).map((market) => (
            <button key={market} role="tab" aria-selected={activeMarket === market} className={activeMarket === market ? "active" : ""} onClick={() => setActiveMarket(market)}>{market}</button>
          ))}
        </div>
        <PanelHeader title={`Top 10 ${activeMarket}`} icon={Target} />
        <div className="screen-summary-bar">
          <div><span>Universe</span><strong>{screen?.universe_size ?? (activeMarket === "B3" ? 350 : 325)}</strong><small>{activeMarket === "B3" ? "liquid stocks" : "stocks + ETFs"}</small></div>
          <div><span>Strict matches</span><strong>{screen?.items.length ?? "—"}</strong><small>{screen ? `${screen.eligible_count} passed data gates` : "hard entry gates"}</small></div>
          <div><span>Methodology</span><strong>{screen ? `v${screen.methodology_version}` : "—"}</strong><small>{screen?.methodology ?? "C3PO canonical valuation"}</small></div>
          <div><span>Source</span><strong>{screen?.source ?? (activeMarket === "B3" ? "Brapi Pro" : "EODHD All-In-One")}</strong><small>{screen ? formatDate(screen.generated_at) : "loading"}</small></div>
          <button className="screen-refresh" onClick={() => loadScreen(true)} disabled={screenLoading} title={`Recarregar o ultimo screening diario da ${activeMarket}`}>
            <RefreshCw size={16} className={screenLoading ? "spin" : ""} />
            <span>{screenLoading ? "Updating" : "Refresh"}</span>
          </button>
        </div>

        {screenError && <div className="screen-error"><AlertTriangle size={17} /><span>{screenError}</span><button onClick={() => loadScreen(true)}>Retry</button></div>}
        {screenLoading && !screen ? <CandidateTableLoading /> : screen && screen.items.length === 0 ? (
          <div className="candidate-empty-state">
            No company currently clears every Power Zone, confidence, dispersion and entry gate in today's validated snapshot.
          </div>
        ) : screen && (
          <div className="candidate-live-table-wrap">
            <table className="candidate-live-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Company</th>
                  <th>Price</th>
                  <th>C3PO TP</th>
                  <th>Buy-in</th>
                  <th>Multiples</th>
                  <th>Score / Risk</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {screen.items.map((item) => (
                  <tr key={item.symbol}>
                    <td><span className="candidate-rank">{String(item.rank).padStart(2, "0")}</span></td>
                    <td>
                      <div className="candidate-company">
                        <div className="candidate-logo">
                          <CompanyLogo logoUrl={item.logo_url} symbol={item.symbol} />
                        </div>
                        <div className={item.security_type === "ETF" ? "candidate-etf" : ""}><InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.name, market: activeMarket }}><strong>{item.symbol}</strong></InstrumentPreviewTarget><span>{item.name}</span><small title={`${item.sector_source ?? "Sector source pending"} · confidence ${item.sector_confidence?.toFixed(0) ?? "N/D"}/100`}>{item.security_type} · {item.valuation_profile} · {item.sector}</small></div>
                      </div>
                    </td>
                    <td>
                      <div className="candidate-number"><strong>{formatResearchPrice(item.price, activeMarket)}</strong><span className={(item.change_percent ?? 0) >= 0 ? "change-up" : "change-down"}><DirectionIcon direction={(item.change_percent ?? 0) > 0 ? "up" : (item.change_percent ?? 0) < 0 ? "down" : "flat"} />{formatPercent(item.change_percent)}</span></div>
                    </td>
                    <td>
                      <div className="candidate-number candidate-target">
                        <strong>{formatResearchPrice(item.our_tp, activeMarket)}</strong><span>{formatPercent(item.upside_percent)}</span>
                        <small>TP validated {item.tp_validation_score.toFixed(0)}/100{item.consensus_gap_percent !== null ? ` · gap ${item.consensus_gap_percent.toFixed(1)}%` : ""}</small>
                        <small>Internal {formatResearchPrice(item.internal_tp, activeMarket)} · {(100 - item.consensus_weight_percent).toFixed(0)}%</small>
                        <small>Expected 12M {formatPercent(item.expected_total_return_percent)}</small>
                        {item.public_consensus_tp ? <small>Consensus {formatResearchPrice(item.public_consensus_tp, activeMarket)} · {item.consensus_weight_percent.toFixed(0)}%{item.analyst_count ? ` · ${item.analyst_count} analysts` : ""}</small> : <small>{item.security_type === "ETF" ? "ETF model · no analyst consensus" : "Consensus unavailable · 0%"}</small>}
                      </div>
                    </td>
                    <td>
                      <div className="candidate-number" title={Object.entries(item.buy_in_models).map(([name, value]) => `${name}: ${formatResearchPrice(value, activeMarket)}`).join(" · ")}><strong>{formatResearchPrice(item.buy_in, activeMarket)}</strong><span className={item.price_vs_buy_in_percent <= 15 ? "entry-near" : "entry-far"}>{formatPercent(item.price_vs_buy_in_percent)} vs entry</span><small>{item.security_type === "ETF" ? "Fund + market entry" : "Fundamental + market entry"}</small></div>
                    </td>
                    <td>
                      <div className="candidate-multiples" title={`ADTV 90d ${formatResearchPrice(item.average_daily_value_90d ?? 0, activeMarket)} · P/B ${formatMultiple(item.price_to_book)} · ROE ${formatPercent(item.roe_percent)} · FCF yield ${formatPercent(item.fcf_yield_percent)}`}>
                        <span>P/E <strong>{formatMultiple(item.pe)}</strong></span>
                        <span>FWRD P/E <strong>{formatMultiple(item.forward_pe)}</strong></span>
                        <span>EV/EBITDA <strong>{formatMultiple(item.ev_ebitda)}</strong></span>
                        <span>PEG <strong>{formatMultiple(item.peg)}</strong></span>
                      </div>
                    </td>
                    <td>
                      <div className="candidate-score" title={`Power Score ${item.score}/100 · Risk ${item.risk_score}/100 · TP validation ${item.tp_validation_score}/100 · Confidence ${item.valuation_confidence}/100 · Source agreement ${item.source_agreement_percent}% · ${item.data_source_count} sources · Dispersion ${item.method_dispersion_percent}%`}><strong>{item.score.toFixed(1)}</strong><span><i style={{ width: `${item.score}%` }} /></span><small>Risk {item.risk_score.toFixed(1)} · TP valid {item.tp_validation_score.toFixed(0)}</small></div>
                    </td>
                    <td>
                      <span className={`candidate-status candidate-status-${item.status}`} title={`${item.thesis} ${item.risk}`}>
                        {item.status === "full_match" ? "Full match" : item.status === "near_buy" ? "Near buy" : "Watchlist"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="screen-method-note">
          <ShieldCheck size={16} />
          <span>{screen ? `${screen.methodology} v${screen.methodology_version}` : "C3PO valuation model"}: official disclosures and market evidence are reconciled before the nightly valuation. Last Jedi remains restricted to independently validated C3PO Target Prices, ordered by upside.</span>
          {screen && screen.items.length > 0 && <small>As of {formatDate(screen.items[0]?.as_of)} · Market cap leader {formatCompact(Math.max(...screen.items.map((item) => item.market_cap ?? 0)))}</small>}
        </div>
      </section>

      <section className="panel">
        <PanelHeader title="Screening Coverage" icon={Target} />
        <div className="data-table candidate-table">
          <div className="data-table-head"><span>Market</span><span>Universe</span><span>Primary source</span><span>Status</span></div>
          {coverage.map((item) => (
            <div className="data-table-row" key={item.market}>
              <strong>{item.market}</strong><span>{item.universe}</span><span>{item.source}</span><span className={`status-label ${item.status.startsWith("Operational") ? "status-ok" : "status-pending"}`}>{item.status}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel">
        <PanelHeader title="Methodology Ledger" icon={ShieldCheck} />
        <div className="ledger-grid">
          <div><span>Canonical model</span><strong>Dark Side · Power Zone</strong></div>
          <div><span>Selection order</span><strong>Power Zone, then C3PO TP upside descending</strong></div>
          <div><span>TP upside gate</span><strong>{screen?.criteria.tp_upside ?? "C3PO TP upside >= Selic + 6 p.p."}</strong></div>
          <div><span>Risk gate</span><strong>{screen?.criteria.risk ?? "Below eligible-universe median"}</strong></div>
          <div><span>Confidence gate</span><strong>{screen?.criteria.confidence ?? "Confidence and method agreement"}</strong></div>
          <div><span>Buy-in framework</span><strong>Five institutional lenses + market structure</strong></div>
          <div><span>Valuation model</span><strong>Five sector-adapted methods</strong></div>
          <div><span>Power Score weights</span><strong>{screen?.criteria.score ?? "Return · risk · quality · confidence · entry"}</strong></div>
          <div><span>Published snapshots</span><strong>{reports.filter((report) => report.name.includes("summary")).length}</strong></div>
        </div>
      </section>
    </div>
  );
}

function MatrixPowerView() {
  const [activeMarket, setActiveMarket] = useState<ResearchMarket>("B3");
  const [matrix, setMatrix] = useState<MatrixPowerResponse | null>(null);
  const [matrixLoading, setMatrixLoading] = useState(true);
  const [matrixError, setMatrixError] = useState("");
  const [activeQuadrant, setActiveQuadrant] = useState<"all" | MatrixQuadrant>("all");
  const [signalFilter, setSignalFilter] = useState<"all" | "validated" | "provisional">("all");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [movements, setMovements] = useState<{ symbol: string; from: MatrixQuadrant; to: MatrixQuadrant }[]>([]);
  const matrixRef = useRef<MatrixPowerResponse | null>(null);
  const mountedRef = useRef(true);
  const matrixRequestRef = useRef(0);

  const loadMatrix = useCallback(async () => {
    const requestId = ++matrixRequestRef.current;
    if (!matrixRef.current) setMatrixLoading(true);
    setMatrixError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/matrix-power/${activeMarket.toLowerCase()}`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      if (!mountedRef.current || requestId !== matrixRequestRef.current) return;
      const previous = matrixRef.current;
      if (previous) {
        const previousQuadrants = new Map(previous.items.map((item) => [item.symbol, item.quadrant]));
        setMovements(payload.items
          .filter((item: MatrixPowerItem) => previousQuadrants.has(item.symbol) && previousQuadrants.get(item.symbol) !== item.quadrant)
          .map((item: MatrixPowerItem) => ({ symbol: item.symbol, from: previousQuadrants.get(item.symbol) as MatrixQuadrant, to: item.quadrant }))
          .slice(0, 8));
      }
      matrixRef.current = payload;
      setMatrix(payload);
    } catch (requestError) {
      if (mountedRef.current && requestId === matrixRequestRef.current) {
        setMatrixError(requestError instanceof Error ? requestError.message : "Dark Side unavailable");
      }
    } finally {
      if (mountedRef.current && requestId === matrixRequestRef.current) setMatrixLoading(false);
    }
  }, [activeMarket]);

  useEffect(() => {
    mountedRef.current = true;
    matrixRef.current = null;
    setMatrix(null);
    setSelectedSymbol(null);
    setMovements([]);
    loadMatrix();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadMatrix();
    }, 60_000);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") loadMatrix();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      mountedRef.current = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [loadMatrix]);

  const counts = useMemo(() => {
    const output: Record<MatrixQuadrant, number> = {
      high_return_low_risk: 0,
      high_return_high_risk: 0,
      low_return_low_risk: 0,
      low_return_high_risk: 0
    };
    matrix?.items.forEach((item) => { output[item.quadrant] += 1; });
    return output;
  }, [matrix]);

  const visibleItems = useMemo(() => {
    if (!matrix) return [];
    return matrix.items.filter((item) => (
      (activeQuadrant === "all" || item.quadrant === activeQuadrant)
      && (signalFilter === "all" || item.signal_quality === signalFilter)
    ));
  }, [activeQuadrant, matrix, signalFilter]);

  const selectedItem = useMemo(() => {
    if (!visibleItems.length) return null;
    return visibleItems.find((item) => item.symbol === selectedSymbol)
      ?? [...visibleItems].sort((left, right) => right.power_score - left.power_score)[0];
  }, [selectedSymbol, visibleItems]);

  const latestQuote = useMemo(() => {
    if (!matrix?.items.length) return matrix?.generated_at;
    return matrix.items.reduce((latest, item) => new Date(item.as_of) > new Date(latest) ? item.as_of : latest, matrix.items[0].as_of);
  }, [matrix]);

  return (
    <div className="content-stack matrix-power-view">
      <section className="panel matrix-control-panel">
        <div className="research-market-tabs" role="tablist" aria-label="Dark Side markets">
          {(["B3", "NASDAQ", "NYSE"] as ResearchMarket[]).map((market) => (
            <button key={market} role="tab" aria-selected={activeMarket === market} className={activeMarket === market ? "active" : ""} onClick={() => setActiveMarket(market)}>
              <img src={valuationMarketMarks[market]} alt="" className="research-market-tab-logo" />
              {market}
            </button>
          ))}
        </div>
        <PanelHeader title={`${activeMarket} Dark Side`} icon={DarkSideIcon} />
        <div className="matrix-summary-bar">
          <div><span>Universe</span><strong>{matrix?.universe_size ?? (activeMarket === "B3" ? 350 : 325)}</strong><small>{activeMarket === "B3" ? "B3 liquid stocks" : `${activeMarket} stocks + ETFs`}</small></div>
          <div><span>Calculated TPs</span><strong>{matrix?.coverage_audit?.calculated_tp ?? matrix?.source_eligible_count ?? "—"}</strong><small>{matrix?.source_eligible_count ?? "—"} cleared source gates</small></div>
          <div><span>Validated</span><strong>{matrix?.validated_count ?? "—"}</strong><small>eligible for Last Jedi</small></div>
          <div><span>Provisional</span><strong>{matrix?.provisional_count ?? "—"}</strong><small>Dark Side only · review required</small></div>
          <div><span>C3PO TP upside hurdle</span><strong>{matrix ? formatPercent(matrix.tp_upside_cutoff_percent) : "Selic + 6 p.p."}</strong><small>Expected Return is analytical only</small></div>
          <div><span>Risk divider</span><strong>{matrix?.risk_cutoff.toFixed(1) ?? "—"}</strong><small>min(40, filtered-universe median)</small></div>
          <div className="matrix-live-cell"><span><i /> Live Dark Side</span><strong>{formatDate(latestQuote)}</strong><small>auto · 60s · delayed {matrix?.provider_delay_minutes ?? 5}m</small></div>
        </div>
        <div className="matrix-segments" role="group" aria-label="Filter Dark Side quadrants">
          <button className={activeQuadrant === "all" ? "active" : ""} onClick={() => setActiveQuadrant("all")}>All <span>{matrix?.item_count ?? 0}</span></button>
          {matrixQuadrants.map((quadrant) => (
            <button key={quadrant.key} className={`${activeQuadrant === quadrant.key ? "active" : ""} segment-${quadrant.key}`} onClick={() => setActiveQuadrant(quadrant.key)}>
              {quadrant.shortLabel} <span>{counts[quadrant.key]}</span>
            </button>
          ))}
          <span className="matrix-segment-divider" />
          <button className={signalFilter === "all" ? "active" : ""} onClick={() => setSignalFilter("all")}>All evidence <span>{matrix?.item_count ?? 0}</span></button>
          <button className={`matrix-quality-validated ${signalFilter === "validated" ? "active" : ""}`} onClick={() => setSignalFilter("validated")}>Validated <span>{matrix?.validated_count ?? 0}</span></button>
          <button className={`matrix-quality-provisional ${signalFilter === "provisional" ? "active" : ""}`} onClick={() => setSignalFilter("provisional")}>Provisional <span>{matrix?.provisional_count ?? 0}</span></button>
        </div>
        {matrixError && <div className="screen-error"><AlertTriangle size={17} /><span>{matrixError}</span></div>}
      </section>

      {matrixLoading && !matrix ? <MatrixPowerLoading /> : matrix && (
        <section className="matrix-workspace">
          <div className="matrix-stage-scroll">
            <div className="matrix-stage" aria-label={`Live ${activeMarket} Dark Side risk-return quadrant`}>
              <div className="matrix-zone matrix-zone-power"><strong>POWER ZONE</strong><span>High TP upside · Low risk</span><b>{counts.high_return_low_risk}</b></div>
              <div className="matrix-zone matrix-zone-aggressive"><strong>AGGRESSIVE</strong><span>High TP upside · High risk</span><b>{counts.high_return_high_risk}</b></div>
              <div className="matrix-zone matrix-zone-defensive"><strong>DEFENSIVE</strong><span>Low TP upside · Low risk</span><b>{counts.low_return_low_risk}</b></div>
              <div className="matrix-zone matrix-zone-avoid"><strong>AVOID ZONE</strong><span>Low TP upside · High risk</span><b>{counts.low_return_high_risk}</b></div>
              <div className="matrix-line matrix-line-vertical"><span>Risk {matrix.risk_cutoff.toFixed(1)}</span></div>
              <div className="matrix-line matrix-line-horizontal"><span>TP upside {formatPercent(matrix.tp_upside_cutoff_percent)}</span></div>
              <span className="matrix-axis matrix-axis-return">C3PO TP UPSIDE</span>
              <span className="matrix-axis matrix-axis-risk">RISK SCORE</span>
              {visibleItems.map((item) => {
                const moved = movements.some((movement) => movement.symbol === item.symbol);
                return (
                  <button
                    key={item.symbol}
                    className={`matrix-node node-${item.quadrant} ${item.signal_quality === "provisional" ? "matrix-node-provisional" : ""} ${selectedItem?.symbol === item.symbol ? "matrix-node-selected" : ""} ${moved ? "matrix-node-moved" : ""}`}
                    style={{ left: `${item.x_percent}%`, bottom: `${item.y_percent}%` }}
                    onClick={() => setSelectedSymbol(item.symbol)}
                    title={`${item.symbol} · ${formatResearchPrice(item.price, activeMarket)} · TP upside ${formatPercent(item.tp_upside_percent)} · risco ${item.risk_score.toFixed(1)} · ${item.signal_quality === "validated" ? "valuation validado" : "valuation provisório"}`}
                    aria-label={`${item.symbol}, C3PO TP upside ${item.tp_upside_percent.toFixed(1)} percent, risk ${item.risk_score.toFixed(1)}`}
                  >
                    <InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.name, market: activeMarket }} nested pinOnClick={false} showIcon={false}><span className={item.security_type === "ETF" ? "matrix-etf-symbol" : ""} style={{ fontSize: item.symbol.length > 4 ? "6px" : "7px" }}>{item.symbol}</span></InstrumentPreviewTarget>
                  </button>
                );
              })}
            </div>
          </div>

          <aside className="matrix-inspector">
            {selectedItem && (
              <>
                <header>
                  <div className="matrix-inspector-logo"><CompanyLogo logoUrl={selectedItem.logo_url} symbol={selectedItem.symbol} /></div>
                  <div><span>{selectedItem.security_type} · {selectedItem.signal_quality === "validated" ? "Validated signal" : "Provisional analysis"}</span><InstrumentPreviewTarget instrument={{ symbol: selectedItem.symbol, name: selectedItem.name, market: activeMarket }}><strong className={selectedItem.security_type === "ETF" ? "matrix-etf-symbol" : ""}>{selectedItem.symbol}</strong></InstrumentPreviewTarget><small>{selectedItem.name}</small></div>
                </header>
                <div className={`matrix-quadrant-tag tag-${selectedItem.quadrant}`}>{matrixQuadrants.find((item) => item.key === selectedItem.quadrant)?.label}</div>
                <dl className="matrix-inspector-grid">
                  <div><dt>Price</dt><dd>{formatResearchPrice(selectedItem.price, activeMarket)} <span className={(selectedItem.change_percent ?? 0) >= 0 ? "change-up" : "change-down"}>{formatPercent(selectedItem.change_percent)}</span></dd></div>
                  <div><dt>C3PO TP upside</dt><dd>{formatPercent(selectedItem.tp_upside_percent)}</dd></div>
                  <div><dt>Expected return 12M</dt><dd>{formatPercent(selectedItem.expected_return_percent)}</dd></div>
                  <div><dt>Risk score</dt><dd>{selectedItem.risk_score.toFixed(1)}</dd></div>
                  <div><dt>Power score</dt><dd>{selectedItem.power_score.toFixed(1)}</dd></div>
                  <div><dt>Valuation confidence</dt><dd>{selectedItem.valuation_confidence.toFixed(1)}</dd></div>
                  <div><dt>Sector / peer group</dt><dd title={selectedItem.industry ?? undefined}>{selectedItem.sector}<span>{selectedItem.peer_group ? ` · ${selectedItem.peer_group}` : ""}</span></dd></div>
                  <div><dt>Sector validation</dt><dd>{selectedItem.sector_confidence?.toFixed(0) ?? "N/D"}/100 <span>{selectedItem.sector_source ?? "Pending"}</span></dd></div>
                  <div><dt>TP validation</dt><dd className={selectedItem.signal_quality === "validated" ? "positive-text" : "warning-text"}>{selectedItem.tp_validation_score.toFixed(1)}/100</dd></div>
                  <div><dt>Valuation methods</dt><dd>{selectedItem.internal_method_count} internal · {selectedItem.valuation_method_count} total</dd></div>
                  <div><dt>Method dispersion</dt><dd>{formatPercent(selectedItem.method_dispersion_percent)}</dd></div>
                  <div><dt>Source evidence</dt><dd>{selectedItem.data_source_count} sources</dd></div>
                  <div><dt>Source agreement</dt><dd>{selectedItem.source_agreement_percent.toFixed(1)}%</dd></div>
                  <div><dt>Valuation signal</dt><dd className={selectedItem.signal_quality === "validated" ? "positive-text" : "negative-text"}>{selectedItem.signal_quality === "validated" ? "Validated" : "Provisional"}</dd></div>
                  <div><dt>C3PO TP</dt><dd>{formatResearchPrice(selectedItem.our_tp, activeMarket)}</dd></div>
                  <div><dt>Internal model</dt><dd>{formatResearchPrice(selectedItem.internal_tp, activeMarket)} <span>{(100 - selectedItem.consensus_weight_percent).toFixed(0)}%</span></dd></div>
                  <div><dt>Market consensus</dt><dd>{selectedItem.public_consensus_tp !== null ? formatResearchPrice(selectedItem.public_consensus_tp, activeMarket) : selectedItem.security_type === "ETF" ? "ETF model" : "N/D"} <span>{selectedItem.consensus_weight_percent.toFixed(0)}%{selectedItem.analyst_count ? ` · ${selectedItem.analyst_count} analysts` : ""}</span></dd></div>
                  <div><dt>Internal/consensus gap</dt><dd>{selectedItem.consensus_gap_percent !== null ? formatPercent(selectedItem.consensus_gap_percent) : "N/D"}</dd></div>
                  <div><dt>Buy-in</dt><dd>{formatResearchPrice(selectedItem.buy_in, activeMarket)}</dd></div>
                  <div><dt>Beta</dt><dd>{selectedItem.beta?.toFixed(2) ?? "N/D"}</dd></div>
                  <div><dt>Volatility 90d</dt><dd>{selectedItem.volatility_90d_percent !== null ? formatPercent(selectedItem.volatility_90d_percent) : "N/D"}</dd></div>
                </dl>
                {selectedItem.signal_quality === "provisional" && selectedItem.tp_validation_reasons.length > 0 && (
                  <div className="matrix-evidence-gaps" title={selectedItem.tp_validation_reasons.join(" · ")}>
                    <AlertTriangle size={13} />
                    <span>{selectedItem.tp_validation_reasons.slice(0, 2).join(" · ")}</span>
                  </div>
                )}
                <footer><Clock3 size={14} /><span>Quote {formatDate(selectedItem.as_of)}</span></footer>
              </>
            )}
          </aside>
        </section>
      )}

      {matrix && (
        <>
          <section className="matrix-foot-grid">
            <div className="panel matrix-method-card"><PanelHeader title={`Dark Side Method · v${matrix.methodology_version}`} icon={ShieldCheck} /><p>{matrix.methodology.return}</p><p>{matrix.methodology.confidence}</p></div>
            <div className="panel matrix-movement-card"><PanelHeader title="Quadrant Moves" icon={Activity} />
              {movements.length ? <div>{movements.map((movement) => {
                const instrument = matrix.items.find((item) => item.symbol === movement.symbol);
                return (
                  <span key={movement.symbol}>
                    <strong>
                      {instrument ? (
                        <InstrumentPreviewTarget
                          instrument={{ symbol: instrument.symbol, name: instrument.name, market: activeMarket }}
                          nested
                          pinOnClick={false}
                        >
                          {movement.symbol}
                        </InstrumentPreviewTarget>
                      ) : movement.symbol}
                    </strong>
                    {matrixQuadrants.find((item) => item.key === movement.from)?.shortLabel} → {matrixQuadrants.find((item) => item.key === movement.to)?.shortLabel}
                  </span>
                );
              })}</div> : <p>No quadrant changes in this session.</p>}
            </div>
          </section>
          <section className="panel matrix-coverage-panel">
            <PanelHeader title="Coverage Audit" icon={Target} />
            <div className="matrix-coverage-grid">
              <div><span>Missing quote</span><strong>{matrix.coverage_audit.missing_quote ?? 0}</strong></div>
              <div><span>History gate</span><strong>{matrix.coverage_audit.insufficient_history ?? 0}</strong></div>
              <div><span>Size gate</span><strong>{matrix.coverage_audit.market_cap_gate ?? 0}</strong></div>
              <div><span>Liquidity gate</span><strong>{matrix.coverage_audit.liquidity_gate ?? 0}</strong></div>
              <div><span>Fundamental gate</span><strong>{matrix.coverage_audit.fundamental_quality_gate ?? 0}</strong></div>
              <div><span>Valuation review</span><strong>{matrix.coverage_audit.valuation_review ?? 0}</strong></div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function MatrixPowerLoading() {
  return <div className="matrix-loading"><div /><aside /></div>;
}

function CandidateTableLoading() {
  return <div className="candidate-loading" aria-label="Loading B3 screening">{Array.from({ length: 10 }).map((_, index) => <span key={index} />)}</div>;
}

function OnePagerView({ canGenerate }: { canGenerate: boolean }) {
  const [symbol, setSymbol] = useState(() => currentViewQuery().toUpperCase().replace(/\s/g, "").slice(0, 18));
  const [reports, setReports] = useState<OnePagerReport[]>([]);
  const [latest, setLatest] = useState<OnePagerReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState("");
  const [symbolSuggestions, setSymbolSuggestions] = useState<RealtimePortfolioSymbolSuggestion[]>([]);
  const [searchingSymbols, setSearchingSymbols] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const symbolSearchRef = useRef<HTMLDivElement>(null);
  const symbolInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const closeSuggestions = (event: PointerEvent) => {
      if (!symbolSearchRef.current?.contains(event.target as Node)) setSuggestionsOpen(false);
    };
    window.addEventListener("pointerdown", closeSuggestions);
    return () => window.removeEventListener("pointerdown", closeSuggestions);
  }, []);

  useEffect(() => {
    const query = symbol.trim();
    if (!query) {
      setSymbolSuggestions([]);
      setSearchingSymbols(false);
      setSuggestionError("");
      return;
    }
    const controller = new AbortController();
    const debounce = window.setTimeout(async () => {
      setSearchingSymbols(true);
      setSuggestionError("");
      try {
        const params = new URLSearchParams({ q: query, limit: "8" });
        const response = await fetch(`${API_URL}/api/v1/realtime/portfolio/search?${params.toString()}`, {
          cache: "no-store",
          credentials: "include",
          signal: controller.signal
        });
        const payload: RealtimePortfolioSymbolSearchResponse & { detail?: string } = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
        setSymbolSuggestions(payload.items);
        setActiveSuggestionIndex(0);
        if (payload.errors.length && !payload.items.length) setSuggestionError("Não foi possível consultar todos os mercados.");
      } catch (requestError) {
        if (!(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setSymbolSuggestions([]);
          setSuggestionError("Busca de empresas temporariamente indisponível.");
        }
      } finally {
        if (!controller.signal.aborted) setSearchingSymbols(false);
      }
    }, 180);
    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [symbol]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/one-pagers`, { cache: "no-store", credentials: "include" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setReports(payload.items ?? []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar o histórico.");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const generate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canGenerate) return;
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!cleanSymbol) return;
    setLoading(true);
    setError("");
    try {
      const apiBase = API_URL.trim();
      const endpoint = /^https?:\/\//i.test(apiBase)
        ? `${apiBase.replace(/\/$/, "")}/api/v1/one-pagers`
        : `${window.location.origin}/api/v1/one-pagers`;
      const request = () => new Promise<{ ok: boolean; status: number; body: string }>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", endpoint, true);
        xhr.withCredentials = true;
        xhr.timeout = 180_000;
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onload = () => resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, body: xhr.responseText });
        xhr.onerror = () => reject(new Error("Não foi possível conectar ao serviço de análise."));
        xhr.ontimeout = () => reject(new Error("A análise excedeu o tempo esperado. Tente novamente."));
        xhr.send(JSON.stringify({ symbol: cleanSymbol }));
      });
      let response = await request();
      if ([502, 503, 504].includes(response.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 1800));
        response = await request();
      }
      let payload: OnePagerReport & { detail?: string };
      try {
        payload = JSON.parse(response.body) as OnePagerReport & { detail?: string };
      } catch {
        throw new Error(
          response.ok
            ? "A API retornou uma resposta inválida. Tente novamente."
            : "O serviço de análise está reiniciando. Aguarde alguns segundos e tente novamente."
        );
      }
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setLatest(payload);
      setReports((current) => [payload, ...current.filter((item) => item.filename !== payload.filename)].slice(0, 12));
      setSymbol("");
      setSymbolSuggestions([]);
      setSuggestionsOpen(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível gerar o One Pager.");
    } finally {
      setLoading(false);
    }
  };

  const chooseSuggestion = (suggestion: RealtimePortfolioSymbolSuggestion) => {
    setSymbol(suggestion.symbol);
    setSuggestionsOpen(false);
    setActiveSuggestionIndex(0);
    setError("");
    symbolInputRef.current?.focus();
  };

  const handleSymbolKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setSuggestionsOpen(false);
      return;
    }
    if (!suggestionsOpen || !symbolSuggestions.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (index + 1) % symbolSuggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (index - 1 + symbolSuggestions.length) % symbolSuggestions.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseSuggestion(symbolSuggestions[activeSuggestionIndex]);
    }
  };

  const exactSymbolSuggestion = symbolSuggestions.some(
    (suggestion) => suggestion.symbol === symbol.trim().toUpperCase()
  );

  return (
    <div className="content-stack one-pager-view">
      <section className="one-pager-builder">
        <div className="one-pager-builder-copy">
          <span>Equity research engine</span>
          <h2>Qual empresa você quer analisar?</h2>
          <p>Digite um ticker da B3 ou dos Estados Unidos. O C3PO coleta cotação, fundamentos, consenso e histórico antes de construir o documento.</p>
          {canGenerate ? <form className="one-pager-form" onSubmit={generate}>
            <label htmlFor="one-pager-symbol">Ticker</label>
            <div className="one-pager-input-row">
              <div className="one-pager-input" ref={symbolSearchRef}>
                <Search size={19} />
                <input
                  ref={symbolInputRef}
                  id="one-pager-symbol"
                  value={symbol}
                  onChange={(event) => {
                    setSymbol(event.target.value.toUpperCase());
                    setSuggestionsOpen(true);
                    setError("");
                  }}
                  onFocus={() => setSuggestionsOpen(true)}
                  onKeyDown={handleSymbolKeyDown}
                  placeholder="Digite ticker ou empresa"
                  maxLength={80}
                  autoComplete="off"
                  spellCheck={false}
                  role="combobox"
                  aria-autocomplete="list"
                  aria-expanded={suggestionsOpen && !!symbol.trim()}
                  aria-controls="one-pager-symbol-suggestions"
                  aria-activedescendant={symbolSuggestions[activeSuggestionIndex] ? `one-pager-symbol-${symbolSuggestions[activeSuggestionIndex].market}-${symbolSuggestions[activeSuggestionIndex].symbol}` : undefined}
                  required
                />
                {searchingSymbols && <RefreshCw size={14} className="spin one-pager-symbol-spinner" />}
                {suggestionsOpen && !!symbol.trim() && (
                  <div className="one-pager-suggestions" id="one-pager-symbol-suggestions" role="listbox">
                    {symbolSuggestions.map((suggestion, index) => (
                      <button
                        type="button"
                        id={`one-pager-symbol-${suggestion.market}-${suggestion.symbol}`}
                        className={index === activeSuggestionIndex ? "one-pager-suggestion one-pager-suggestion-active" : "one-pager-suggestion"}
                        key={`${suggestion.market}-${suggestion.symbol}`}
                        onClick={() => chooseSuggestion(suggestion)}
                        onMouseEnter={() => setActiveSuggestionIndex(index)}
                        role="option"
                        aria-selected={index === activeSuggestionIndex}
                      >
                        <span>{suggestion.symbol}</span>
                        <div>
                          <strong>{suggestion.name}</strong>
                          <small>{suggestion.market} · {suggestion.security_type}</small>
                        </div>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                    {!symbolSuggestions.length && !searchingSymbols && (
                      <div className="one-pager-suggestion-empty">
                        <Search size={15} />
                        <span>{suggestionError || "Nenhuma empresa encontrada"}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <button type="submit" disabled={loading || !exactSymbolSuggestion} title="Selecione uma empresa válida">
                {loading ? <RefreshCw size={18} className="spin" /> : <LaserPagerIcon size={20} />}
                <span>{loading ? "Gerando análise..." : "Gerar One Pager"}</span>
              </button>
            </div>
          </form> : <div className="one-pager-readonly"><LockKeyhole size={18} /><div><strong>Acesso somente para leitura</strong><span>Você pode consultar e abrir o histórico, mas não gerar novos One Pagers.</span></div></div>}
          {error && <div className="one-pager-error"><AlertTriangle size={16} /><span>{error}</span></div>}
        </div>
        <aside className="one-pager-protocol">
          <span>Research protocol</span>
          <strong>5-method valuation</strong>
          <div><i>01</i><p>Cotação e histórico verificados nas APIs contratadas</p></div>
          <div><i>02</i><p>DCF, earnings, enterprise value, book value e consenso</p></div>
          <div><i>03</i><p>Buy-in, risco, confiança, tese e pontos de validação</p></div>
        </aside>
      </section>

      {latest && (
        <section className="panel one-pager-ready">
          <div className="one-pager-ready-head">
            <div className="one-pager-symbol-mark">{latest.symbol.slice(0, 2)}</div>
            <div><span>One Pager concluído</span><InstrumentPreviewTarget instrument={{ symbol: latest.symbol, name: latest.company_name, market: latest.market }}><strong>{latest.symbol} | {latest.company_name}</strong></InstrumentPreviewTarget><small>{latest.market} · {latest.methodology_name}{latest.methodology_version ? ` v${latest.methodology_version}` : ""} · {formatDate(latest.generated_at)}</small></div>
            <a href={`${API_URL}${latest.download_url}`} target="_blank" rel="noreferrer"><Download size={17} /><span>Abrir PDF</span></a>
          </div>
          <div className="one-pager-metrics">
            <div><span>Price</span><strong>{formatCurrency(latest.price, latest.currency)}</strong></div>
            <div><span>C3PO TP</span><strong>{formatCurrency(latest.c3po_tp, latest.currency)}</strong></div>
            <div><span>Upside</span><strong className={latest.upside_percent >= 0 ? "positive-text" : "negative-text"}>{formatPercent(latest.upside_percent)}</strong></div>
            <div><span>Buy-in</span><strong>{formatCurrency(latest.buy_in, latest.currency)}</strong></div>
            <div><span>Confidence</span><strong>{latest.confidence}/100</strong></div>
          </div>
        </section>
      )}

      <section className="panel">
        <PanelHeader title="Generated One Pagers" icon={LaserPagerIcon} action="Refresh" onAction={loadHistory} />
        {historyLoading ? <div className="one-pager-history-loading">{Array.from({ length: 4 }).map((_, index) => <span key={index} />)}</div> : (
          <div className="one-pager-history">
            {reports.map((report) => (
              <a href={`${API_URL}${report.download_url}`} target="_blank" rel="noreferrer" key={report.filename}>
                <div className="one-pager-history-mark">{report.symbol.slice(0, 2)}</div>
                <div><InstrumentPreviewTarget instrument={{ symbol: report.symbol, name: report.company_name, market: report.market }} nested pinOnClick={false}><strong>{report.symbol} | {report.company_name}</strong></InstrumentPreviewTarget><span>{formatDate(report.generated_at)}{report.methodology_version ? ` · v${report.methodology_version}` : " · legacy"} · {report.method_count} methods · confidence {report.confidence}</span></div>
                <div className="one-pager-history-upside"><span>Upside</span><strong className={report.upside_percent >= 0 ? "positive-text" : "negative-text"}>{formatPercent(report.upside_percent)}</strong></div>
                <Download size={17} />
              </a>
            ))}
            {!reports.length && <EmptyLine label="Nenhum One Pager gerado nesta biblioteca" />}
          </div>
        )}
      </section>
    </div>
  );
}

const valuationMarketMarks: Record<string, string> = {
  B3: "/market-marks/b3.svg",
  NASDAQ: "/market-marks/nasdaq.svg",
  NYSE: "/market-marks/nyse.svg"
};

function MarketMark({ market }: { market: string }) {
  const src = valuationMarketMarks[market];
  return src
    ? <span className="iq-record-market-mark" title={market}><img src={src} alt={market} /></span>
    : <span className="iq-record-market-mark iq-record-market-mark-text">{market}</span>;
}

const valuationTriggerLabels: Record<ValuationTrigger, string> = {
  initial: "Base inicial",
  financial_results: "Resultado",
  material_event: "Material relevante",
  web_research: "Pesquisa web",
  market_data: "Dados & consenso",
  methodology: "Metodologia"
};

const IQ_RECORDS_PAGE_SIZE = 30;

function IQRecordsView() {
  const initialQuery = currentViewQuery();
  const [data, setData] = useState<ValuationChangeResponse | null>(null);
  const [query, setQuery] = useState(initialQuery);
  const [activeQuery, setActiveQuery] = useState(initialQuery);
  const [market, setMarket] = useState<"" | "B3" | "NASDAQ" | "NYSE">("");
  const [triggerType, setTriggerType] = useState<"" | ValuationTrigger>("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRecords = useCallback(async (search = activeQuery, pageNumber = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        limit: String(IQ_RECORDS_PAGE_SIZE),
        offset: String((pageNumber - 1) * IQ_RECORDS_PAGE_SIZE)
      });
      if (search.trim()) params.set("q", search.trim());
      if (market) params.set("market", market);
      if (triggerType) params.set("trigger_type", triggerType);
      const response = await fetch(`${API_URL}/api/v1/valuation-records?${params.toString()}`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setData(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar o histórico de valuation.");
    } finally {
      setLoading(false);
    }
  }, [activeQuery, market, page, triggerType]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = query.trim();
    if (nextQuery === activeQuery && page === 1) {
      loadRecords(nextQuery, 1);
      return;
    }
    setPage(1);
    setActiveQuery(nextQuery);
  };

  const records = data?.items ?? [];
  const totalRecords = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalRecords / IQ_RECORDS_PAGE_SIZE));
  const firstRecord = totalRecords ? ((page - 1) * IQ_RECORDS_PAGE_SIZE) + 1 : 0;
  const lastRecord = totalRecords ? Math.min(page * IQ_RECORDS_PAGE_SIZE, totalRecords) : 0;
  const companyCount = new Set(records.map((item) => `${item.market}:${item.symbol}`)).size;
  const evidenceCount = records.filter((item) => ["financial_results", "material_event", "web_research"].includes(item.trigger_type)).length;
  const latestRecord = records[0];

  return (
    <div className="content-stack iq-records-view">
      <section className="panel iq-records-summary">
        <div className="iq-records-intro">
          <div className="iq-records-mark"><BenKenobiRecordsIcon size={32} /></div>
          <div>
            <span>Permanent valuation ledger</span>
            <strong>Cada mudança preserva o antes, o depois e a evidência.</strong>
          </div>
        </div>
        <div className="iq-records-metrics">
          <div><span>Registros</span><strong>{data?.total ?? 0}</strong></div>
          <div><span>Empresas nesta visão</span><strong>{companyCount}</strong></div>
          <div><span>Novas evidências</span><strong>{evidenceCount}</strong></div>
          <div><span>Última alteração</span><strong>{latestRecord ? formatRecordDate(latestRecord.changed_at) : "N/D"}</strong></div>
        </div>
      </section>

      <section className="panel iq-records-panel">
        <div className="iq-records-toolbar">
          <form onSubmit={submitSearch} className="iq-records-search">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ticker ou empresa"
              aria-label="Buscar registros de valuation"
            />
            <button type="submit">Buscar</button>
          </form>
          <div className="iq-market-filter" aria-label="Filtrar mercado">
            {(["", "B3", "NASDAQ", "NYSE"] as const).map((value) => (
              <button key={value || "all"} className={market === value ? "active" : ""} onClick={() => { setPage(1); setMarket(value); }}>
                {value || "Todos"}
              </button>
            ))}
          </div>
          <label className="iq-trigger-filter">
            <span>Gatilho</span>
            <select value={triggerType} onChange={(event) => { setPage(1); setTriggerType(event.target.value as "" | ValuationTrigger); }}>
              <option value="">Todos</option>
              {(Object.keys(valuationTriggerLabels) as ValuationTrigger[]).map((value) => (
                <option key={value} value={value}>{valuationTriggerLabels[value]}</option>
              ))}
            </select>
          </label>
          <button className="icon-button" onClick={() => loadRecords()} disabled={loading} aria-label="Atualizar histórico" title="Atualizar histórico">
            <RefreshCw size={18} className={loading ? "spin" : ""} />
          </button>
        </div>

        {error && <div className="iq-records-error"><AlertTriangle size={17} /><span>{error}</span></div>}

        <div className="iq-records-table" aria-live="polite">
          <div className="iq-records-head">
            <span>Data & empresa</span>
            <span>Gatilho & fonte</span>
            <span>C3PO TP</span>
            <span>Buy-in</span>
            <span>Consenso</span>
            <span>Metodologia & motivo</span>
          </div>
          {loading && !data ? <IQRecordsLoading /> : records.map((record) => <IQRecordRow key={record.id} record={record} />)}
          {!loading && !records.length && (
            <div className="iq-records-empty">
              <BookOpenCheck size={24} />
              <strong>Nenhuma alteração encontrada</strong>
              <span>Os próximos recálculos de valuation serão registrados automaticamente aqui.</span>
            </div>
          )}
        </div>
        {totalRecords > 0 && (
          <footer className="iq-records-pagination" aria-label="Paginação dos registros">
            <div>
              <strong>{firstRecord}–{lastRecord}</strong>
              <span>de {totalRecords} registros</span>
            </div>
            <div className="iq-pagination-controls">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={loading || page === 1}
                aria-label="Página anterior"
                title="Página anterior"
              >
                <ChevronLeft size={16} />
              </button>
              <span>Página <strong>{page}</strong> de {totalPages}</span>
              <button
                type="button"
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                disabled={loading || page === totalPages}
                aria-label="Próxima página"
                title="Próxima página"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </footer>
        )}
      </section>
    </div>
  );
}

function IQRecordRow({ record }: { record: ValuationChangeRecord }) {
  const changedFields = valuationChangedFieldLabels(record);
  return (
    <article className="iq-record-row">
      <div className="iq-record-company" data-label="Data & empresa">
        <time>{formatRecordDate(record.changed_at)}</time>
        <div className="iq-record-identity">
          <div className="iq-record-logo"><CompanyLogo logoUrl={record.logo_url} symbol={record.symbol} /></div>
          <div>
            <InstrumentPreviewTarget instrument={{ symbol: record.symbol, name: record.company_name, market: record.market }}><strong>{record.symbol}</strong></InstrumentPreviewTarget>
            <span>{record.company_name}</span>
            <MarketMark market={record.market} />
          </div>
        </div>
      </div>
      <div className="iq-record-trigger" data-label="Gatilho & fonte">
        <span className={`iq-trigger-badge iq-trigger-${record.trigger_type}`}>{valuationTriggerLabels[record.trigger_type]}</span>
        <strong>{record.trigger_title}</strong>
        <p>{record.trigger_summary}</p>
        <div className="iq-changed-fields">
          <span>{record.trigger_type === "initial" ? "Registrou" : "Alterou"}</span>
          <strong>{changedFields.join(" · ")}</strong>
        </div>
        {record.source_url ? (
          <a href={record.source_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />{record.source_name || "Abrir fonte"}</a>
        ) : <small>{record.source_name}</small>}
      </div>
      <IQValueChange label="C3PO TP" oldValue={record.old_tp} newValue={record.new_tp} currency={record.currency} change={record.tp_change_percent} />
      <IQValueChange label="Buy-in" oldValue={record.old_buy_in} newValue={record.new_buy_in} currency={record.currency} />
      <IQValueChange label="Consenso" oldValue={record.old_consensus_tp} newValue={record.new_consensus_tp} currency={record.currency} />
      <div className="iq-record-method" data-label="Metodologia & motivo">
        <strong>{record.methodology_name}{record.methodology_version ? ` v${record.methodology_version}` : ""}</strong>
        <p>{valuationChangeReason(record, changedFields)}</p>
        <small>Confiança {record.new_confidence !== null ? `${Math.round(record.new_confidence)}/100` : "N/D"}</small>
      </div>
    </article>
  );
}

function IQValueChange({
  label,
  oldValue,
  newValue,
  currency,
  change
}: {
  label: string;
  oldValue: number | null;
  newValue: number | null;
  currency: string;
  change?: number | null;
}) {
  const calculatedChange = change ?? (
    oldValue !== null && oldValue !== 0 && newValue !== null
      ? ((newValue / oldValue) - 1) * 100
      : null
  );
  const direction = oldValue === null
    ? "neutral"
    : newValue !== null && newValue > oldValue
      ? "positive"
      : newValue !== null && newValue < oldValue
        ? "negative"
        : "neutral";
  return (
    <div className="iq-record-value" data-label={label}>
      <div className="iq-value-price iq-value-old">
        <span>Anterior</span>
        <strong>{oldValue !== null ? formatCurrency(oldValue, currency) : "N/D"}</strong>
      </div>
      <div className={`iq-value-direction iq-value-${direction}`}>
        {direction === "positive" ? <ArrowUp size={13} /> : direction === "negative" ? <ArrowDown size={13} /> : <Minus size={13} />}
        <span>{oldValue === null ? "Base inicial" : direction === "neutral" ? "Sem mudança" : formatPercent(calculatedChange)}</span>
      </div>
      <div className={`iq-value-price iq-value-new iq-value-new-${direction}`}>
        <span>Novo</span>
        <strong>{newValue !== null ? formatCurrency(newValue, currency) : "N/D"}</strong>
      </div>
    </div>
  );
}

function valuationChangedFieldLabels(record: ValuationChangeRecord) {
  const raw = Array.isArray(record.metadata.changed_fields) ? record.metadata.changed_fields : [];
  const labels: Record<string, string> = {
    initial_valuation: "Base de valuation",
    c3po_tp: "C3PO TP",
    buy_in: "Buy-in",
    consensus_tp: "Consenso",
    confidence: "Confiança"
  };
  const fields = raw.map((item) => labels[String(item)]).filter((item): item is string => Boolean(item));
  return fields.length ? fields : [record.trigger_type === "initial" ? "Base de valuation" : "Premissas do valuation"];
}

function valuationChangeReason(record: ValuationChangeRecord, changedFields: string[]) {
  const affected = changedFields.join(", ");
  if (record.trigger_type === "initial") return "Base inicial criada; ainda não existe um valuation anterior para comparação.";
  if (record.trigger_type === "financial_results") return `Novo resultado oficial incorporado aos fundamentos, com impacto em ${affected}.`;
  if (record.trigger_type === "material_event") return `Material oficial alterou premissas do modelo e recalculou ${affected}.`;
  if (record.trigger_type === "web_research") return `Nova evidência validada no RI, SEC ou web recalibrou ${affected}.`;
  if (record.trigger_type === "methodology") return `Novos pesos ou parâmetros da metodologia recalcularam ${affected}.`;
  return `Fundamentos, consenso ou dados de mercado atualizados recalibraram ${affected}.`;
}

function IQRecordsLoading() {
  return <div className="iq-records-loading">{Array.from({ length: 5 }).map((_, index) => <span key={index} />)}</div>;
}

function RebellionNewsView() {
  const [data, setData] = useState<NewsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{
    group: NewsSourceGroup;
    item: NewsItem;
    left: number;
    top: number;
    width: number;
  } | null>(null);
  const previewCloseTimer = useRef<number | null>(null);

  const closePreview = useCallback(() => {
    if (previewCloseTimer.current) window.clearTimeout(previewCloseTimer.current);
    previewCloseTimer.current = window.setTimeout(() => setPreview(null), 90);
  }, []);

  const openPreview = useCallback((group: NewsSourceGroup, item: NewsItem, anchor: HTMLElement) => {
    if (window.matchMedia("(hover: none)").matches) return;
    if (previewCloseTimer.current) window.clearTimeout(previewCloseTimer.current);
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(420, window.innerWidth - 24);
    const estimatedHeight = 248;
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const top = window.innerHeight - rect.bottom >= estimatedHeight + 12
      ? rect.bottom + 8
      : Math.max(10, rect.top - estimatedHeight - 8);
    setPreview({ group, item, left, top, width });
  }, []);

  const loadNews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/news?refresh=true`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setData(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar as notícias.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNews();
  }, [loadNews]);

  useEffect(() => {
    const refreshMs = Math.max(60, data?.refresh_seconds ?? 300) * 1000;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadNews();
    }, refreshMs);
    return () => window.clearInterval(interval);
  }, [data?.refresh_seconds, loadNews]);

  useEffect(() => () => {
    if (previewCloseTimer.current) window.clearTimeout(previewCloseTimer.current);
  }, []);

  return (
    <div className="content-stack rebellion-news-view">
      <section className="panel rebellion-news-briefing">
        <div className="rebellion-news-briefing-copy">
          <div className="rebellion-news-briefing-mark"><RebellionNewsIcon size={27} /></div>
          <div>
            <span>Live editorial desk</span>
            <strong>Quatro fontes, vinte manchetes prioritárias</strong>
            <small>Seleção automática por atualidade e relevância econômica, política e de mercado.</small>
          </div>
        </div>
        <div className="rebellion-news-metrics">
          <div><span>Fontes online</span><strong>{data?.source_count ?? "-"}/4</strong></div>
          <div><span>Notícias</span><strong>{data?.item_count ?? "-"}</strong></div>
          <div><span>Atualizado</span><strong>{data ? formatDate(data.generated_at) : "Coletando"}</strong></div>
        </div>
        <button className="rebellion-news-refresh" type="button" onClick={loadNews} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          <span>Atualizar agora</span>
        </button>
      </section>

      {error && <div className="screen-error"><AlertTriangle size={17} /><span>{error}</span><button onClick={loadNews}>Tentar novamente</button></div>}
      {loading && !data ? <RebellionNewsLoading /> : data && (
        <div className="rebellion-news-grid">
          {data.groups.map((group) => (
            <RebellionSourcePanel
              key={group.code}
              group={group}
              onPreviewOpen={openPreview}
              onPreviewClose={closePreview}
            />
          ))}
        </div>
      )}
      {data && <div className="rebellion-news-footnote"><ShieldCheck size={15} /><span>Feeds editoriais oficiais, deduplicados e ordenados pelo C3PO.</span><small>Atualização automática a cada {Math.round(data.refresh_seconds / 60)} minutos.</small></div>}
      {preview && typeof document !== "undefined" && createPortal(
        <NewsHoverPreview {...preview} />,
        document.body
      )}
    </div>
  );
}

function RebellionSourcePanel({
  group,
  onPreviewOpen,
  onPreviewClose
}: {
  group: NewsSourceGroup;
  onPreviewOpen: (group: NewsSourceGroup, item: NewsItem, anchor: HTMLElement) => void;
  onPreviewClose: () => void;
}) {
  return (
    <section className={`panel rebellion-source-panel rebellion-source-${group.code}`}>
      <header className="rebellion-source-head">
        <a href={group.homepage_url} target="_blank" rel="noreferrer" aria-label={`Abrir ${group.name}`}>
          <NewsSourceBrand code={group.code} />
        </a>
        <div>
          <span className={`rebellion-source-status rebellion-source-status-${group.status}`}><i />{group.status === "fresh" ? "Atualizado" : group.status === "partial" ? "Parcial" : "Indisponível"}</span>
          <small>{group.items.length}/5 notícias</small>
        </div>
      </header>
      <div className="rebellion-source-list">
        {group.items.map((item) => (
          <a
            className="rebellion-news-item"
            href={item.url}
            key={`${group.code}-${item.rank}-${item.url}`}
            target="_blank"
            rel="noopener noreferrer"
            onMouseEnter={(event) => onPreviewOpen(group, item, event.currentTarget)}
            onMouseLeave={onPreviewClose}
            onFocus={(event) => onPreviewOpen(group, item, event.currentTarget)}
            onBlur={onPreviewClose}
            aria-label={`${item.title}. Abrir em nova aba.`}
          >
            <span className="rebellion-news-rank">{String(item.rank).padStart(2, "0")}</span>
            <div>
              <strong>{item.title}</strong>
              {item.summary && <p>{item.summary}</p>}
              <time dateTime={item.published_at ?? undefined} title={item.published_at ? formatRecordDate(item.published_at) : undefined}>{formatNewsAge(item.published_at)}</time>
            </div>
            <ExternalLink size={15} />
          </a>
        ))}
        {!group.items.length && <div className="rebellion-source-empty"><AlertTriangle size={18} /><strong>Fonte temporariamente indisponível</strong><span>{group.errors[0] ?? "Tente atualizar novamente em alguns minutos."}</span></div>}
      </div>
      {group.status === "partial" && group.errors.length > 0 && <div className="rebellion-source-warning">Alguns feeds não responderam; as manchetes disponíveis foram preservadas.</div>}
    </section>
  );
}

function NewsHoverPreview({
  group,
  item,
  left,
  top,
  width
}: {
  group: NewsSourceGroup;
  item: NewsItem;
  left: number;
  top: number;
  width: number;
}) {
  return (
    <aside
      className={`rebellion-news-preview rebellion-news-preview-${group.code}`}
      style={{ left, top, width }}
      role="tooltip"
      aria-label={`Prévia de ${item.title}`}
    >
      <header>
        <NewsSourceBrand code={group.code} />
        <div><span>Prévia editorial</span><small>{formatNewsAge(item.published_at)}</small></div>
      </header>
      <div className="rebellion-news-preview-copy">
        <span>{group.name}</span>
        <strong>{item.title}</strong>
        <p>{item.summary || "Abra a matéria para consultar o conteúdo completo na fonte original."}</p>
      </div>
      <footer>
        <span><Clock3 size={13} />{item.published_at ? formatRecordDate(item.published_at) : "Horário não informado"}</span>
        <strong>Abrir em nova aba <ExternalLink size={13} /></strong>
      </footer>
    </aside>
  );
}

function NewsSourceBrand({ code }: { code: NewsSourceGroup["code"] }) {
  if (code === "globo") return <span className="news-brand news-brand-globo"><img src="/globo-com-logo.png" alt="globo.com" /></span>;
  if (code === "uol") return <span className="news-brand news-brand-uol"><img src="/uol-logo.svg" alt="UOL" /></span>;
  if (code === "bloomberg") return <span className="news-brand news-brand-bloomberg"><b>Bloomberg</b></span>;
  return <span className="news-brand news-brand-cnbc"><i><b /><b /><b /><b /><b /></i><em>CNBC</em></span>;
}

function RebellionNewsLoading() {
  return <div className="rebellion-news-loading">{Array.from({ length: 4 }).map((_, index) => <div key={index}>{Array.from({ length: 6 }).map((__, row) => <span key={row} />)}</div>)}</div>;
}

function WeatherView() {
  const [data, setData] = useState<WeatherResponse | null>(null);
  const [query, setQuery] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadWeather = useCallback(async (search = "") => {
    setLoading(true);
    setError("");
    try {
      const suffix = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
      const response = await fetch(`${API_URL}/api/v1/weather${suffix}`, {
        cache: "no-store",
        credentials: "include"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `API ${response.status}`);
      setData(payload);
      setActiveSearch(search.trim());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível carregar a previsão.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWeather();
  }, [loadWeather]);

  useEffect(() => {
    const refreshMs = Math.max(60, data?.refresh_seconds ?? 300) * 1000;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") loadWeather(activeSearch);
    }, refreshMs);
    return () => window.clearInterval(interval);
  }, [activeSearch, data?.refresh_seconds, loadWeather]);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim()) loadWeather(query.trim());
  };

  const clearSearch = () => {
    setQuery("");
    loadWeather();
  };

  return (
    <div className="content-stack weather-view">
      <section className="panel weather-control">
        <div className="weather-control-copy">
          <div className="weather-control-mark"><DagobahWeatherIcon size={24} /></div>
          <div>
            <span>24-hour forecast desk</span>
            <strong>Leblon e Campo Belo fixos, com pesquisa mundial</strong>
            <small>Atualização automática a cada {Math.round((data?.refresh_seconds ?? 300) / 60)} minutos.</small>
          </div>
        </div>
        <form className="weather-search" onSubmit={submitSearch}>
          <label htmlFor="weather-city-search">Pesquisar no mundo</label>
          <div>
            <Search size={17} />
            <input
              id="weather-city-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Cidade, região ou país"
              maxLength={100}
              autoComplete="off"
            />
            {activeSearch && <button type="button" className="weather-search-clear" onClick={clearSearch} title="Remover cidade pesquisada" aria-label="Remover cidade pesquisada"><X size={15} /></button>}
            <button type="submit" className="weather-search-submit" disabled={loading || !query.trim()} title="Buscar previsão" aria-label="Buscar previsão">
              {loading ? <RefreshCw size={17} className="spin" /> : <Search size={17} />}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="screen-error"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => loadWeather(activeSearch)}>Tentar novamente</button></div>}
      {data?.errors.length ? <div className="weather-warning"><AlertTriangle size={15} /><span>{data.errors.join(" · ")}</span></div> : null}

      {loading && !data ? <WeatherLoading /> : data && (
        <>
          <div className="weather-location-list">
            {data.locations.map((location) => <WeatherLocationCard key={location.key} location={location} />)}
          </div>
          <div className="weather-source-note">
            <ShieldCheck size={16} />
            <span>{data.source} · geocodificação mundial e coordenadas específicas para os bairros fixos</span>
            <small>Coletado em {formatDate(data.generated_at)}</small>
          </div>
        </>
      )}
    </div>
  );
}

function WeatherLocationCard({ location }: { location: WeatherLocation }) {
  return (
    <section className="panel weather-location-card">
      <header className="weather-location-head">
        <div className="weather-location-identity">
          <div><WeatherConditionIcon code={location.current_weather_code} size={26} /></div>
          <div>
            <span>{location.fixed ? "Permanent location" : "Searched location"}</span>
            <strong>{location.label}</strong>
            <small>{location.latitude.toFixed(4)}, {location.longitude.toFixed(4)} · {location.timezone}</small>
          </div>
        </div>
        <div className="weather-location-current">
          <div><span>Agora</span><strong>{formatTemperature(location.current_temperature_c)}</strong></div>
          <div><span>Condição</span><strong>{location.current_condition}</strong></div>
          <div><span>Vento</span><strong>{formatWind(location.current_wind_kts, location.current_wind_direction)}</strong></div>
          <div><span>Chuva</span><strong>{formatRain(location.current_precipitation_mm)}</strong></div>
        </div>
      </header>
      <div className="weather-chart-section">
        <div className="weather-chart-head">
          <div><span>Próximas 24 horas</span><strong>Temperatura e probabilidade de chuva</strong></div>
          <div className="weather-chart-legend"><span><i className="temperature" />Temperatura</span><span><i className="rain" />Chuva</span></div>
        </div>
        <WeatherChart hours={location.hours} label={location.label} />
      </div>
      <div className="weather-hour-grid">
        {location.hours.map((hour) => (
          <article key={hour.time} title={`${hour.condition} · sensação ${formatTemperature(hour.apparent_c)}`}>
            <time>{formatWeatherHour(hour.time)}</time>
            <WeatherConditionIcon code={hour.weather_code} size={15} />
            <strong>{formatTemperature(hour.temperature_c)}</strong>
            <span className="weather-hour-rain"><Droplets size={11} />{formatProbability(hour.rain_probability_percent)}</span>
            <span className="weather-hour-wind">
              <ArrowUp size={12} style={{ transform: `rotate(${hour.wind_direction_deg ?? 0}deg)` }} />
              {hour.wind_direction} {formatKnots(hour.wind_kts)}
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

function WeatherChart({ hours, label }: { hours: WeatherHour[]; label: string }) {
  const width = 1200;
  const height = 300;
  const left = 48;
  const right = 24;
  const top = 28;
  const bottom = 56;
  const baseY = height - bottom;
  const temperatures = hours.map((hour) => hour.temperature_c).filter((value): value is number => value !== null);
  const rawMin = temperatures.length ? Math.min(...temperatures) : 0;
  const rawMax = temperatures.length ? Math.max(...temperatures) : 1;
  const minTemp = Math.floor(rawMin - 1);
  const maxTemp = Math.ceil(Math.max(rawMax + 1, minTemp + 4));
  const plotHeight = baseY - top;
  const plotWidth = width - left - right;
  const x = (index: number) => left + (hours.length <= 1 ? 0 : index * plotWidth / (hours.length - 1));
  const y = (temperature: number) => top + (maxTemp - temperature) / (maxTemp - minTemp) * plotHeight;
  let started = false;
  const path = hours.map((hour, index) => {
    if (hour.temperature_c === null) return "";
    const command = started ? "L" : "M";
    started = true;
    return `${command}${x(index).toFixed(1)},${y(hour.temperature_c).toFixed(1)}`;
  }).filter(Boolean).join(" ");
  const gridValues = [maxTemp, Math.round((maxTemp + minTemp) / 2), minTemp];
  const barWidth = Math.max(8, Math.min(28, plotWidth / Math.max(1, hours.length) * 0.58));

  return (
    <svg className="weather-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Previsão de temperatura e chuva para ${label}`}>
      {gridValues.map((value) => {
        const gridY = y(value);
        return <g key={value}><line className="weather-chart-gridline" x1={left} y1={gridY} x2={width - right} y2={gridY} /><text className="weather-chart-y-label" x={left - 9} y={gridY + 4} textAnchor="end">{value}°</text></g>;
      })}
      <line className="weather-chart-axis" x1={left} y1={baseY} x2={width - right} y2={baseY} />
      {hours.map((hour, index) => {
        const probability = Math.max(0, Math.min(100, hour.rain_probability_percent ?? 0));
        const barHeight = probability / 100 * Math.min(105, plotHeight * 0.56);
        return <rect key={`rain-${hour.time}`} className="weather-chart-rain-bar" x={x(index) - barWidth / 2} y={baseY - barHeight} width={barWidth} height={barHeight}><title>{formatWeatherHour(hour.time)} · chuva {formatProbability(hour.rain_probability_percent)}</title></rect>;
      })}
      {path && <path className="weather-chart-temperature-line" d={path} />}
      {hours.map((hour, index) => hour.temperature_c === null ? null : (
        <g key={`temperature-${hour.time}`}>
          <circle className="weather-chart-temperature-dot" cx={x(index)} cy={y(hour.temperature_c)} r={index % 3 === 0 ? 4.3 : 2.8}><title>{formatWeatherHour(hour.time)} · {formatTemperature(hour.temperature_c)} · chuva {formatProbability(hour.rain_probability_percent)} · vento {formatWind(hour.wind_kts, hour.wind_direction)}</title></circle>
          {(index % 3 === 0 || index === hours.length - 1) && <text className="weather-chart-temperature-label" x={x(index)} y={Math.max(14, y(hour.temperature_c) - 10)} textAnchor="middle">{hour.temperature_c.toFixed(1).replace(".", ",")}°</text>}
        </g>
      ))}
      {hours.map((hour, index) => (index % 3 === 0 || index === hours.length - 1) ? <text key={`time-${hour.time}`} className="weather-chart-x-label" x={x(index)} y={height - 18} textAnchor="middle">{formatWeatherHour(hour.time)}</text> : null)}
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
  return (
    <section className="panel">
      <PanelHeader title="Active Alerts" icon={RadarAlertsIcon} />
      {readError && <div className="screen-error"><AlertTriangle size={16} /><span>{readError}</span></div>}
      <div className="alert-list">
        {stale && <AlertRow item={{ id: "stale-snapshot", severity: "High", subject: "Legacy snapshot is stale", context: "A fonte principal não foi atualizada dentro da janela esperada.", action: `Last source update: ${formatDate(data.generated_at)}`, source: "Legacy Summary Adapter", occurred_at: data.generated_at, metadata: {}, is_read: true }} expanded={expandedId === "stale-snapshot"} onToggle={() => setExpandedId((current) => current === "stale-snapshot" ? null : "stale-snapshot")} />}
        {data.items.map((item) => <AlertRow key={item.id} item={item} expanded={expandedId === item.id} onToggle={() => toggleAlert(item)} />)}
        {!stale && !data.items.length && <EmptyLine label="No active alerts" />}
      </div>
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

  const feedUrl = useMemo(() => {
    const params = new URLSearchParams({ limit: "150" });
    params.set("scope", scope);
    if (market !== "all") params.set("market", market);
    if (source !== "all") params.set("source", source);
    if (eventType !== "all") params.set("event_type", eventType);
    if (search.trim()) params.set("q", search.trim());
    return `${API_URL}/api/v1/investor-relations?${params.toString()}`;
  }, [eventType, market, scope, search, source]);

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
        <PanelHeader title="Official disclosure feed" icon={TatooineNewsIcon} action={feed ? `${feed.items.length} visible` : "Loading"} />
        <div className="ir-feed-head">
          <span>Source</span><span>Company</span><span>Disclosure</span><span>Published</span><span>CVM First</span><span>Document</span>
        </div>
        <div className="ir-feed-body">
          {loading && !feed ? <div className="ir-feed-loading" /> : feed?.items.map((item) => (
            <article className="ir-event-row" key={item.id}>
              <div><span className={`ir-source-badge ir-source-${item.source}`}>{item.source.toUpperCase()}</span><small>{item.market}</small></div>
              <div className="ir-company-cell">{item.symbol ? <InstrumentPreviewTarget instrument={{ symbol: item.symbol, name: item.company_name, market: item.market }}><strong>{item.symbol}</strong></InstrumentPreviewTarget> : <strong>{item.regulator_id ?? "Issuer"}</strong>}<span>{item.company_name}</span></div>
              <div className="ir-disclosure-cell"><strong>{item.title}</strong><span>{item.event_type}{item.form ? ` · ${item.form}` : ""}</span><small className={`ir-materiality ir-materiality-${item.materiality}`}>{item.materiality} materiality</small></div>
              <div className="ir-date-cell"><strong>{formatIrEventDate(item)}</strong><span>{item.reference_date ? `Ref. ${new Date(`${item.reference_date}T12:00:00`).toLocaleDateString("pt-BR")}` : "No reference period"}</span></div>
              <div className="ir-status-cell">
                <span className={`ir-valuation-status ir-valuation-${item.valuation_status}`}>{item.valuation_status.replace("_", " ")}</span>
                {canManage && item.valuation_status === "pending_review" && <button onClick={() => reviewEvent(item.id)} disabled={syncing}>Mark reviewed</button>}
              </div>
              <div className="ir-document-cell">
                <a href={item.document_url ?? item.official_url} target="_blank" rel="noreferrer" title="Open official filing"><ExternalLink size={15} /></a>
              </div>
            </article>
          ))}
          {!loading && feed && !feed.items.length && <EmptyLine label="No official disclosures match these filters" />}
        </div>
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
  return event.published_time_precision === "collected" ? `${formatted} collected` : formatted;
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

function ServerUsageView() {
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
        </div>

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
      apis: 1,
      external_services: 2,
      open_finance: 3,
      quotes: 4,
      official_sources: 5,
      automations: 6
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
    finnhub: "/service-finnhub.png",
    cvm: "/cvm-mark.png",
    sec: "/sec-mark.gif",
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
  if (kind === "intermedia") return <span className="service-logo service-logo-intermedia" aria-hidden="true"><Mail size={21} /><b>IX</b></span>;
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

  const requestCode = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/request-code`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Não foi possível enviar o código.");
      setChallengeId(payload.challenge_id);
      setMessage(`Código enviado. Ele vale por ${Math.round(payload.expires_in_seconds / 60)} minutos.`);
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

  const resetLogin = () => {
    setChallengeId("");
    setCode("");
    setMessage("");
    setError("");
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
          <p>{challengeId ? `Enviamos um código de seis dígitos para ${email}.` : "Use seu e-mail autorizado. Nenhuma senha é necessária."}</p>
        </div>

        {!challengeId ? (
          <form onSubmit={(event) => { event.preventDefault(); requestCode(); }} className="login-form">
            <label htmlFor="login-email">E-mail</label>
            <div className="login-input"><Mail size={18} /><input id="login-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></div>
            <button className="login-primary" type="submit" disabled={loading}>{loading ? "Enviando..." : "Enviar código"}</button>
          </form>
        ) : (
          <form onSubmit={(event) => { event.preventDefault(); verifyCode(); }} className="login-form">
            <label htmlFor="login-code">Código de acesso</label>
            <div className="login-input login-code-input"><LockKeyhole size={18} /><input id="login-code" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="000000" pattern="\d{6}" required autoFocus /></div>
            {message && <p className="login-message">{message}</p>}
            <button className="login-primary" type="submit" disabled={loading || code.length !== 6}>{loading ? "Validando..." : "Entrar no C3PO"}</button>
            <button className="login-secondary" type="button" onClick={resetLogin}>Usar outro e-mail</button>
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
  const [showLoginOpening, setShowLoginOpening] = useState(false);
  const [previewOpening, setPreviewOpening] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV !== "production" && new URLSearchParams(window.location.search).get("preview") === "opening") {
      setPreviewOpening(true);
    }
  }, []);

  const refreshSession = useCallback((playOpening = false) => {
    setAuthState("checking");
    return fetch(`${API_URL}/api/v1/auth/session`, { cache: "no-store", credentials: "include" })
      .then((response) => response.json())
      .then((payload: AuthSession) => {
        setSession(payload.authenticated ? payload : null);
        setAuthState(payload.authenticated ? "authenticated" : "anonymous");
        setShowLoginOpening(Boolean(payload.authenticated && playOpening));
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
    setShowLoginOpening(false);
  };

  const enterCommandCenter = () => {
    const params = new URLSearchParams(window.location.search);
    params.set("view", "command");
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    setShowLoginOpening(false);
  };

  if (previewOpening) return <C3POOpeningView onEnter={() => setPreviewOpening(false)} />;

  if (authState === "checking") {
    return <main className="login-shell"><div className="login-loading"><div className="login-mark" /><span>Estabelecendo canal seguro...</span></div></main>;
  }
  if (authState === "anonymous") return <LoginScreen onAuthenticated={() => { void refreshSession(true); }} />;
  if (!session) return <main className="login-shell"><div className="login-loading"><div className="login-mark" /><span>Validando autorização...</span></div></main>;
  if (showLoginOpening) return <C3POOpeningView onEnter={enterCommandCenter} />;
  return <AppShell session={session} onLogout={logout} onSessionExpired={() => { setSession(null); setAuthState("anonymous"); }} />;
}

export default function Page() {
  return <C3POGate />;
}
