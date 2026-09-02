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
