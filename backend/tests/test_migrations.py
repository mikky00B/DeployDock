import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command
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


def test_migrations_add_host_key_and_active_deployment_index(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "deploydock.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    assert {
        "known_host_key",
        "known_host_key_fingerprint",
        "known_host_key_pinned_at",
    }.issubset(list_column_names(database_path, "servers"))
    assert "uq_deployments_active_per_app" in list_index_names(database_path, "deployments")

    get_settings.cache_clear()


def test_migrations_downgrade_all_the_way_and_back(tmp_path, monkeypatch) -> None:
    """CI runs upgrade/downgrade/upgrade, so every downgrade path must work."""
    database_path = tmp_path / "deploydock.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert "servers" not in list_table_names(database_path)

    command.upgrade(config, "head")

    assert "servers" in list_table_names(database_path)
    assert "uq_deployments_active_per_app" in list_index_names(database_path, "deployments")

    get_settings.cache_clear()


def list_column_names(database_path: Path, table: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def list_index_names(database_path: Path, table: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA index_list({table})").fetchall()
    return {row[1] for row in rows}
