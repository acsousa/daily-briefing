"""SQLite persistence: one table per model.

Each table is `id TEXT PRIMARY KEY, data TEXT` (the full model as JSON) plus a few
promoted columns for filtering. The full object always round-trips through `data`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import (
    EpisodePlan,
    EpisodeSegment,
    InteractionContext,
    RawArticle,
    StoryCluster,
    StoryThread,
)

# model -> (table, {column: (sql_type, extractor)})
_SPECS = {
    RawArticle: ("raw_articles", {
        "source_id": ("TEXT", lambda o: o.source_id),
        "content_hash": ("TEXT", lambda o: o.content_hash),
        "published_at": ("TEXT", lambda o: o.published_at.isoformat()),
    }),
    StoryCluster: ("story_clusters", {
        "last_updated": ("TEXT", lambda o: o.last_updated.isoformat()),
    }),
    StoryThread: ("story_threads", {
        "topic": ("TEXT", lambda o: o.topic),
        "status": ("TEXT", lambda o: o.status),
        "last_briefed": ("TEXT", lambda o: o.last_briefed.isoformat()),
    }),
    EpisodePlan: ("episode_plans", {
        "date": ("TEXT", lambda o: o.date.isoformat()),
        "status": ("TEXT", lambda o: o.status),
    }),
    EpisodeSegment: ("episode_segments", {
        "episode_id": ("TEXT", lambda o: o.episode_id),
        "order_index": ("INTEGER", lambda o: o.order_index),
    }),
    InteractionContext: ("interaction_contexts", {
        "episode_id": ("TEXT", lambda o: o.episode_id),
    }),
}


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        for table, columns in _SPECS.values():
            extra = "".join(f', "{name}" {sql_type}' for name, (sql_type, _) in columns.items())
            self.conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, data TEXT NOT NULL{extra})"
            )
        self.conn.commit()

    def save(self, obj) -> None:
        table, columns = _SPECS[type(obj)]
        names = ["id", "data"] + list(columns)
        values = [obj.id, obj.model_dump_json()] + [ext(obj) for _, ext in columns.values()]
        placeholders = ", ".join("?" * len(names))
        cols_sql = ", ".join(f'"{n}"' for n in names)
        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES ({placeholders})", values
        )
        self.conn.commit()

    def save_many(self, objs) -> None:
        for obj in objs:
            self.save(obj)

    def get(self, cls, id: str):
        table, _ = _SPECS[cls]
        row = self.conn.execute(f"SELECT data FROM {table} WHERE id = ?", (id,)).fetchone()
        return cls.model_validate_json(row["data"]) if row else None

    def list(self, cls, **filters):
        table, _ = _SPECS[cls]
        where, params = "", []
        if filters:
            where = " WHERE " + " AND ".join(f'"{k}" = ?' for k in filters)
            params = list(filters.values())
        rows = self.conn.execute(f"SELECT data FROM {table}{where}", params).fetchall()
        return [cls.model_validate_json(r["data"]) for r in rows]

    def close(self) -> None:
        self.conn.close()
