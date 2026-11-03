import logging


def test_the_ir_worker_never_logs_request_urls_with_tokens() -> None:
    """httpx logs each request URL at INFO, the provider token in its query string included."""
    import app.ir_worker  # noqa: F401  (configures logging on import)

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
