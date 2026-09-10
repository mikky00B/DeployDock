import sqlite3
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.models.deployment import DeploymentStatus


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


def test_migration_0007_matches_the_deployment_status_enum(tmp_path, monkeypatch) -> None:
    """Migration 0007 and the SQLAlchemy enum must agree on every status value."""
    database_path = tmp_path / "deploydock.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    columns = {row[1]: row[2] for row in table_info(database_path, "deployments")}
    declared_values = {member.value for member in DeploymentStatus}

    # SQLite stores the enum as VARCHAR, so the strong guarantee is: every enum
    # value survives a write round-trip through the migrated schema.
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        owner_id = str(uuid.uuid4())
        server_id = str(uuid.uuid4())
        connection.execute(
            sa.text("INSERT INTO users (id, email, hashed_password) VALUES (:id, :email, :password)"),
            {"id": owner_id, "email": "round-trip@example.com", "password": "x"},
        )
        connection.execute(
            sa.text(
                "INSERT INTO servers (id, owner_id, name, host, username, encrypted_private_key) "
                "VALUES (:id, :owner_id, :name, :host, :username, :key)"
            ),
            {
                "id": server_id,
                "owner_id": owner_id,
                "name": "VPS",
                "host": "203.0.113.10",
                "username": "deploy",
                "key": "encrypted",
            },
        )
        # uq_deployments_active_per_app allows at most one pending/running row
        # per app, so the two active statuses each get their own app.
        pending_app_id = str(uuid.uuid4())
        running_app_id = str(uuid.uuid4())
        inactive_app_id = str(uuid.uuid4())
        for app_id in (pending_app_id, running_app_id, inactive_app_id):
            connection.execute(
                sa.text(
                    "INSERT INTO apps (id, owner_id, server_id, name, repository_url, app_path, deploy_command) "
                    "VALUES (:id, :owner_id, :server_id, :name, :url, :path, :command)"
                ),
                {
                    "id": app_id,
                    "owner_id": owner_id,
                    "server_id": server_id,
                    "name": "App",
                    "url": "https://example.com/repo.git",
                    "path": "/opt/app",
                    "command": "make deploy",
                },
            )
        active_app_ids = {"pending": pending_app_id, "running": running_app_id}
        for status_value in declared_values:
            connection.execute(
                sa.text(
                    "INSERT INTO deployments (id, owner_id, app_id, server_id, status) "
                    "VALUES (:id, :owner_id, :app_id, :server_id, :status)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "owner_id": owner_id,
                    "app_id": active_app_ids.get(status_value, inactive_app_id),
                    "server_id": server_id,
                    "status": status_value,
                },
            )
        stored = {
            row[0]
            for row in connection.execute(sa.text("SELECT status FROM deployments")).fetchall()
        }
    engine.dispose()

    assert columns["status"].upper().startswith("VARCHAR")
    assert stored == declared_values

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


def test_migrations_create_pipeline_status_values(tmp_path, monkeypatch) -> None:
    """0007 extends the deployment status enum with the §13 pipeline values."""
    database_path = tmp_path / "deploydock.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'deployments'"
        ).fetchone()[0]

    for value in (
        "queued",
        "cloning",
        "building",
        "testing",
        "deploying",
        "health_check",
        "rolled_back",
    ):
        assert f"'{value}'" in table_sql

    get_settings.cache_clear()


def list_column_names(database_path: Path, table: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def table_info(database_path: Path, table: str) -> list[tuple]:
    with sqlite3.connect(database_path) as connection:
        return connection.execute(f"PRAGMA table_info({table})").fetchall()


def list_index_names(database_path: Path, table: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA index_list({table})").fetchall()
    return {row[1] for row in rows}
