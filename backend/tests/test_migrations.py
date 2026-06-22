import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def test_initial_migration_creates_core_tables(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "deploydock.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    table_names = list_table_names(database_path)

    assert {
        "users",
        "servers",
        "apps",
        "deployments",
        "deployment_logs",
        "audit_logs",
    }.issubset(table_names)

    get_settings.cache_clear()


def list_table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    return {row[0] for row in rows}
