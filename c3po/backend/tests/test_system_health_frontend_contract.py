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
    assert "candidateTimestamp >= currentTimestamp" in page
    assert "shouldAcceptSystemHealthSnapshot(current, candidate) ? candidate : current" in page
    assert "Atualização automática temporariamente indisponível" in page
    assert "exibindo a última medição válida" in page


def test_attestation_is_not_presented_as_a_regular_panel_refresh() -> None:
    page = _page()

    assert '`${API_URL}/api/v1/admin/governance/attest`' in page
    assert '"Gerar novo atestado"' in page
    assert '"Atualizar agora"' not in page[page.index("function HealthView"):page.index("function MetricCard")]
