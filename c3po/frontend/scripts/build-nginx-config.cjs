const fs = require("node:fs");

function renderNginxConfig(template, dsn) {
  let origin = "";
  if (dsn?.trim()) {
    const url = new URL(dsn.trim());
    if (url.protocol !== "https:" || !url.hostname.endsWith(".sentry.io") ||
        !/^[a-f0-9]+$/i.test(url.username) || url.password || !/^\/\d+$/.test(url.pathname) ||
        url.search || url.hash || (url.port && url.port !== "443")) {
      throw new Error("Invalid public Sentry DSN for browser CSP");
    }
    origin = ` ${url.origin}`;
  }
  const needle = "connect-src 'self';";
  if (template.split(needle).length !== 2) throw new Error("Expected one CSP connect-src directive");
  return template.replace(needle, `connect-src 'self'${origin};`);
}

module.exports = { renderNginxConfig };

if (require.main === module) {
  fs.writeFileSync("nginx.production.conf", renderNginxConfig(
    fs.readFileSync("nginx.conf", "utf8"), process.env.NEXT_PUBLIC_SENTRY_DSN
  ));
}
