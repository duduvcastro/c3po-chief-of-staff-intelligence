import assert from "node:assert/strict";
import test from "node:test";
import { chewieLogoSources } from "../lib/chewie-company-logo.ts";

test("reported B3 issuers use verified, distinct marks even with old cached BRAPI placeholders", () => {
  const generic = "https://icons.brapi.dev/icons/BRAPI.svg";
  assert.deepEqual(chewieLogoSources("B3", "ITSA4", generic), ["/company-marks/itausa.png"]);
  assert.deepEqual(chewieLogoSources("B3", "AXIA3", generic), ["/company-marks/axia.svg"]);
  assert.deepEqual(chewieLogoSources("B3", "AXIA7", generic), ["/company-marks/axia.svg"]);
  assert.deepEqual(chewieLogoSources("B3", "EMBJ3", generic), ["/company-marks/embraer.svg"]);
  assert.deepEqual(chewieLogoSources(" b3 ", " itsa4.sa "), ["/company-marks/itausa.png"]);
});
test("unmapped placeholders and unavailable logos fall back to ticker", () => {
  for (const value of [null, "", "https://icons.brapi.dev/icons/BRAPI.svg", "//icons.brapi.dev/icons/brapi.svg?v=1", "https://icons.brapi.dev/icons/%42RAPI.svg"])
    assert.deepEqual(chewieLogoSources("B3", "OTHER3", value), []);
});
test("valid provider logos are preserved and relative EODHD paths normalized", () => {
  const url = "https://icons.brapi.dev/icons/ABEV3.svg";
  assert.deepEqual(chewieLogoSources("B3", "ABEV3", url), [url]);
  assert.deepEqual(chewieLogoSources("NASDAQ", "ABC", "/img/logos/US/abc.png"), ["https://eodhd.com/img/logos/US/abc.png"]);
});
test("B3 mappings never leak into US symbols and unsafe URLs are not images", () => {
  assert.deepEqual(chewieLogoSources("NASDAQ", "ITSA4"), []);
  for (const value of ["javascript:alert(1)", "data:image/svg+xml,x", "http://example.com/logo.png", "https://user:pass@example.com/logo.png"])
    assert.deepEqual(chewieLogoSources("NYSE", "ABC", value), []);
});
