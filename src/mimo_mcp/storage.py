"""SQLite 持久化层(aiosqlite)。voices / audit_log 两张表。

仅维护表结构 + 基本增删查;复杂业务编排放到 api/* 层去。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from .models import AuditLogEntry, VoiceRecord, VoiceSource, VoiceStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS voices (
    voice_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('default','clone','design')),
    status          TEXT NOT NULL DEFAULT 'ready',
    description     TEXT,
    voice_prompt    TEXT,
    reference_path  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,
    channel         TEXT NOT NULL CHECK (channel IN ('mcp','web')),
    tool            TEXT NOT NULL,
    model           TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    latency_ms      INTEGER,
    status          TEXT NOT NULL DEFAULT 'ok',
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_voices_source ON voices (source);
"""


def _row_to_voice(row: aiosqlite.Row) -> VoiceRecord:
    return VoiceRecord(
        voice_id=row["voice_id"],
        name=row["name"],
        source=VoiceSource(row["source"]),
        status=VoiceStatus(row["status"]),
        description=row["description"],
        voice_prompt=row["voice_prompt"],
        reference_path=row["reference_path"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class Storage:
    """轻量包装,使用前必须 await init()。多任务共享单例即可。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def list_voices(self, source: VoiceSource | None = None) -> list[VoiceRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if source:
                cursor = await db.execute(
                    "SELECT * FROM voices WHERE source = ? ORDER BY created_at DESC",
                    (source.value,),
                )
            else:
                cursor = await db.execute("SELECT * FROM voices ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [_row_to_voice(r) for r in rows]

    async def get_voice(self, voice_id: str) -> VoiceRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM voices WHERE voice_id = ?", (voice_id,))
            row = await cursor.fetchone()
            return _row_to_voice(row) if row else None

    async def upsert_voice(self, record: VoiceRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO voices (voice_id, name, source, status, description, voice_prompt,
                                    reference_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(voice_id) DO UPDATE SET
                    name = excluded.name,
                    source = excluded.source,
                    status = excluded.status,
                    description = excluded.description,
                    voice_prompt = excluded.voice_prompt,
                    reference_path = excluded.reference_path,
                    updated_at = excluded.updated_at
                """,
                (
                    record.voice_id,
                    record.name,
                    record.source.value,
                    record.status.value,
                    record.description,
                    record.voice_prompt,
                    record.reference_path,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def delete_voice(self, voice_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM voices WHERE voice_id = ?", (voice_id,))
            await db.commit()
            return (cursor.rowcount or 0) > 0

    async def append_audit(self, entry: AuditLogEntry) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO audit_log (ts, channel, tool, model, input_tokens, output_tokens,
                                       latency_ms, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.ts.isoformat(),
                    entry.channel,
                    entry.tool,
                    entry.model,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.latency_ms,
                    entry.status,
                    entry.error,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def recent_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
