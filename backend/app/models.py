from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class User:
    id: int
    username: str


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    username: str
    password_hash: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthDB:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
            except sqlite3.OperationalError:
                pass
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);")

            now = _utc_now().isoformat()
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?;", (now,))

    def purge_expired_sessions(self, now: datetime) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?;", (now.isoformat(),))
            return int(cur.rowcount)

    def get_user_record_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?;",
                (username,),
            ).fetchone()
            if row is None:
                return None
            return UserRecord(id=int(row["id"]), username=str(row["username"]), password_hash=str(row["password_hash"]))

    def get_user_by_id(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id, username FROM users WHERE id = ?;", (user_id,)).fetchone()
            if row is None:
                return None
            return User(id=int(row["id"]), username=str(row["username"]))

    def create_user(self, username: str, password_hash: str) -> User:
        now = _utc_now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?);",
                (username, password_hash, now),
            )
            user_id = int(cur.lastrowid)
        return User(id=user_id, username=username)

    def create_session(self, token_hash: str, user_id: int, expires_at: datetime) -> None:
        now = _utc_now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (token_hash, user_id, now, expires_at.isoformat(), now),
            )

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?;", (token_hash,))

    def get_user_by_session_token_hash(self, token_hash: str, now: datetime) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id AS user_id, u.username AS username, s.expires_at AS expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?;
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None

            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at <= now:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?;", (token_hash,))
                return None

            conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?;", (now.isoformat(), token_hash))
            return User(id=int(row["user_id"]), username=str(row["username"]))


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    username: str


ProjectType = Literal["python", "node", "other"]


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    path: str
    is_git: bool
    git_branch: str | None
    git_dirty: bool
    detected_type: ProjectType
    last_modified: str


ActionName = Literal["git_status", "git_pull", "list_files"]


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionName


class FileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    is_dir: bool
    size: int


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    files: list[FileEntry] | None = None


class LogsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[str]


class SystemStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_percent: float
    load_avg: list[float]
    mem_total: int
    mem_used: int
    disk_total: int
    disk_used: int
    uptime_seconds: int
    hostname: str
    local_time_iso: str
