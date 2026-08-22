# C3PO edge security

The application and origin now redirect Cloudflare requests whose original scheme was HTTP,
and both proxy layers emit HSTS and the baseline Content Security Policy.

Production rollout also requires Cloudflare **SSL/TLS -> Edge Certificates -> Always Use HTTPS**
to be enabled. This makes the redirect happen at the edge before the request reaches Caddy;
the repository rules remain as defense in depth. After enabling it, verify:

```sh
curl -I http://c3po.eduardocastro.com.br/
curl -I https://c3po.eduardocastro.com.br/
```

The first response must be `301` or `308`. The HTTPS response must include
`Strict-Transport-Security` and `Content-Security-Policy`.
