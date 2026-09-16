// Explicit issuer marks; never infer identity from ticker prefixes or another exchange.
const B3_MARKS: Record<string, string> = {
  ITSA3: "/company-marks/itausa.png",
  ITSA4: "/company-marks/itausa.png",
  AXIA3: "/company-marks/axia.svg",
  AXIA7: "/company-marks/axia.svg",
  EMBJ3: "/company-marks/embraer.svg"
};

export function chewieLogoSources(market: string, symbol: string, logoUrl?: string | null): string[] {
  const exchange = market.trim().toUpperCase();
  const ticker = symbol.trim().toUpperCase().replace(exchange === "B3" ? /\.SA$/ : /\.US$/, "");
  const verified = exchange === "B3" ? B3_MARKS[ticker] : undefined;
  // Once an issuer has a verified mark, a broken asset must fall back to its ticker,
  // not to a potentially stale provider logo (including pre-rename brands).
  if (verified) return [verified];
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
