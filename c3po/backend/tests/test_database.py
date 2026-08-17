from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import Settings
from app.database import Database


class RecordingCursor:
    def __init__(self) -> None:
        self.query = ""
        self.rows: list[tuple[str, str, datetime]] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def executemany(self, query: str, rows: list[tuple[str, str, datetime]]) -> None:
        self.query = query
        self.rows = rows


class PostgresStyleConnection:
    def __init__(self) -> None:
        self.recording_cursor = RecordingCursor()
        self.committed = False

    def cursor(self) -> RecordingCursor:
        return self.recording_cursor

    def commit(self) -> None:
        self.committed = True


def test_mark_alerts_read_uses_postgres_cursor_executemany(monkeypatch, tmp_path) -> None:
    database = Database(Settings(database_url="postgresql://configured", migrations_dir=tmp_path))
    connection = PostgresStyleConnection()

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(database, "connection", fake_connection)
    read_at = datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc)

    marked = database.mark_alerts_read(
        " EU@EduardoCastro.com.br ",
        ["alert-1", "alert-2", "alert-1", ""],
        read_at,
    )

    assert marked == 2
    assert connection.committed is True
    assert "INSERT INTO alert_reads" in connection.recording_cursor.query
    assert connection.recording_cursor.rows == [
        ("eu@eduardocastro.com.br", "alert-1", read_at),
        ("eu@eduardocastro.com.br", "alert-2", read_at),
    ]
