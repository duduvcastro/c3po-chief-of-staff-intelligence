# Server Capacity Telemetry V1

## Purpose

Measure before changing the Lightsail plan. The collector records host CPU, CPU
steal, load averages and disk usage every 60 seconds. Samples are retained in
PostgreSQL for 90 days.

## Windows

- `us_regular_session`: weekdays, 09:30-16:00 America/New_York.
- `valuation_off_hours`: every day, 01:00-08:00 America/Sao_Paulo.

The performance history endpoint publishes, for each window, sample count,
observed dates, CPU average/p95/max, steal average/p95/max, and one-minute load
average/p95/max. It also publishes the p95 one-minute load divided by the
configured vCPU count.

## Decision Rule

Capacity remains `collecting` until at least five distinct US regular sessions
have been observed. No infrastructure purchase is authorized by telemetry
alone.

After five sessions:

1. Use the persisted API and page-load ranking to locate the expensive route or
   view.
2. Compare CPU, load per vCPU and steal between regular-session and off-hours
   windows.
3. Prefer cache, query reduction, parallelism or timeout fixes when CPU and load
   remain moderate.
4. Consider a larger instance only when sustained CPU/load saturation is
   measured and the ranked workload identifies CPU as the limiting resource.

Existing rows remain valid after migration; the new load and steal fields are
`null` before this collector version is deployed.
