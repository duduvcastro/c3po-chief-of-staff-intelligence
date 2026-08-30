from pathlib import Path


PAGE = Path(__file__).parents[2] / "frontend" / "app" / "page.tsx"


def test_hyperspace_popup_headline_uses_the_values_from_its_visible_row() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "linePrice?: number | null;" in source
    assert "lineChangePercent?: number | null;" in source
    assert 'const headlinePrice = hasLinePrice ? item.linePrice : data?.current;' in source
    assert "? item.lineChangePercent" in source
    assert 'formatIntradayPrice(data.current, data.currency, data.market)' not in source

    # All four Hyper Space surfaces carry their displayed quote into the popup.
    assert "linePrice: snapshot.index.value" in source
    assert "lineChangePercent: snapshot.index.change_percent" in source
    assert source.count("linePrice: item.price") >= 2
    assert source.count("lineChangePercent: item.change_percent") >= 2
    assert 'linePrice: item.status === "stale" ? null : item.price' in source
    assert 'item.reference_status === "unvalidated"' in source


def test_otc_origin_reference_is_visible_and_always_formatted_in_usd() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'item.market === "OTC" ? "USD" : item.currency' in source
    assert "item.origin_reference_note" in source
    assert "realtime-portfolio-origin-${item.origin_reference_status}" in source
    assert "sem listagem-mãe mapeada" not in source
