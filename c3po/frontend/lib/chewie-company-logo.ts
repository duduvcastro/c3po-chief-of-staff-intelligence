// Explicit issuer marks; never infer identity from ticker prefixes or another exchange.
import catalog from "../public/company-marks/b3-catalog.json" with { type: "json" };
const B3_MARKS: Record<string, string> = catalog;

export function chewieLogoSources(market: string, symbol: string, logoUrl?: string | null): string[] {
  const exchange = market.trim().toUpperCase();
  const ticker = symbol.trim().toUpperCase().replace(exchange === "B3" ? /\.SA$/ : /\.US$/, "");
  const verified = exchange === "B3" ? B3_MARKS[ticker] : undefined;
  // Current constituents use local marks; new constituents resolve on demand.
  if (exchange === "B3" && /^[A-Z][A-Z0-9]{3}[0-9]{1,2}$/.test(ticker)) {
    const fallback = `/api/v1/chewie-fundamentals/B3/${encodeURIComponent(ticker)}/logo`;
    return verified ? [verified, fallback] : [fallback];
  }
  const raw = logoUrl?.trim();
  if (!raw) return [];
  try {
    const url = new URL(raw.startsWith("//") ? `https:${raw}` : raw, "https://eodhd.com");
    if (url.protocol !== "https:" || url.username || url.password) return [];
    if (url.hostname.toLowerCase() === "icons.brapi.dev" &&
        decodeURIComponent(url.pathname).toLowerCase().replace(/\/+$/, "") === "/icons/brapi.svg") return [];
    return [url.href];
  } catch {
    return [];
  }
}
