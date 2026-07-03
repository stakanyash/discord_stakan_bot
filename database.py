"""Работа с базой данных: подключение, создание таблиц, CRUD-функции."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_FILE


# ─── Connection ───────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ─── Tables ───────────────────────────────────────────────────────────────

def create_tables():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                      user_id   INTEGER,
                      timestamp TEXT,
                      reason    TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS mutes (
                      user_id  INTEGER UNIQUE,
                      end_time TEXT,
                      reason   TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS bomb_cooldowns (
                      guild_id INTEGER PRIMARY KEY,
                      end_time TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS last_video_ids (
                      channel_id TEXT PRIMARY KEY,
                      video_id   TEXT
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS video_history (
                      channel_id TEXT,
                      video_id   TEXT,
                      PRIMARY KEY (channel_id, video_id)
                   )''')
        c.execute('''CREATE TABLE IF NOT EXISTS role_users (
                      user_id INTEGER PRIMARY KEY,
                      role_id INTEGER
                   )''')


# ─── Time helpers ─────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def dt_from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ─── Warnings ─────────────────────────────────────────────────────────────

def get_warnings(user_id: int) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, reason FROM warnings WHERE user_id = ? ORDER BY timestamp",
            (user_id,)
        ).fetchall()
    return [{'timestamp': r[0], 'reason': r[1]} for r in rows]


def add_warning(user_id: int, reason: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO warnings (user_id, timestamp, reason) VALUES (?, ?, ?)",
            (user_id, dt_to_iso(_utcnow()), reason)
        )


def remove_warnings(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))


def get_recent_warnings(user_id: int) -> list:
    """Возвращает предупреждения за последние 24 часа."""
    since = dt_to_iso(_utcnow() - __import__('datetime', fromlist=['timedelta']).timedelta(days=1))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT timestamp, reason FROM warnings WHERE user_id = ? AND timestamp > ?",
            (user_id, since)
        ).fetchall()
    return [{'timestamp': r[0], 'reason': r[1]} for r in rows]


# ─── Mutes ────────────────────────────────────────────────────────────────

def get_mutes() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT user_id, end_time, reason FROM mutes").fetchall()
    return {r[0]: {'end_time': r[1], 'reason': r[2]} for r in rows}


def add_mute(user_id: int, end_time: datetime, reason: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mutes (user_id, end_time, reason) VALUES (?, ?, ?)",
            (user_id, dt_to_iso(end_time), reason)
        )


def remove_mute(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))


# ─── Bomb cooldowns ──────────────────────────────────────────────────────

def get_bomb_cooldown(guild_id: int) -> datetime | None:
    with get_db() as conn:
        result = conn.execute(
            "SELECT end_time FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return dt_from_iso(result[0]) if result else None


def set_bomb_cooldown(guild_id: int, end_time: datetime):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bomb_cooldowns (guild_id, end_time) VALUES (?, ?)",
            (guild_id, dt_to_iso(end_time))
        )


def remove_bomb_cooldown(guild_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM bomb_cooldowns WHERE guild_id = ?", (guild_id,))


# ─── YouTube ──────────────────────────────────────────────────────────────

def get_last_video_id(channel_id: str) -> str | None:
    with get_db() as conn:
        result = conn.execute(
            "SELECT video_id FROM last_video_ids WHERE channel_id = ?", (channel_id,)
        ).fetchone()
    return result[0] if result else None


def set_last_video_id(channel_id: str, video_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO last_video_ids (channel_id, video_id) VALUES (?, ?)",
            (channel_id, video_id)
        )


def is_video_known(channel_id: str, video_id: str) -> bool:
    with get_db() as conn:
        result = conn.execute(
            "SELECT 1 FROM video_history WHERE channel_id = ? AND video_id = ?",
            (channel_id, video_id)
        ).fetchone()
    return result is not None


def add_video_to_history(channel_id: str, video_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO video_history (channel_id, video_id) VALUES (?, ?)",
            (channel_id, video_id)
        )


# ─── Role users ───────────────────────────────────────────────────────────

def add_role_user(user_id: int, role_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO role_users (user_id, role_id) VALUES (?, ?)",
            (user_id, role_id)
        )


def remove_role_user(user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM role_users WHERE user_id = ?", (user_id,))
