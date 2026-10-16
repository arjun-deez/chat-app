import os
import sqlite3
from pathlib import Path

import aiosqlite

# The whole database is one file. Change its location with the DB_PATH setting if you want.
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "chat.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    member_limit INTEGER NOT NULL,
    password_hash BLOB,
    image_url TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS room_members (
    room_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    last_visited_at TEXT NOT NULL,
    UNIQUE(room_id, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    file_url TEXT,
    file_name TEXT,
    file_size INTEGER,
    file_mimetype TEXT,
    created_at TEXT NOT NULL
);
"""

with sqlite3.connect(DB_PATH) as _conn:
    _conn.executescript(SCHEMA)


# ---------- users ----------

async def create_user(username: str, password_hash: bytes) -> int:
    """Raises sqlite3.IntegrityError if the username is taken."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)", (username, password_hash)
        )
        await conn.commit()
        return cur.lastrowid


async def get_user(username: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return await cur.fetchone()


# ---------- rooms ----------

# aesthetically consistent placeholder photos (picsum.photos, fixed seeds so they never change)
DUMMY_ROOMS = [
    ("General", 50, "https://picsum.photos/seed/general-room-chat/800/600"),
    ("Random", 20, "https://picsum.photos/seed/random-room-chat/800/600"),
    ("Study Group", 8, "https://picsum.photos/seed/study-room-chat/800/600"),
]


async def seed_dummy_rooms():
    """Adds a few starter rooms the first time the app runs. Safe to call every startup."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM rooms")
        (count,) = await cur.fetchone()
        if count:
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await conn.executemany(
            "INSERT INTO rooms (name, member_limit, password_hash, image_url, created_by, created_at) "
            "VALUES (?, ?, NULL, ?, NULL, ?)",
            [(name, limit, img, now) for name, limit, img in DUMMY_ROOMS],
        )
        await conn.commit()


async def create_room(name: str, member_limit: int, password_hash, image_url, created_by: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO rooms (name, member_limit, password_hash, image_url, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, member_limit, password_hash, image_url, created_by, created_at),
        )
        await conn.commit()
        return cur.lastrowid


async def get_room(room_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        return await cur.fetchone()


async def list_rooms(user_id: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT r.id, r.name, r.member_limit, r.created_by, r.created_at, r.image_url,
                      (r.password_hash IS NOT NULL) AS has_password,
                      (SELECT COUNT(*) FROM room_members m WHERE m.room_id = r.id) AS member_count,
                      EXISTS(SELECT 1 FROM room_members m WHERE m.room_id = r.id AND m.user_id = ?) AS is_member,
                      (SELECT last_visited_at FROM room_members m WHERE m.room_id = r.id AND m.user_id = ?) AS last_visited_at
               FROM rooms r ORDER BY r.id ASC""",
            (user_id, user_id),
        )
        return await cur.fetchall()


async def member_count(room_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM room_members WHERE room_id = ?", (room_id,))
        (count,) = await cur.fetchone()
        return count


async def is_member(room_id: int, user_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ?", (room_id, user_id)
        )
        return (await cur.fetchone()) is not None


async def visit_room(room_id: int, user_id: str, when: str):
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO room_members (room_id, user_id, joined_at, last_visited_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(room_id, user_id) DO UPDATE SET last_visited_at = excluded.last_visited_at""",
            (room_id, user_id, when, when),
        )
        await conn.commit()


# ---------- messages ----------

async def add_message(room_id, user_id, username, text, file, created_at) -> int:
    file = file or {}
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO messages
               (room_id, user_id, username, text, file_url, file_name, file_size, file_mimetype, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, user_id, username, text, file.get("url"), file.get("name"),
             file.get("size"), file.get("mimetype"), created_at),
        )
        await conn.commit()
        return cur.lastrowid


async def recent_messages(room_id: int, limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT * FROM (SELECT * FROM messages WHERE room_id = ? ORDER BY id DESC LIMIT ?)
               ORDER BY id ASC""",
            (room_id, limit),
        )
        return await cur.fetchall()
