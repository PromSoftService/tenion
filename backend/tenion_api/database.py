from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Registration:
    email: str
    username: str
    status: str


@dataclass(frozen=True)
class AdminSession:
    csrf_token: str
    expires_at: str


class RegistrationDatabase:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (
                        status IN ('processing', 'mail_failed', 'enable_failed', 'sent')
                    ),
                    consent_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    email_sent_at TEXT,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS registration_attempts (
                    id INTEGER PRIMARY KEY,
                    ip_hash TEXT NOT NULL,
                    email_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS registration_attempts_ip_time
                    ON registration_attempts (ip_hash, created_at);
                CREATE INDEX IF NOT EXISTS registration_attempts_email_time
                    ON registration_attempts (email_hash, created_at);

                CREATE TABLE IF NOT EXISTS contact_attempts (
                    id INTEGER PRIMARY KEY,
                    ip_hash TEXT NOT NULL,
                    email_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS contact_attempts_ip_time
                    ON contact_attempts (ip_hash, created_at);
                CREATE INDEX IF NOT EXISTS contact_attempts_email_time
                    ON contact_attempts (email_hash, created_at);

                CREATE TABLE IF NOT EXISTS admin_login_failures (
                    id INTEGER PRIMARY KEY,
                    ip_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS admin_login_failures_ip_time
                    ON admin_login_failures (ip_hash, created_at);

                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS admin_sessions_expiry
                    ON admin_sessions (expires_at);
                """
            )

    def record_attempt_and_check_limit(self, ip_hash: str, email_hash: str) -> bool:
        now = utc_now()
        ten_minutes_ago = timestamp(now - timedelta(minutes=10))
        one_hour_ago = timestamp(now - timedelta(hours=1))
        one_day_ago = timestamp(now - timedelta(days=1))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM registration_attempts WHERE created_at < ?", (one_day_ago,)
            )
            ip_count = connection.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE ip_hash = ? AND created_at >= ?",
                (ip_hash, ten_minutes_ago),
            ).fetchone()[0]
            email_count = connection.execute(
                "SELECT COUNT(*) FROM registration_attempts WHERE email_hash = ? AND created_at >= ?",
                (email_hash, one_hour_ago),
            ).fetchone()[0]
            if ip_count >= 5 or email_count >= 3:
                connection.commit()
                return False
            connection.execute(
                "INSERT INTO registration_attempts (ip_hash, email_hash, created_at) VALUES (?, ?, ?)",
                (ip_hash, email_hash, timestamp(now)),
            )
            connection.commit()
            return True

    def begin_registration(self, email: str, username: str) -> tuple[Registration, bool]:
        now = timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            by_email = connection.execute(
                "SELECT email, username, status FROM registrations WHERE email = ?", (email,)
            ).fetchone()
            by_username = connection.execute(
                "SELECT email, username, status FROM registrations WHERE username = ?", (username,)
            ).fetchone()

            if by_email and by_email[1] != username:
                raise EmailAlreadyRegistered
            if by_username and by_username[0] != email:
                raise UsernameAlreadyRegistered
            if by_email:
                registration = Registration(*by_email)
                if registration.status == "sent":
                    raise EmailAlreadyRegistered
                connection.execute(
                    "UPDATE registrations SET status = 'processing', updated_at = ?, last_error = NULL WHERE email = ?",
                    (now, email),
                )
                connection.commit()
                return Registration(email, username, "processing"), True

            connection.execute(
                """
                INSERT INTO registrations (
                    email, username, status, consent_at, created_at, updated_at
                ) VALUES (?, ?, 'processing', ?, ?, ?)
                """,
                (email, username, now, now, now),
            )
            connection.commit()
            return Registration(email, username, "processing"), False

    def record_contact_attempt_and_check_limit(
        self, ip_hash: str, email_hash: str
    ) -> bool:
        now = utc_now()
        ten_minutes_ago = timestamp(now - timedelta(minutes=10))
        one_hour_ago = timestamp(now - timedelta(hours=1))
        one_day_ago = timestamp(now - timedelta(days=1))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM contact_attempts WHERE created_at < ?", (one_day_ago,)
            )
            ip_count = connection.execute(
                "SELECT COUNT(*) FROM contact_attempts WHERE ip_hash = ? AND created_at >= ?",
                (ip_hash, ten_minutes_ago),
            ).fetchone()[0]
            email_count = connection.execute(
                "SELECT COUNT(*) FROM contact_attempts WHERE email_hash = ? AND created_at >= ?",
                (email_hash, one_hour_ago),
            ).fetchone()[0]
            if ip_count >= 5 or email_count >= 3:
                connection.commit()
                return False
            connection.execute(
                "INSERT INTO contact_attempts (ip_hash, email_hash, created_at) VALUES (?, ?, ?)",
                (ip_hash, email_hash, timestamp(now)),
            )
            connection.commit()
            return True

    def set_status(self, email: str, status: str, error: str | None = None) -> None:
        sent_at = timestamp() if status == "sent" else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE registrations
                SET status = ?, updated_at = ?, email_sent_at = COALESCE(?, email_sent_at), last_error = ?
                WHERE email = ?
                """,
                (status, timestamp(), sent_at, error, email),
            )

    def discard_unsent(self, email: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM registrations WHERE email = ? AND status != 'sent'", (email,)
            )

    def registration_emails_by_username(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT username, email FROM registrations"
            ).fetchall()
        return {str(username): str(email) for username, email in rows}

    def delete_registration_by_username(self, username: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM registrations WHERE username = ?", (username,)
            )
            return cursor.rowcount > 0

    def admin_login_allowed(self, ip_hash: str) -> bool:
        now = utc_now()
        cutoff = timestamp(now - timedelta(minutes=15))
        prune_before = timestamp(now - timedelta(days=1))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM admin_login_failures WHERE created_at < ?",
                (prune_before,),
            )
            count = connection.execute(
                """SELECT COUNT(*) FROM admin_login_failures
                   WHERE ip_hash = ? AND created_at >= ?""",
                (ip_hash, cutoff),
            ).fetchone()[0]
            connection.commit()
            return count < 5

    def record_admin_login_failure(self, ip_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO admin_login_failures (ip_hash, created_at) VALUES (?, ?)",
                (ip_hash, timestamp()),
            )

    def clear_admin_login_failures(self, ip_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM admin_login_failures WHERE ip_hash = ?", (ip_hash,)
            )

    def create_admin_session(
        self, token_hash: str, csrf_token: str, expires_at: str
    ) -> None:
        now = timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM admin_sessions WHERE expires_at <= ?", (now,)
            )
            connection.execute(
                """INSERT INTO admin_sessions (
                       token_hash, csrf_token, created_at, last_seen_at, expires_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (token_hash, csrf_token, now, now, expires_at),
            )
            connection.commit()

    def get_admin_session(self, token_hash: str) -> AdminSession | None:
        now = timestamp()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM admin_sessions WHERE expires_at <= ?", (now,)
            )
            row = connection.execute(
                """SELECT csrf_token, expires_at FROM admin_sessions
                   WHERE token_hash = ?""",
                (token_hash,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                "UPDATE admin_sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now, token_hash),
            )
            connection.commit()
            return AdminSession(csrf_token=str(row[0]), expires_at=str(row[1]))

    def delete_admin_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash,)
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


class EmailAlreadyRegistered(Exception):
    pass


class UsernameAlreadyRegistered(Exception):
    pass
