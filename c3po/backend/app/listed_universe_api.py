from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .listed_universe import read_universe


def listed_universe_router(database: Any) -> APIRouter:
    router = APIRouter()

    # Prefixes deliberately reuse the existing module permissions. Both views
    # consume one inventory and the same immutable canonical TP records.
    @router.get("/api/v1/candidates/{market}/universe")
    @router.get("/api/v1/matrix-power/{market}/universe")
    def listed_universe(market: str) -> dict[str, Any]:
        try:
            return read_universe(database, market)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
