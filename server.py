from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "quality_sheets.db"))).resolve()
DB_BACKEND = "postgres" if DATABASE_URL else "sqlite"
DEFAULT_PREFIX = "QT230201-GSS-QA-ITN-01417"
SESSION_DURATION_SECONDS = 8 * 60 * 60
PBKDF2_ITERATIONS = 200_000
ROLE_LEVELS = {"viewer": 1, "editor": 2, "admin": 3}
DBConnection = Any
MODULE_DEFAULT_PREFIXES = {
    "itn": DEFAULT_PREFIX,
    "rir": "QT230201-GSS-QA-RIR-01417",
    "mrr": "QT230201-GSS-QA-MRR-01417",
    "ncr": "QT230201-GSS-QA-NCR-01417",
    "qor": "QT230201-GSS-QA-QOR-01417",
}
MODULE_TABLES = {
    "itn": "records",
    "rir": "rir_records",
    "mrr": "mrr_records",
    "ncr": "ncr_records",
    "qor": "qor_records",
}
MODULE_ROUTE_PATHS = {module: f"/{module}" for module in MODULE_TABLES if module != "itn"}

if psycopg is not None:
    DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def sanitize_prefix(value: str | None) -> str:
    raw = (value or DEFAULT_PREFIX).upper()
    cleaned = "".join(char for char in raw if char.isalnum() or char == "-")[:32]
    return cleaned or DEFAULT_PREFIX


def build_number(prefix: str, serial: int) -> str:
    head = prefix.rstrip("0123456789")
    tail = prefix[len(head):]
    if not tail:
        return f"{prefix}{serial}"

    width = len(tail) + 1
    value = int(tail) * 10 + serial
    return f"{head}{value:0{width}d}"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def now_timestamp() -> int:
    return int(time.time())


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt_hex = salt_hex or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    ).hex()
    return salt_hex, digest


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    _, computed_hash = hash_password(password, salt_hex)
    return secrets.compare_digest(computed_hash, expected_hash)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def using_postgres() -> bool:
    return DB_BACKEND == "postgres"


def get_connection() -> DBConnection:
    if using_postgres():
        if psycopg is None:
            raise RuntimeError("Le package psycopg est requis pour utiliser PostgreSQL.")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def adapt_sql(sql: str) -> str:
    if using_postgres():
        return sql.replace("?", "%s")
    return sql


def db_execute(connection: DBConnection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return connection.execute(adapt_sql(sql), params)


def db_fetchone(connection: DBConnection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return db_execute(connection, sql, params).fetchone()


def db_fetchall(connection: DBConnection, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return db_execute(connection, sql, params).fetchall()


def begin_write(connection: DBConnection) -> None:
    if using_postgres():
        return
    db_execute(connection, "BEGIN IMMEDIATE")


def get_table_columns(connection: DBConnection, table_name: str) -> set[str]:
    if using_postgres():
        rows = db_fetchall(
            connection,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        )
        return {row["column_name"] for row in rows}

    rows = db_fetchall(connection, f"PRAGMA table_info({table_name})")
    return {row["name"] for row in rows}


def normalize_module(module: str | None) -> str:
    normalized = (module or "itn").strip().lower()
    if normalized not in MODULE_TABLES:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le module demande est invalide.")
    return normalized


def get_module_table(module: str) -> str:
    return MODULE_TABLES[normalize_module(module)]


def get_module_prefix_key(module: str) -> str:
    normalized = normalize_module(module)
    return "prefix" if normalized == "itn" else f"prefix_{normalized}"


def ensure_record_columns(connection: DBConnection, table_name: str) -> None:
    columns = get_table_columns(connection, table_name)

    if "created_by" not in columns:
        db_execute(connection, f"ALTER TABLE {table_name} ADD COLUMN created_by TEXT NOT NULL DEFAULT ''")

    if "updated_by" not in columns:
        db_execute(connection, f"ALTER TABLE {table_name} ADD COLUMN updated_by TEXT NOT NULL DEFAULT ''")


def ensure_user_columns(connection: DBConnection) -> None:
    columns = get_table_columns(connection, "users")

    if "must_change_password" not in columns:
        default_value = "FALSE" if using_postgres() else "0"
        db_execute(
            connection,
            f"ALTER TABLE users ADD COLUMN must_change_password {'BOOLEAN' if using_postgres() else 'INTEGER'} NOT NULL DEFAULT {default_value}",
        )


def init_db() -> None:
    with get_connection() as connection:
        if not using_postgres():
            db_execute(connection, "PRAGMA journal_mode=WAL")

        db_execute(
            connection,
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """,
        )

        if using_postgres():
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS records (
                  id BIGSERIAL PRIMARY KEY,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  created_by TEXT NOT NULL DEFAULT '',
                  updated_by TEXT NOT NULL DEFAULT '',
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS rir_records (
                  id BIGSERIAL PRIMARY KEY,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS mrr_records (
                  id BIGSERIAL PRIMARY KEY,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS ncr_records (
                  id BIGSERIAL PRIMARY KEY,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS qor_records (
                  id BIGSERIAL PRIMARY KEY,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS users (
                  id BIGSERIAL PRIMARY KEY,
                  username TEXT NOT NULL UNIQUE,
                  display_name TEXT NOT NULL,
                  password_salt TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL,
                  is_active BOOLEAN NOT NULL DEFAULT TRUE,
                  must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  token_hash TEXT NOT NULL UNIQUE,
                  expires_at BIGINT NOT NULL,
                  created_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL
                )
                """,
            )
        else:
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS rir_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS mrr_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS ncr_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS qor_records (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prefix TEXT NOT NULL,
                  year INTEGER NOT NULL,
                  serial INTEGER NOT NULL,
                  number TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  department TEXT NOT NULL,
                  owner TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(prefix, serial)
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL UNIQUE,
                  display_name TEXT NOT NULL,
                  password_salt TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  must_change_password INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """,
            )
            db_execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  token_hash TEXT NOT NULL UNIQUE,
                  expires_at INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """,
            )
        for table_name in MODULE_TABLES.values():
            ensure_record_columns(connection, table_name)
        ensure_user_columns(connection)
        for module_name, default_prefix in MODULE_DEFAULT_PREFIXES.items():
            db_execute(
                connection,
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (get_module_prefix_key(module_name), default_prefix),
            )
        cleanup_expired_sessions(connection)
        seed_default_admin(connection)
        connection.commit()


def cleanup_expired_sessions(connection: DBConnection) -> None:
    db_execute(connection, "DELETE FROM sessions WHERE expires_at <= ?", (now_timestamp(),))


def seed_default_admin(connection: DBConnection) -> None:
    user_count = db_fetchone(connection, "SELECT COUNT(*) AS count FROM users")["count"]
    if user_count:
        return

    username = os.environ.get("ADMIN_USERNAME", "admin").strip().lower() or "admin"
    password = os.environ.get("ADMIN_PASSWORD", "admin1234")
    display_name = os.environ.get("ADMIN_NAME", "Administrateur Qualite").strip() or "Administrateur Qualite"
    create_user(connection, username, display_name, password, "admin")


def get_prefix(connection: DBConnection, module: str) -> str:
    normalized_module = normalize_module(module)
    row = db_fetchone(connection, "SELECT value FROM settings WHERE key = ?", (get_module_prefix_key(normalized_module),))
    return sanitize_prefix(row["value"] if row else MODULE_DEFAULT_PREFIXES[normalized_module])


def set_prefix(connection: DBConnection, module: str, prefix: str) -> None:
    db_execute(
        connection,
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (get_module_prefix_key(module), sanitize_prefix(prefix)),
    )


def get_current_serial(connection: DBConnection, prefix: str) -> int:
    row = db_fetchone(connection, "SELECT value FROM settings WHERE key = ?", (f"serial_{prefix}",))
    return int(row["value"]) if row else 0


def set_current_serial(connection: DBConnection, prefix: str, serial: int) -> None:
    db_execute(
        connection,
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (f"serial_{prefix}", str(serial)),
    )


def next_serial(
    connection: DBConnection,
    module: str,
    prefix: str,
    excluded_id: int | None = None,
) -> int:
    table_name = get_module_table(module)
    if excluded_id is None:
        row = db_fetchone(
            connection,
            f"""
            SELECT COALESCE(MAX(serial), 0) + 1 AS next_serial
            FROM {table_name}
            WHERE prefix = ?
            """,
            (prefix,),
        )
    else:
        row = db_fetchone(
            connection,
            f"""
            SELECT COALESCE(MAX(serial), 0) + 1 AS next_serial
            FROM {table_name}
            WHERE prefix = ? AND id <> ?
            """,
            (prefix, excluded_id),
        )

    return int(row["next_serial"])


def find_reusable_reserved_record(connection: DBConnection, module: str, prefix: str) -> Any:
    table_name = get_module_table(module)
    return db_fetchone(
        connection,
        f"""
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
        WHERE prefix = ?
          AND status = 'unused'
        ORDER BY serial ASC, id ASC
        LIMIT 1
        """,
        (prefix,),
    )


def fetch_reusable_record_by_id(connection: DBConnection, module: str, prefix: str, record_id: int) -> Any:
    table_name = get_module_table(module)
    return db_fetchone(
        connection,
        f"""
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
        WHERE id = ? AND prefix = ? AND status = 'unused'
        """,
        (record_id, prefix),
    )


def fetch_reusable_records_by_ids(
    connection: DBConnection,
    module: str,
    prefix: str,
    record_ids: list[int],
) -> list[Any]:
    if not record_ids:
        return []

    table_name = get_module_table(module)
    placeholders = ", ".join("?" for _ in record_ids)
    rows = db_fetchall(
        connection,
        f"""
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
        WHERE prefix = ? AND status = 'unused' AND id IN ({placeholders})
        ORDER BY serial ASC, id ASC
        """,
        (prefix, *record_ids),
    )
    return list(rows)


def get_next_record_number(connection: DBConnection, module: str, prefix: str) -> tuple[str, bool]:
    reusable = find_reusable_reserved_record(connection, module, prefix)
    if reusable is not None:
        return str(reusable["number"]), True

    return build_number(prefix, next_serial(connection, module, prefix)), False


def serialize_record(row: Any) -> dict[str, object]:
    return {
        "id": row["id"],
        "prefix": row["prefix"],
        "year": row["year"],
        "serial": row["serial"],
        "number": row["number"],
        "title": row["title"],
        "department": row["department"],
        "owner": row["owner"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "notes": row["notes"],
        "updatedAt": row["updated_at"],
        "createdBy": row["created_by"],
        "updatedBy": row["updated_by"],
    }


def serialize_user(row: Any) -> dict[str, object]:
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "role": row["role"],
        "isActive": bool(row["is_active"]),
        "mustChangePassword": bool(row["must_change_password"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def fetch_record(connection: DBConnection, module: str, record_id: int) -> Any:
    table_name = get_module_table(module)
    return db_fetchone(
        connection,
        f"""
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
        WHERE id = ?
        """,
        (record_id,),
    )


def list_records(connection: DBConnection, module: str, params: dict[str, list[str]]) -> list[dict[str, object]]:
    table_name = get_module_table(module)
    clauses: list[str] = []
    values: list[object] = []
    search = params.get("search", [""])[0].strip().lower()
    status = params.get("status", ["all"])[0]
    year = params.get("year", ["all"])[0]
    owner = params.get("owner", ["all"])[0].strip()

    if status != "all":
        clauses.append("status = ?")
        values.append(status)

    if year != "all":
        clauses.append("year = ?")
        values.append(int(year))

    if owner != "all":
        clauses.append("owner = ?")
        values.append(owner)

    if search:
        clauses.append(
            """
            LOWER(number || ' ' || title || ' ' || department || ' ' || owner || ' ' || notes || ' ' || created_by || ' ' || updated_by) LIKE ?
            """
        )
        values.append(f"%{search}%")

    sql = """
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
    """
    sql = sql.format(table_name=table_name)

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += " ORDER BY id DESC"
    rows = db_fetchall(connection, sql, tuple(values))
    return [serialize_record(row) for row in rows]


def list_record_owners(connection: DBConnection, module: str) -> list[str]:
    table_name = get_module_table(module)
    if using_postgres():
        rows = db_fetchall(
            connection,
            f"""
            SELECT DISTINCT owner
            FROM {table_name}
            WHERE owner <> ''
            ORDER BY LOWER(owner)
            """,
        )
    else:
        rows = db_fetchall(
            connection,
            f"""
            SELECT DISTINCT owner
            FROM {table_name}
            WHERE owner <> ''
            ORDER BY owner COLLATE NOCASE
            """,
        )

    return [str(row["owner"]) for row in rows]


def list_unused_records(connection: DBConnection, module: str, prefix: str) -> list[dict[str, object]]:
    table_name = get_module_table(module)
    rows = db_fetchall(
        connection,
        f"""
        SELECT id, prefix, year, serial, number, title, department, owner, status, created_at, notes,
               updated_at, created_by, updated_by
        FROM {table_name}
        WHERE prefix = ? AND status = 'unused'
        ORDER BY serial ASC, id ASC
        """,
        (prefix,),
    )
    return [serialize_record(row) for row in rows]


def list_users(connection: DBConnection) -> list[dict[str, object]]:
    if using_postgres():
        sql = """
            SELECT id, username, display_name, role, is_active, must_change_password, created_at, updated_at
            FROM users
            ORDER BY LOWER(display_name), LOWER(username)
        """
    else:
        sql = """
            SELECT id, username, display_name, role, is_active, must_change_password, created_at, updated_at
            FROM users
            ORDER BY display_name COLLATE NOCASE, username COLLATE NOCASE
        """
    rows = db_fetchall(connection, sql)
    return [serialize_user(row) for row in rows]


def create_user(
    connection: DBConnection,
    username: str,
    display_name: str,
    password: str,
    role: str,
) -> dict[str, object]:
    username = username.strip().lower()
    display_name = display_name.strip()
    role = role.strip().lower()

    normalized_username = (
        username.replace(".", "")
        .replace("_", "")
        .replace("-", "")
        .replace("@", "")
    )

    if len(username) < 3 or not normalized_username.isalnum():
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le nom d'utilisateur est invalide.")

    if len(display_name) < 2:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le nom complet est invalide.")

    if len(password) < 8:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le mot de passe doit contenir au moins 8 caracteres.")

    if role not in ROLE_LEVELS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le role est invalide.")

    salt_hex, password_hash = hash_password(password)
    now = utc_now()
    db_execute(
        connection,
        """
        INSERT INTO users (username, display_name, password_salt, password_hash, role, must_change_password, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, display_name, salt_hex, password_hash, role, False, now, now),
    )
    row = db_fetchone(
        connection,
        """
        SELECT id, username, display_name, role, is_active, must_change_password, created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (username,),
    )
    return serialize_user(row)


def authenticate_user(connection: DBConnection, username: str, password: str) -> Any:
    row = db_fetchone(
        connection,
        """
        SELECT id, username, display_name, password_salt, password_hash, role, is_active, must_change_password, created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (username.strip().lower(),),
    )

    if row is None or not row["is_active"]:
        return None

    if not verify_password(password, row["password_salt"], row["password_hash"]):
        return None

    return row


def create_session(connection: DBConnection, user_id: int) -> str:
    cleanup_expired_sessions(connection)
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    now = utc_now()
    db_execute(
        connection,
        """
        INSERT INTO sessions (user_id, token_hash, expires_at, created_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, token_hash, now_timestamp() + SESSION_DURATION_SECONDS, now, now),
    )
    return token


def fetch_user_by_id(connection: DBConnection, user_id: int) -> Any:
    return db_fetchone(
        connection,
        """
        SELECT id, username, display_name, role, is_active, must_change_password, created_at, updated_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )


def fetch_user_with_secret_by_username(connection: DBConnection, username: str) -> Any:
    return db_fetchone(
        connection,
        """
        SELECT id, username, display_name, password_salt, password_hash, role, is_active, must_change_password, created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (username.strip().lower(),),
    )


def update_user_password(
    connection: DBConnection,
    user_id: int,
    new_password: str,
    must_change_password: bool,
) -> dict[str, object]:
    if len(new_password) < 8:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le mot de passe doit contenir au moins 8 caracteres.")

    salt_hex, password_hash = hash_password(new_password)
    db_execute(
        connection,
        """
        UPDATE users
        SET password_salt = ?, password_hash = ?, must_change_password = ?, updated_at = ?
        WHERE id = ?
        """,
        (salt_hex, password_hash, bool(must_change_password), utc_now(), user_id),
    )
    row = fetch_user_by_id(connection, user_id)
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "Utilisateur introuvable.")
    return serialize_user(row)


def generate_temporary_password() -> str:
    return f"TMP-{secrets.token_urlsafe(8)}"


def delete_session(connection: DBConnection, token: str | None) -> None:
    if not token:
        return

    db_execute(connection, "DELETE FROM sessions WHERE token_hash = ?", (hash_session_token(token),))


def delete_sessions_for_user(connection: DBConnection, user_id: int) -> None:
    db_execute(connection, "DELETE FROM sessions WHERE user_id = ?", (user_id,))


def get_user_by_session(connection: DBConnection, token: str | None) -> Any:
    if not token:
        return None

    cleanup_expired_sessions(connection)
    active_condition = "users.is_active = TRUE" if using_postgres() else "users.is_active = 1"
    row = db_fetchone(
        connection,
        f"""
        SELECT users.id, users.username, users.display_name, users.role, users.is_active, users.must_change_password,
               users.created_at, users.updated_at,
               sessions.id AS session_id
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ? AND sessions.expires_at > ? AND {active_condition}
        """,
        (hash_session_token(token), now_timestamp()),
    )

    if row is None:
        return None

    db_execute(
        connection,
        "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
        (utc_now(), row["session_id"]),
    )
    return row


def validate_record_payload(payload: dict[str, object]) -> dict[str, object]:
    title = str(payload.get("title", "")).strip()
    department = str(payload.get("department", "")).strip()
    owner = str(payload.get("owner", "")).strip()
    status = str(payload.get("status", "")).strip()
    created_at = str(payload.get("createdAt", "")).strip()
    notes = str(payload.get("notes", "")).strip()

    try:
        year = int(payload.get("year", 0))
    except (TypeError, ValueError) as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "L'annee est invalide.") from error

    if not title or not department or not owner or not created_at:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Les champs obligatoires sont manquants.")

    if status not in {"draft", "in_review", "approved", "archived", "reserved", "unused"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le statut est invalide.")

    try:
        datetime.strptime(created_at, "%Y-%m-%d")
    except ValueError as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "La date de creation est invalide.") from error

    return {
        "title": title,
        "department": department,
        "owner": owner,
        "status": status,
        "created_at": created_at,
        "notes": notes,
        "year": year,
    }


def validate_bulk_reservation_payload(payload: dict[str, object]) -> dict[str, object]:
    try:
        quantity = int(payload.get("quantity", 0))
    except (TypeError, ValueError) as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le nombre de codes est invalide.") from error

    if quantity < 1:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le nombre de codes doit etre superieur a zero.")

    if quantity > 200:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Vous pouvez reserver jusqu'a 200 codes par operation.")

    raw_ids = payload.get("preferredReusableRecordIds", [])
    if raw_ids == "" or raw_ids is None:
        raw_ids = []

    if not isinstance(raw_ids, list):
        raise ApiError(HTTPStatus.BAD_REQUEST, "La selection des numeros non utilises est invalide.")

    try:
        preferred_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError) as error:
        raise ApiError(HTTPStatus.BAD_REQUEST, "La selection des numeros non utilises est invalide.") from error

    preferred_ids = list(dict.fromkeys(preferred_ids))

    if len(preferred_ids) > quantity:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Le nombre de numeros non utilises coches depasse la quantite demandee.")

    return {"quantity": quantity, "preferred_reusable_record_ids": preferred_ids}


class QualityRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.route_request()

    def do_POST(self) -> None:
        self.route_request()

    def do_PUT(self) -> None:
        self.route_request()

    def do_DELETE(self) -> None:
        self.route_request()

    def route_request(self) -> None:
        parsed = urlparse(self.path)
        self.current_user = self.resolve_current_user()

        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return

        self.serve_static(parsed.path)

    def handle_api(self, parsed) -> None:
        try:
            if parsed.path == "/api/health" and self.command == "GET":
                self.send_json({"status": "ok"})
                return

            if parsed.path == "/api/auth/me" and self.command == "GET":
                self.api_auth_me()
                return

            if parsed.path == "/api/auth/login" and self.command == "POST":
                self.api_auth_login()
                return

            if parsed.path == "/api/auth/change-password" and self.command == "POST":
                self.api_auth_change_password()
                return

            if parsed.path == "/api/auth/logout" and self.command == "POST":
                self.api_auth_logout()
                return

            if parsed.path == "/api/settings":
                if self.command == "GET":
                    self.api_get_settings(parsed)
                    return
                if self.command == "PUT":
                    self.require_role("admin")
                    self.api_update_settings(parsed)
                    return

            if parsed.path == "/api/records":
                if self.command == "GET":
                    self.require_auth()
                    self.api_list_records(parsed)
                    return
                if self.command == "POST":
                    self.require_role("editor")
                    self.api_create_record(parsed)
                    return

            if parsed.path == "/api/records/reserve" and self.command == "POST":
                self.require_role("editor")
                self.api_bulk_reserve_records(parsed)
                return

            if parsed.path.startswith("/api/records/"):
                record_id = self.parse_record_id(parsed.path)
                if record_id is None:
                    raise ApiError(HTTPStatus.NOT_FOUND, "Fiche introuvable.")

                if self.command == "PUT":
                    self.require_role("editor")
                    self.api_update_record(parsed, record_id)
                    return
                if self.command == "DELETE":
                    self.require_role("admin")
                    self.api_delete_record(parsed, record_id)
                    return

            if parsed.path == "/api/users":
                if self.command == "GET":
                    self.require_role("admin")
                    self.api_list_users()
                    return
                if self.command == "POST":
                    self.require_role("admin")
                    self.api_create_user()
                    return

            user_route = self.parse_user_action_path(parsed.path)
            if user_route is not None:
                if self.command == "POST" and user_route["action"] == "reset-password":
                    self.require_role("admin")
                    self.api_reset_user_password(user_route["user_id"])
                    return

            raise ApiError(HTTPStatus.NOT_FOUND, "Route API introuvable.")
        except ApiError as error:
            self.send_error_json(error.status, error.message)
        except DB_INTEGRITY_ERRORS as error:
            message = "Cette operation entre en conflit avec une donnee existante."
            if "users.username" in str(error):
                message = "Ce nom d'utilisateur existe deja."
            if ".number" in str(error) or ".prefix, " in str(error):
                message = "Ce numero existe deja."
            self.send_error_json(HTTPStatus.CONFLICT, message)
        except Exception as error:
            self.log_error("API error: %s", error)
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Une erreur interne est survenue.")

    def api_auth_me(self) -> None:
        self.require_auth()
        self.send_json({"user": self.serialize_current_user()})

    def api_auth_login(self) -> None:
        payload = self.read_json_body()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))

        if not username or not password:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Identifiant ou mot de passe manquant.")

        with get_connection() as connection:
            user = authenticate_user(connection, username, password)
            if user is None:
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Identifiants invalides.")

            token = create_session(connection, int(user["id"]))
            connection.commit()

        headers = [("Set-Cookie", self.build_session_cookie(token))]
        self.send_json({"user": serialize_user(user)}, headers=headers)

    def api_auth_change_password(self) -> None:
        self.require_auth()
        payload = self.read_json_body()
        current_password = str(payload.get("currentPassword", ""))
        new_password = str(payload.get("newPassword", ""))

        if not current_password or not new_password:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Le mot de passe actuel et le nouveau mot de passe sont obligatoires.")

        username = str(self.current_user["username"])
        with get_connection() as connection:
            user = fetch_user_with_secret_by_username(connection, username)
            if user is None or not verify_password(current_password, user["password_salt"], user["password_hash"]):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Le mot de passe actuel est incorrect.")

            updated_user = update_user_password(connection, int(user["id"]), new_password, False)
            connection.commit()

        self.send_json({"user": updated_user})

    def api_auth_logout(self) -> None:
        token = self.get_session_token()
        with get_connection() as connection:
            delete_session(connection, token)
            connection.commit()

        headers = [("Set-Cookie", self.build_expired_cookie())]
        self.send_json({"loggedOut": True}, headers=headers)

    def api_get_settings(self, parsed) -> None:
        self.require_auth()
        module = self.get_requested_module(parsed)
        current_year = datetime.now().year
        with get_connection() as connection:
            prefix = get_prefix(connection, module)
            next_number, using_reserved_number = get_next_record_number(connection, module, prefix)

        self.send_json(
            {
                "module": module,
                "prefix": prefix,
                "currentYear": current_year,
                "nextNumber": next_number,
                "usingReservedNumber": using_reserved_number,
            }
        )

    def api_update_settings(self, parsed) -> None:
        module = self.get_requested_module(parsed)
        payload = self.read_json_body()
        prefix = sanitize_prefix(str(payload.get("prefix", "")))
        with get_connection() as connection:
            set_prefix(connection, module, prefix)
            connection.commit()

        self.send_json({"module": module, "prefix": prefix})

    def api_list_records(self, parsed) -> None:
        params = parse_qs(parsed.query)
        module = self.get_requested_module(parsed)
        with get_connection() as connection:
            records = list_records(connection, module, params)
            prefix = get_prefix(connection, module)
            reusable_records = list_unused_records(connection, module, prefix)
            owners = list_record_owners(connection, module)

        self.send_json(
            {
                "module": module,
                "records": records,
                "reusableRecords": reusable_records,
                "owners": owners,
                "prefix": prefix,
            }
        )

    def api_create_record(self, parsed) -> None:
        module = self.get_requested_module(parsed)
        table_name = get_module_table(module)
        raw_payload = self.read_json_body()
        payload = validate_record_payload(raw_payload)
        actor = self.serialize_current_user()["displayName"]
        reusable_record_id = raw_payload.get("reusableRecordId")

        if reusable_record_id in {"", None}:
            requested_reusable_record_id = None
        else:
            try:
                requested_reusable_record_id = int(reusable_record_id)
            except (TypeError, ValueError) as error:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Le numero non utilise selectionne est invalide.") from error

        with get_connection() as connection:
            prefix = get_prefix(connection, module)
            begin_write(connection)
            now = utc_now()
            if requested_reusable_record_id is not None:
                reusable = fetch_reusable_record_by_id(connection, module, prefix, requested_reusable_record_id)
                if reusable is None:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Le numero non utilise selectionne n'est plus disponible.")
            else:
                reusable = find_reusable_reserved_record(connection, module, prefix)

            if reusable is not None:
                record_id = int(reusable["id"])
                number = str(reusable["number"])
                db_execute(
                    connection,
                    f"""
                    UPDATE {table_name}
                    SET year = ?, title = ?, department = ?, owner = ?, status = ?, created_at = ?, notes = ?,
                        updated_at = ?, created_by = ?, updated_by = ?
                    WHERE id = ?
                    """,
                    (
                        payload["year"],
                        payload["title"],
                        payload["department"],
                        payload["owner"],
                        payload["status"],
                        payload["created_at"],
                        payload["notes"],
                        now,
                        actor,
                        actor,
                        record_id,
                    ),
                )
            else:
                serial = next_serial(connection, module, prefix)
                number = build_number(prefix, serial)
                db_execute(
                    connection,
                    f"""
                    INSERT INTO {table_name} (
                      prefix, year, serial, number, title, department, owner, status, created_at, notes,
                      updated_at, created_by, updated_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prefix,
                        payload["year"],
                        serial,
                        number,
                        payload["title"],
                        payload["department"],
                        payload["owner"],
                        payload["status"],
                        payload["created_at"],
                        payload["notes"],
                        now,
                        actor,
                        actor,
                    ),
                )
                row = db_fetchone(connection, f"SELECT id FROM {table_name} WHERE number = ?", (number,))
                record_id = int(row["id"])

            connection.commit()
            row = fetch_record(connection, module, record_id)

        self.send_json(
            {
                "record": serialize_record(row),
                "usedReservedNumber": reusable is not None,
            },
            status=HTTPStatus.CREATED,
        )

    def api_bulk_reserve_records(self, parsed) -> None:
        module = self.get_requested_module(parsed)
        table_name = get_module_table(module)
        payload = validate_bulk_reservation_payload(self.read_json_body())
        actor = self.serialize_current_user()["displayName"]
        quantity = int(payload["quantity"])
        preferred_reusable_record_ids = list(payload["preferred_reusable_record_ids"])
        created_at = datetime.now().date().isoformat()
        year = datetime.now().year

        with get_connection() as connection:
            prefix = get_prefix(connection, module)
            begin_write(connection)
            selected_reusable_rows = fetch_reusable_records_by_ids(
                connection,
                module,
                prefix,
                preferred_reusable_record_ids,
            )
            if len(selected_reusable_rows) != len(preferred_reusable_record_ids):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Un ou plusieurs numeros non utilises selectionnes ne sont plus disponibles.")

            selected_by_id = {int(row["id"]): row for row in selected_reusable_rows}
            selected_reusable_rows = [selected_by_id[record_id] for record_id in preferred_reusable_record_ids]

            numbers: list[str] = []
            reserved_items: list[tuple[int, str]] = []

            for row in selected_reusable_rows:
                number = str(row["number"])
                numbers.append(number)
                reserved_items.append((int(row["serial"]), number))
                now = utc_now()
                db_execute(
                    connection,
                    f"""
                    UPDATE {table_name}
                    SET year = ?, title = ?, department = ?, owner = ?, status = ?, created_at = ?, notes = ?,
                        updated_at = ?, created_by = ?, updated_by = ?
                    WHERE id = ?
                    """,
                    (
                        year,
                        "Numero reserve",
                        "Suivi numerotation",
                        actor,
                        "reserved",
                        created_at,
                        f"Reservation rapide de {quantity} code(s).",
                        now,
                        actor,
                        actor,
                        int(row["id"]),
                    ),
                )

            start_serial = next_serial(connection, module, prefix)
            generated_count = quantity - len(selected_reusable_rows)

            for index in range(generated_count):
                serial = start_serial + index
                number = build_number(prefix, serial)
                numbers.append(number)
                reserved_items.append((serial, number))
                now = utc_now()
                db_execute(
                    connection,
                    f"""
                    INSERT INTO {table_name} (
                      prefix, year, serial, number, title, department, owner, status, created_at, notes,
                      updated_at, created_by, updated_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prefix,
                        year,
                        serial,
                        number,
                        "Numero reserve",
                        "Suivi numerotation",
                        actor,
                        "reserved",
                        created_at,
                        f"Reservation rapide de {quantity} code(s).",
                        now,
                        actor,
                        actor,
                    ),
                )

            connection.commit()

        reserved_items.sort(key=lambda item: item[0])

        self.send_json(
            {
                "count": quantity,
                "firstNumber": reserved_items[0][1],
                "lastNumber": reserved_items[-1][1],
                "numbers": numbers if quantity <= 20 else [],
                "selectedCount": len(selected_reusable_rows),
                "generatedCount": generated_count,
            },
            status=HTTPStatus.CREATED,
        )

    def api_update_record(self, parsed, record_id: int) -> None:
        module = self.get_requested_module(parsed)
        table_name = get_module_table(module)
        payload = validate_record_payload(self.read_json_body())
        actor = self.serialize_current_user()["displayName"]

        with get_connection() as connection:
            existing = fetch_record(connection, module, record_id)
            if existing is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Fiche introuvable.")

            prefix = existing["prefix"]
            begin_write(connection)
            serial = int(existing["serial"])

            db_execute(
                connection,
                f"""
                UPDATE {table_name}
                SET year = ?, serial = ?, number = ?, title = ?, department = ?, owner = ?, status = ?,
                    created_at = ?, notes = ?, updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (
                    payload["year"],
                    serial,
                    build_number(prefix, serial),
                    payload["title"],
                    payload["department"],
                    payload["owner"],
                    payload["status"],
                    payload["created_at"],
                    payload["notes"],
                    utc_now(),
                    actor,
                    record_id,
                ),
            )
            connection.commit()
            updated = fetch_record(connection, module, record_id)

        self.send_json({"record": serialize_record(updated)})

    def api_delete_record(self, parsed, record_id: int) -> None:
        module = self.get_requested_module(parsed)
        table_name = get_module_table(module)
        with get_connection() as connection:
            cursor = db_execute(connection, f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
            connection.commit()

        if cursor.rowcount == 0:
            raise ApiError(HTTPStatus.NOT_FOUND, "Fiche introuvable.")

        self.send_json({"deleted": True})

    def api_list_users(self) -> None:
        with get_connection() as connection:
            users = list_users(connection)

        self.send_json({"users": users})

    def api_create_user(self) -> None:
        payload = self.read_json_body()
        username = str(payload.get("username", ""))
        display_name = str(payload.get("displayName", ""))
        password = str(payload.get("password", ""))
        role = str(payload.get("role", "viewer"))

        with get_connection() as connection:
            user = create_user(connection, username, display_name, password, role)
            connection.commit()

        self.send_json({"user": user}, status=HTTPStatus.CREATED)

    def api_reset_user_password(self, user_id: int) -> None:
        payload = self.read_json_body()
        requested_password = str(payload.get("newPassword", "")).strip()
        temporary_password = requested_password or generate_temporary_password()

        with get_connection() as connection:
            user = fetch_user_by_id(connection, user_id)
            if user is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Utilisateur introuvable.")

            updated_user = update_user_password(connection, user_id, temporary_password, True)
            delete_sessions_for_user(connection, user_id)
            connection.commit()

        self.send_json(
            {
                "user": updated_user,
                "temporaryPassword": temporary_password,
            }
        )

    def require_auth(self) -> None:
        if self.current_user is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Authentification requise.")

    def require_role(self, minimum_role: str) -> None:
        self.require_auth()
        user_role = str(self.current_user["role"])
        if ROLE_LEVELS[user_role] < ROLE_LEVELS[minimum_role]:
            raise ApiError(HTTPStatus.FORBIDDEN, "Vous n'avez pas les droits necessaires.")

    def resolve_current_user(self) -> Any:
        token = self.get_session_token()
        if not token:
            return None

        with get_connection() as connection:
            user = get_user_by_session(connection, token)
            connection.commit()
            return user

    def serialize_current_user(self) -> dict[str, object]:
        if self.current_user is None:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Authentification requise.")

        return {
            "id": self.current_user["id"],
            "username": self.current_user["username"],
            "displayName": self.current_user["display_name"],
            "role": self.current_user["role"],
            "mustChangePassword": bool(self.current_user["must_change_password"]),
        }

    def get_session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None

        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        if "session" not in cookie:
            return None

        return cookie["session"].value

    def build_session_cookie(self, token: str) -> str:
        secure_flag = "; Secure" if os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes"} else ""
        return f"session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DURATION_SECONDS}{secure_flag}"

    def build_expired_cookie(self) -> str:
        secure_flag = "; Secure" if os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes"} else ""
        return f"session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_flag}"

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            return json.loads(raw_body or "{}")
        except json.JSONDecodeError as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Le corps JSON est invalide.") from error

    def get_requested_module(self, parsed) -> str:
        params = parse_qs(parsed.query)
        return normalize_module(params.get("module", ["itn"])[0])

    def parse_record_id(self, path: str) -> int | None:
        try:
            return int(path.rstrip("/").split("/")[-1])
        except ValueError:
            return None

    def parse_user_action_path(self, path: str) -> dict[str, object] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "users":
            return None

        try:
            user_id = int(parts[2])
        except ValueError:
            return None

        return {"user_id": user_id, "action": parts[3]}

    def serve_static(self, path: str) -> None:
        normalized_path = path.rstrip("/") or "/"
        target = "index.html" if normalized_path in {"/", *MODULE_ROUTE_PATHS.values()} else path.lstrip("/")
        requested = (STATIC_DIR / target).resolve()

        if STATIC_DIR not in requested.parents and requested != STATIC_DIR:
            self.send_error_json(HTTPStatus.FORBIDDEN, "Acces refuse.")
            return

        if not requested.exists() or not requested.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Fichier introuvable.")
            return

        content_type, _ = mimetypes.guess_type(str(requested))
        data = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for header_name, header_value in headers or []:
            self.send_header(header_name, header_value)
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    init_db()
    server = ThreadingHTTPServer((host, port), QualityRequestHandler)
    print(f"Serveur disponible sur http://{host}:{port}")
    server.serve_forever()


def reset_password_by_username(username: str, new_password: str) -> None:
    init_db()
    with get_connection() as connection:
        user = fetch_user_with_secret_by_username(connection, username)
        if user is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Utilisateur introuvable.")

        update_user_password(connection, int(user["id"]), new_password, False)
        delete_sessions_for_user(connection, int(user["id"]))
        connection.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Registre numerique des fiches qualite")
    parser.add_argument("--reset-user-password", dest="reset_user_password", help="Nom d'utilisateur a reinitialiser")
    parser.add_argument("--new-password", dest="new_password", help="Nouveau mot de passe")
    args = parser.parse_args()

    if args.reset_user_password:
        if not args.new_password:
            raise SystemExit("Utilisez --new-password pour definir le nouveau mot de passe.")
        reset_password_by_username(args.reset_user_password, args.new_password)
        print(f"Mot de passe reinitialise pour {args.reset_user_password}.")
    else:
        host = os.environ.get("HOST", "127.0.0.1")
        port = int(os.environ.get("PORT", "8765"))
        run_server(host=host, port=port)
