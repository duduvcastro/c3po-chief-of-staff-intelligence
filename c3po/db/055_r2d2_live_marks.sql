-- The R2D2 live engine's own marks of its held names, in one row (owner 30/10/2026, after ASST and FTI showed +0.10% on
-- the screen without arming the lock: "temos q acertar isso"). The screen re-marked on the EODHD feed's last trade, the
-- engine decides on the bid of Massive's NBBO net of the sale's fee: the engine overwrites this row every second of the
-- session with what it decides on — the bid, the net at that bid, the lock armed or not and the level it sells at — and
-- the api shows it. Display only: the engine never reads it back. Additive and idempotent (every migration runs at
-- every start).
CREATE TABLE IF NOT EXISTS r2d2_live_marks (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    session DATE NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    marks JSONB NOT NULL
);
