from pathlib import Path


PAGE = Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx"


def _source_between(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end)]


def test_falcon_uses_nullable_nav_session_delta_instead_of_episode_win_rate() -> None:
    source = PAGE.read_text(encoding="utf-8")
    falcon = _source_between(source, "function MillenniumFalconView", "function FalconMetric")

    assert 'label="NAV Δ vs sessão anterior"' in falcon
    assert 'label="Episode Win Rate"' not in falcon
    assert 'navSessionDelta?.status === "available"' in falcon
    assert 'navSessionDelta?.status === "first_session"' in falcon
    assert 'navSessionDelta?.status === "missing_previous_close"' in falcon
    assert 'navSessionDelta?.status === "current_mark_unavailable"' in falcon
    assert 'navDeltaFirstSession ? "primeira sessão"' in falcon
    assert ': "N/D"' in falcon
    assert '"Marca viva indisponível"' in falcon
    assert "`orgânico ${signedPercent(" in falcon
    assert "· juros ${signedPercent(" in falcon
    assert 'navSessionDelta.interest_status === "pending"' in falcon


def test_episode_win_rate_remains_visible_in_the_daily_log() -> None:
    source = PAGE.read_text(encoding="utf-8")
    rising = _source_between(source, "function R2D2RisingView", "function R2D2Ticker")

    assert "const todayEpisodes = data.today_episode_stats;" in rising
    assert "todayEpisodes.decided_episodes > 0" in rising
    assert 'todayEpisodeWinRate === null ? "N/D"' in rising
    assert 'aria-label="Resumo dos episódios e das transações"' in rising
    assert "todayEpisodes.positive_episodes" in rising
    assert "todayEpisodes.decided_episodes" in rising
    assert "todayEpisodeWinRate.toFixed(1)" in rising


def test_learning_curve_window_and_every_label_derive_from_one_constant() -> None:
    """NO-GO do Codex na #350: a linha calculava MM10 com tres textos dizendo 5.
    Janela, legenda, aria-label, tooltip e selo MM nascem da MESMA constante."""
    import re

    falcon = PAGE.read_text(encoding="utf-8")

    assert "const LEARNING_MOVING_AVERAGE_WINDOW = 10;" in falcon
    assert "index - (LEARNING_MOVING_AVERAGE_WINDOW - 1)" in falcon
    assert "`Média móvel (${LEARNING_MOVING_AVERAGE_WINDOW}d)`" in falcon
    assert "média móvel de ${LEARNING_MOVING_AVERAGE_WINDOW} dias" in falcon
    assert "`Média móvel ${LEARNING_MOVING_AVERAGE_WINDOW} dias em ${" in falcon
    assert "`MM${LEARNING_MOVING_AVERAGE_WINDOW} ${" in falcon

    start = falcon.index("LEARNING_MOVING_AVERAGE_WINDOW = 10")
    learning_section = falcon[start : falcon.index("r2d2-learning-ma-dot") + 2000]
    assert re.findall(r"MM5|m[óo]vel de 5|m[óo]vel \(5d\)|m[óo]vel 5 dias", learning_section) == []


def test_panel_polling_is_adaptive_and_suspends_when_hidden() -> None:
    source = PAGE.read_text(encoding="utf-8")
    hook = _source_between(source, "function usePanelPolling", "function useR2D2LivePositions")

    assert "const MARKET_CLOSED_POLL_MS = 60_000;" in source
    assert 'marketOpen === false ? Math.max(closedMs, MARKET_CLOSED_POLL_MS)' in hook
    assert 'if (!active || document.visibilityState !== "visible") return;' in hook
    assert "document.addEventListener(\"visibilitychange\", handleVisibility);" in hook
    assert "} else {\n        stop();" in hook
    assert "void loadRef.current();\n        schedule();" in hook
    assert "stop();\n      timer = window.setTimeout(" in hook
    # Lifecycle guard (audited on #373): nothing schedules after cleanup, and a tab that
    # is born hidden neither loads nor schedules until it becomes visible.
    assert "let active = true;" in hook
    assert "const schedule = () => {\n      if (!active) return;" in hook
    assert "const handleVisibility = () => {\n      if (!active) return;" in hook
    assert 'if (document.visibilityState === "visible") {\n      if (!hasLoadedRef.current) {' in hook
    assert "return () => {\n      active = false;\n      stop();" in hook


def test_r2d2_pollers_use_the_shared_polling_policy() -> None:
    source = PAGE.read_text(encoding="utf-8")
    live = _source_between(source, "function useR2D2LivePositions", "function MillenniumFalconIcon")
    falcon = _source_between(source, "function MillenniumFalconView", "function FalconMetric")
    rising = _source_between(source, "function R2D2RisingView", "function R2D2Ticker")

    assert "window.setInterval(" not in live
    assert "usePanelPolling(load, {" in live
    assert "marketOpen: telemetry?.market_session_open ?? null" in live
    assert "window.setInterval(" not in falcon
    assert "usePanelPolling(loadR2D2, { openMs: 2_000, marketOpen: falconMarketOpen });" in falcon
    assert "usePanelPolling(loadIndices, { openMs: 10_000, marketOpen: falconMarketOpen });" in falcon
    assert "usePanelPolling(loadHealth, { openMs: 60_000, marketOpen: falconMarketOpen });" in falcon
    assert "usePanelPolling(load, { openMs: 2_000, marketOpen: data?.market_session_open ?? null });" in rising
    assert "market_session_open?: boolean;" in source
