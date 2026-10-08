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


def test_quote_source_and_delay_are_a_single_small_footer_note() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = (PAGE.parent / "globals.css").read_text(encoding="utf-8")

    note = (
        '{snapshot && activeMarket !== "PORTFOLIO" && <p className="realtime-source-note">'
        "Ações: {snapshot.source} · atraso informado: {snapshot.delay_minutes} min</p>}"
    )
    assert source.count("atraso informado") == 1
    assert source.count(note) == 1

    # Rendered once, after the screen footnote, never inside the tab header panel.
    header = source[source.index('<section className="panel realtime-control">'):]
    header = header[:header.index("</section>")]
    assert "atraso informado" not in header
    assert source.index('<div className="realtime-footnote">') < source.index(note)

    rule = next(line for line in styles.splitlines() if line.startswith(".realtime-source-note {"))
    assert "font-size: 10px" in rule
    assert "font-weight: 400" in rule
    assert "color: var(--muted)" in rule
    assert "white-space" not in rule
