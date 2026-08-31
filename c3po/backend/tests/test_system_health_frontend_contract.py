from pathlib import Path


PAGE = Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_storm_troops_refreshes_read_only_every_minute_while_visible() -> None:
    page = _page()

    assert "const SYSTEM_HEALTH_REFRESH_INTERVAL_MS = 60_000;" in page
    assert "window.setInterval(refreshWhenVisible, SYSTEM_HEALTH_REFRESH_INTERVAL_MS)" in page
    assert 'document.visibilityState === "visible"' in page
    assert 'fetch(`${API_URL}/api/v1/system-health`, {' in page
    assert 'cache: "no-store"' in page
    assert 'credentials: "include"' in page
    assert 'document.addEventListener("visibilitychange", refreshWhenVisible)' in page
    assert 'document.removeEventListener("visibilitychange", refreshWhenVisible)' in page


def test_storm_troops_rejects_out_of_order_snapshots_and_keeps_last_good_state() -> None:
    page = _page()

    assert "function shouldAcceptSystemHealthSnapshot" in page
    candidate_guard = "if (!Number.isFinite(candidateTimestamp)) return false;"
    first_snapshot_acceptance = "if (!current) return true;"
    newer_snapshot_acceptance = "return candidateTimestamp >= currentTimestamp;"
    assert candidate_guard in page
    assert first_snapshot_acceptance in page
    assert newer_snapshot_acceptance in page
    assert page.index(candidate_guard) < page.index(first_snapshot_acceptance)
    assert "candidateTimestamp >= currentTimestamp" in page
    assert "shouldAcceptSystemHealthSnapshot(current, candidate) ? candidate : current" in page
    assert "const accepted = shouldAcceptSystemHealthSnapshot(systemHealthSnapshotRef.current, candidate);" in page
    assert "if (!accepted) return false;" in page
    assert "return true;" in page[page.index("const acceptSystemHealth"):page.index("const refreshSystemHealth")]
    acceptance = page[page.index("const acceptSystemHealth"):page.index("const refreshSystemHealth")]
    assert acceptance.index("if (!accepted) return false;") < acceptance.index("setSystemHealthCheckedAt")
    assert acceptance.index("if (!accepted) return false;") < acceptance.index("setSystemHealthRefreshError")
    assert "Atualização automática temporariamente indisponível" in page
    assert "exibindo a última medição válida" in page


def test_every_system_health_snapshot_setter_uses_the_timestamp_guard() -> None:
    page = _page()
    guarded_system_health_setter = (
        "setSystemHealth((current) => shouldAcceptSystemHealthSnapshot(current, candidate) ? candidate : current)"
    )
    guarded_falcon_setter = (
        "setHealth((current) => shouldAcceptSystemHealthSnapshot(current, candidate) ? candidate : current)"
    )

    assert page.count("setSystemHealth(") == page.count(guarded_system_health_setter) == 1
    assert page.count("setHealth(") == page.count(guarded_falcon_setter) == 2
    falcon = page[page.index("function MillenniumFalconView"):page.index("function FalconMetric")]
    assert falcon.count(guarded_falcon_setter) == 2


def test_attestation_is_not_presented_as_a_regular_panel_refresh() -> None:
    page = _page()

    assert '`${API_URL}/api/v1/admin/governance/attest`' in page
    assert '"Gerar novo atestado"' in page
    assert '"Atualizar agora"' not in page[page.index("function HealthView"):page.index("function MetricCard")]
