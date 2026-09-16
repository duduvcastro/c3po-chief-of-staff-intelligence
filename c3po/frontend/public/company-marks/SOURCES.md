# Company marks

Copies verified for Chewie Fundamentals on 2026-09-16. Marks remain the property of their respective issuers.

- `itausa.png`: https://financialmodelingprep.com/image-stock/ITSA4.SA.png
  SHA256: `57390fd1aa672ebf3a21ee0b5ec613416ab96b580b0226e6e3cf42ad3396e400`
- `axia.svg`: https://axia.com.br/documents/32426/93838/AxiaEnergia_marca-PP.svg/dd56b9f3-eed1-7290-eeaa-ce855a526f71
  SHA256: `2d1b35dac687c85cbaf2ce5081e4568cebd2aafc055c659caf5efced73b0efb6`
- `embraer.svg`: https://www.embraer.com/assets/images/Embraer-logo-blue.svg
  SHA256: `026cd6e7b822c7084b3fd1c5a66a046633b2ee7ec7d91daff14d1d978f1fcc64`

AXIA and Embraer assets are linked by their official homepages (https://axia.com.br/ and https://www.embraer.com/pt). Itaúsa PNG was visually verified. Unverified FMP AXIA7 and unavailable AXIA3/EMBJ3 images were not used.

## Full current B3 catalog and new issuers

`b3-catalog.json` covers all 103 symbols from the Chewie B3 snapshot inspected on 2026-09-16 UTC. `b3-catalog-sources.json` records the public download URL and SHA256 for every asset. Most assets come from Brapi's exact-symbol icon catalog. Official issuer websites supplied the current AXIA, Embraer, SAUD, Motiva, MBRF, Riachuelo, Compass and Grupo Petz Cobasi marks. CYRE4 uses CYRE3's issuer mark: Cyrela's official ownership page identifies both share classes (https://ri.cyrela.com.br/governanca-corporativa/composicao-acionaria/). This is an explicit mapping, not prefix guessing.

New B3 symbols automatically use the authenticated logo endpoint, trying the exact Brapi symbol then FMP's `.SA` image. The service rejects known generic Brapi/FMP images, unsafe SVG, oversized payloads and redirects. It uses at most four concurrent downloads, a bounded 128-entry memory cache (24-hour successes, five-minute misses), and no provider credentials. Current local assets remain available without a provider request. New dynamically resolved assets are cached in memory and the browser, not persisted across server restarts.

If both providers fail, the UI leaves the logo slot empty with an accessible explanation and retries after five minutes; it does not substitute a ticker or pretend that a generic provider icon is a company logo. A structured warning identifies unresolved symbols. Future issuer coverage depends on providers publishing a correct mark; this mechanism cannot invent missing company artwork or guarantee provider identity accuracy. Explicit local mappings take precedence and require updating when an issuer changes its brand.
