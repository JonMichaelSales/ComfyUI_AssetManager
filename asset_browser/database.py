from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import folder_paths

EXTENSION_NAME = "ComfyUI-Asset-Browser"
SCHEMA_VERSION = 1


def data_dir() -> Path:
    base = Path(folder_paths.get_user_directory())
    path = base / EXTENSION_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "assets.sqlite"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path()), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            subfolder TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'output',
            size INTEGER NOT NULL DEFAULT 0,
            mtime_ns INTEGER NOT NULL DEFAULT 0,
            ctime_ns INTEGER NOT NULL DEFAULT 0,
            width INTEGER,
            height INTEGER,
            format TEXT,
            has_prompt INTEGER NOT NULL DEFAULT 0,
            has_workflow INTEGER NOT NULL DEFAULT 0,
            prompt_json TEXT,
            workflow_json TEXT,
            metadata_json TEXT,
            workflow_hash TEXT,
            lora_names TEXT,
            model_name TEXT,
            sampler_name TEXT,
            steps INTEGER,
            cfg REAL,
            seed TEXT,
            duration_sec REAL,
            is_missing INTEGER NOT NULL DEFAULT 0,
            scan_error TEXT,
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_metadata (
            asset_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value_text TEXT,
            value_num REAL,
            value_bool INTEGER,
            ordinal INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (asset_id, key, ordinal),
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            started_at REAL,
            finished_at REAL,
            last_error TEXT,
            files_seen INTEGER NOT NULL DEFAULT 0,
            files_indexed INTEGER NOT NULL DEFAULT 0,
            files_failed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_annotations (
            asset_id TEXT PRIMARY KEY,
            favorite INTEGER NOT NULL DEFAULT 0,
            rating INTEGER,
            note TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            color TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_tags (
            asset_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (asset_id, tag_id),
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            description TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_assets (
            collection_id INTEGER NOT NULL,
            asset_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            PRIMARY KEY (collection_id, asset_id),
            FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_missing ON assets(is_missing)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_mtime ON assets(mtime_ns)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_format ON assets(format)")
    _ensure_column(conn, "assets", "workflow_hash", "TEXT")
    _ensure_column(conn, "assets", "lora_names", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_model ON assets(model_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_workflow ON assets(has_workflow)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_workflow_hash ON assets(workflow_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_filename ON assets(filename)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_meta_key_text ON asset_metadata(key, value_text)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_annotations_favorite ON asset_annotations(favorite)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_annotations_archived ON asset_annotations(archived)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_annotations_rating ON asset_annotations(rating)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_asset_tags_tag ON asset_tags(tag_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_collection_assets_collection ON collection_assets(collection_id, position)")
    cur = conn.execute("SELECT COUNT(*) AS count FROM schema_info")
    if cur.fetchone()["count"] == 0:
        conn.execute("INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def upsert_asset(conn: sqlite3.Connection, asset: dict[str, Any], meta_rows: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO assets (
            id, path, filename, subfolder, type, size, mtime_ns, ctime_ns,
            width, height, format, has_prompt, has_workflow, prompt_json,
            workflow_json, metadata_json, workflow_hash, lora_names, model_name, sampler_name, steps,
            cfg, seed, duration_sec, is_missing, scan_error, updated_at
        ) VALUES (
            :id, :path, :filename, :subfolder, :type, :size, :mtime_ns, :ctime_ns,
            :width, :height, :format, :has_prompt, :has_workflow, :prompt_json,
            :workflow_json, :metadata_json, :workflow_hash, :lora_names, :model_name, :sampler_name, :steps,
            :cfg, :seed, :duration_sec, 0, :scan_error, :updated_at
        )
        ON CONFLICT(path) DO UPDATE SET
            id = excluded.id,
            filename = excluded.filename,
            subfolder = excluded.subfolder,
            type = excluded.type,
            size = excluded.size,
            mtime_ns = excluded.mtime_ns,
            ctime_ns = excluded.ctime_ns,
            width = excluded.width,
            height = excluded.height,
            format = excluded.format,
            has_prompt = excluded.has_prompt,
            has_workflow = excluded.has_workflow,
            prompt_json = excluded.prompt_json,
            workflow_json = excluded.workflow_json,
            metadata_json = excluded.metadata_json,
            workflow_hash = excluded.workflow_hash,
            lora_names = excluded.lora_names,
            model_name = excluded.model_name,
            sampler_name = excluded.sampler_name,
            steps = excluded.steps,
            cfg = excluded.cfg,
            seed = excluded.seed,
            duration_sec = excluded.duration_sec,
            is_missing = 0,
            scan_error = excluded.scan_error,
            updated_at = excluded.updated_at
        """,
        asset,
    )
    conn.execute("DELETE FROM asset_metadata WHERE asset_id = ?", (asset["id"],))
    if meta_rows:
        conn.executemany(
            """
            INSERT INTO asset_metadata(asset_id, key, value_text, value_num, value_bool, ordinal)
            VALUES(:asset_id, :key, :value_text, :value_num, :value_bool, :ordinal)
            """,
            meta_rows,
        )


def mark_missing_except(conn: sqlite3.Connection, seen_paths: set[str]) -> int:
    rows = conn.execute("SELECT path FROM assets WHERE is_missing = 0").fetchall()
    missing = [row["path"] for row in rows if row["path"] not in seen_paths or not os.path.exists(row["path"])]
    if not missing:
        return 0
    conn.executemany("UPDATE assets SET is_missing = 1, updated_at = ? WHERE path = ?", [(time.time(), p) for p in missing])
    return len(missing)


def list_assets(
    *,
    limit: int,
    offset: int,
    query: str | None,
    workflow: str | None,
    fmt: str | None,
    model: str | None,
    exclude_model: str | None,
    lora: str | None,
    exclude_lora: str | None,
    workflow_hash: str | None,
    favorite: str | None = None,
    archived: str | None = None,
    rating: str | None = None,
    tag: str | None = None,
    collection: str | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    sampler: str | None = None,
    seed: str | None = None,
    duration: str | None = None,
    sort: str,
    order: str,
) -> dict[str, Any]:
    where, params = _asset_filter_where(
        query=query,
        workflow=workflow,
        fmt=fmt,
        model=model,
        exclude_model=exclude_model,
        lora=lora,
        exclude_lora=exclude_lora,
        workflow_hash=workflow_hash,
        favorite=favorite,
        archived=archived,
        rating=rating,
        tag=tag,
        collection=collection,
        min_width=min_width,
        min_height=min_height,
        date_from=date_from,
        date_to=date_to,
        sampler=sampler,
        seed=seed,
        duration=duration,
    )
    sort_column = {
        "filename": "filename",
        "modified": "mtime_ns",
        "size": "size",
        "model": "model_name",
        "rating": "COALESCE(a.rating, 0)",
        "duration": "duration_sec",
    }.get(sort, "mtime_ns")
    order_sql = "ASC" if order.lower() == "asc" else "DESC"
    with connect() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where}
            """,
            params,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT assets.id, filename, subfolder, type, size, mtime_ns, width, height,
                   format, has_prompt, has_workflow, workflow_hash, lora_names, model_name, sampler_name,
                   steps, cfg, seed, duration_sec,
                   COALESCE(a.favorite, 0) AS favorite, a.rating AS rating, COALESCE(a.archived, 0) AS archived, a.note AS note
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where}
            ORDER BY {sort_column} {order_sql}, filename ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {
        "assets": [asset_summary(dict(row)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }



def _asset_filter_where(
    *,
    query: str | None,
    workflow: str | None,
    fmt: str | None,
    model: str | None,
    exclude_model: str | None,
    lora: str | None,
    exclude_lora: str | None,
    workflow_hash: str | None,
    favorite: str | None = None,
    archived: str | None = None,
    rating: str | None = None,
    tag: str | None = None,
    collection: str | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    sampler: str | None = None,
    seed: str | None = None,
    duration: str | None = None,
) -> tuple[str, list[Any]]:
    clauses = ["is_missing = 0"]
    params: list[Any] = []
    if query:
        like = f"%{query}%"
        clauses.append("(filename LIKE ? OR model_name LIKE ? OR sampler_name LIKE ? OR prompt_json LIKE ? OR metadata_json LIKE ?)")
        params.extend([like, like, like, like, like])
    if workflow == "1":
        clauses.append("has_workflow = 1")
    elif workflow == "0":
        clauses.append("has_workflow = 0")
    if fmt:
        clauses.append("LOWER(format) = LOWER(?)")
        params.append(fmt)
    if model:
        clauses.append("model_name = ?")
        params.append(model)
    if exclude_model:
        clauses.append("(model_name IS NULL OR model_name != ?)")
        params.append(exclude_model)
    if lora:
        clauses.append("lora_names LIKE ?")
        params.append(f'%"{lora}"%')
    if exclude_lora:
        clauses.append("(lora_names IS NULL OR lora_names NOT LIKE ?)")
        params.append(f'%"{exclude_lora}"%')
    if workflow_hash:
        clauses.append("workflow_hash = ?")
        params.append(workflow_hash)
    if favorite == "1":
        clauses.append("COALESCE(a.favorite, 0) = 1")
    elif favorite == "0":
        clauses.append("COALESCE(a.favorite, 0) = 0")
    if archived == "1":
        clauses.append("COALESCE(a.archived, 0) = 1")
    elif archived != "all":
        clauses.append("COALESCE(a.archived, 0) = 0")
    if rating:
        clauses.append("COALESCE(a.rating, 0) >= ?")
        params.append(_int_or_none(rating) or 0)
    if tag:
        clauses.append("EXISTS (SELECT 1 FROM asset_tags at JOIN tags t ON t.id = at.tag_id WHERE at.asset_id = assets.id AND t.name = ? COLLATE NOCASE)")
        params.append(tag)
    if collection:
        clauses.append("EXISTS (SELECT 1 FROM collection_assets ca WHERE ca.asset_id = assets.id AND ca.collection_id = ?)")
        params.append(_int_or_none(collection) or -1)
    if min_width:
        clauses.append("width >= ?")
        params.append(min_width)
    if min_height:
        clauses.append("height >= ?")
        params.append(min_height)
    if date_from:
        clauses.append("mtime_ns >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("mtime_ns <= ?")
        params.append(date_to)
    if sampler:
        clauses.append("sampler_name = ?")
        params.append(sampler)
    if seed:
        clauses.append("seed = ?")
        params.append(seed)
    if duration == "1":
        clauses.append("duration_sec IS NOT NULL")
    elif duration == "0":
        clauses.append("duration_sec IS NULL")
    return " AND ".join(clauses), params


def list_filter_options(
    *,
    query: str | None,
    workflow: str | None,
    fmt: str | None,
    model: str | None,
    exclude_model: str | None,
    lora: str | None,
    exclude_lora: str | None,
    workflow_hash: str | None,
    favorite: str | None = None,
    archived: str | None = None,
    rating: str | None = None,
    tag: str | None = None,
    collection: str | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    sampler: str | None = None,
    seed: str | None = None,
    duration: str | None = None,
) -> dict[str, Any]:
    where, params = _asset_filter_where(
        query=query,
        workflow=workflow,
        fmt=fmt,
        model=model,
        exclude_model=exclude_model,
        lora=lora,
        exclude_lora=exclude_lora,
        workflow_hash=workflow_hash,
        favorite=favorite,
        archived=archived,
        rating=rating,
        tag=tag,
        collection=collection,
        min_width=min_width,
        min_height=min_height,
        date_from=date_from,
        date_to=date_to,
        sampler=sampler,
        seed=seed,
        duration=duration,
    )
    with connect() as conn:
        model_rows = conn.execute(
            f"""
            SELECT model_name AS value, COUNT(*) AS count
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where} AND model_name IS NOT NULL AND model_name != ''
            GROUP BY model_name
            ORDER BY count DESC, value ASC
            LIMIT 200
            """,
            params,
        ).fetchall()
        workflow_rows = conn.execute(
            f"""
            SELECT workflow_hash AS value, COUNT(*) AS count, MAX(model_name) AS model
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where} AND workflow_hash IS NOT NULL AND workflow_hash != ''
            GROUP BY workflow_hash
            ORDER BY count DESC, value ASC
            LIMIT 200
            """,
            params,
        ).fetchall()
        lora_source = conn.execute(
            f"""
            SELECT lora_names
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where} AND lora_names IS NOT NULL AND lora_names != ''
            """,
            params,
        ).fetchall()
        sampler_rows = conn.execute(
            f"""
            SELECT sampler_name AS value, COUNT(*) AS count
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE {where} AND sampler_name IS NOT NULL AND sampler_name != ''
            GROUP BY sampler_name
            ORDER BY count DESC, value ASC
            LIMIT 200
            """,
            params,
        ).fetchall()
        tag_rows = conn.execute(
            """
            SELECT t.name AS value, COUNT(at.asset_id) AS count
            FROM tags t
            LEFT JOIN asset_tags at ON at.tag_id = t.id
            GROUP BY t.id
            ORDER BY count DESC, lower(t.name)
            LIMIT 200
            """
        ).fetchall()
        collection_rows = conn.execute(
            """
            SELECT c.id AS value, c.name AS label, COUNT(ca.asset_id) AS count
            FROM collections c
            LEFT JOIN collection_assets ca ON ca.collection_id = c.id
            GROUP BY c.id
            ORDER BY count DESC, lower(c.name)
            LIMIT 200
            """
        ).fetchall()
    lora_counts: dict[str, int] = {}
    for row in lora_source:
        for name in load_json(row["lora_names"]) or []:
            name = str(name)
            lora_counts[name] = lora_counts.get(name, 0) + 1
    return {
        "models": [dict(row) for row in model_rows],
        "loras": [
            {"value": name, "count": count}
            for name, count in sorted(lora_counts.items(), key=lambda item: (-item[1], item[0].lower()))[:200]
        ],
        "workflows": [dict(row) for row in workflow_rows],
        "samplers": [dict(row) for row in sampler_rows],
        "tags": [dict(row) for row in tag_rows],
        "collections": [dict(row) for row in collection_rows],
    }

def get_asset(asset_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT assets.*, COALESCE(a.favorite, 0) AS favorite, a.rating AS rating,
                   COALESCE(a.archived, 0) AS archived, a.note AS note
            FROM assets
            LEFT JOIN asset_annotations a ON a.asset_id = assets.id
            WHERE assets.id = ?
            """,
            (asset_id,),
        ).fetchone()
        tags = _asset_tags(conn, asset_id)
        collections = _asset_collections(conn, asset_id)
    if not row:
        return None
    detail = asset_detail(dict(row))
    detail["tags"] = tags
    detail["collections"] = collections
    return detail


def asset_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "subfolder": row["subfolder"],
        "type": row["type"],
        "size": row["size"],
        "modified": row["mtime_ns"],
        "width": row["width"],
        "height": row["height"],
        "format": row["format"],
        "has_prompt": bool(row["has_prompt"]),
        "has_workflow": bool(row["has_workflow"]),
        "workflow_hash": row.get("workflow_hash"),
        "lora_names": load_json(row.get("lora_names")) or [],
        "model_name": row["model_name"],
        "sampler_name": row["sampler_name"],
        "steps": row["steps"],
        "cfg": row["cfg"],
        "seed": row["seed"],
        "duration_sec": row["duration_sec"],
        "favorite": bool(row.get("favorite", 0)),
        "rating": row.get("rating"),
        "archived": bool(row.get("archived", 0)),
        "note": row.get("note"),
        "view_url": build_view_url(row["filename"], row["subfolder"], row["type"]),
    }


def asset_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = asset_summary(row)
    detail["created"] = row["ctime_ns"]
    detail["scan_error"] = row["scan_error"]
    detail["metadata"] = load_json(row.get("metadata_json")) or {}
    detail["prompt"] = load_json(row.get("prompt_json"))
    return detail


def update_annotation(asset_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    if get_asset(asset_id) is None:
        return None
    favorite = _bool_int(values.get("favorite"))
    archived = _bool_int(values.get("archived"))
    rating = _rating_or_none(values.get("rating"))
    note = str(values.get("note") or "").strip() or None
    now = time.time()
    with connect() as conn:
        current = conn.execute("SELECT * FROM asset_annotations WHERE asset_id = ?", (asset_id,)).fetchone()
        if current:
            favorite = current["favorite"] if favorite is None else favorite
            archived = current["archived"] if archived is None else archived
            rating = current["rating"] if "rating" not in values else rating
            note = current["note"] if "note" not in values else note
        conn.execute(
            """
            INSERT INTO asset_annotations(asset_id, favorite, rating, note, archived, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                favorite = excluded.favorite,
                rating = excluded.rating,
                note = excluded.note,
                archived = excluded.archived,
                updated_at = excluded.updated_at
            """,
            (asset_id, favorite or 0, rating, note, archived or 0, now),
        )
    return get_asset(asset_id)


def list_tags() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.color, COUNT(at.asset_id) AS count
            FROM tags t
            LEFT JOIN asset_tags at ON at.tag_id = t.id
            GROUP BY t.id
            ORDER BY lower(t.name)
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_tag(name: str, color: str | None = None) -> dict[str, Any]:
    now = time.time()
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Tag name is required.")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tags(name, color, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET color = COALESCE(excluded.color, tags.color), updated_at = excluded.updated_at
            """,
            (clean_name, color, now, now),
        )
        row = conn.execute("SELECT id, name, color FROM tags WHERE name = ? COLLATE NOCASE", (clean_name,)).fetchone()
    return dict(row)


def update_tag(tag_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
        if not row:
            return None
        name = str(values.get("name") or row["name"]).strip()
        color = values.get("color", row["color"])
        conn.execute("UPDATE tags SET name = ?, color = ?, updated_at = ? WHERE id = ?", (name, color, time.time(), tag_id))
        updated = conn.execute("SELECT id, name, color FROM tags WHERE id = ?", (tag_id,)).fetchone()
    return dict(updated)


def delete_tag(tag_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        return cur.rowcount > 0


def add_asset_tag(asset_id: str, tag_name: str) -> dict[str, Any] | None:
    if get_asset(asset_id) is None:
        return None
    tag = create_tag(tag_name)
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO asset_tags(asset_id, tag_id, created_at) VALUES(?, ?, ?)",
            (asset_id, tag["id"], time.time()),
        )
    return get_asset(asset_id)


def remove_asset_tag(asset_id: str, tag_name: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)).fetchone()
        if row:
            conn.execute("DELETE FROM asset_tags WHERE asset_id = ? AND tag_id = ?", (asset_id, row["id"]))
    return get_asset(asset_id)


def list_collections() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.description, COUNT(ca.asset_id) AS count
            FROM collections c
            LEFT JOIN collection_assets ca ON ca.collection_id = c.id
            GROUP BY c.id
            ORDER BY lower(c.name)
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_collection(name: str, description: str | None = None) -> dict[str, Any]:
    now = time.time()
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Collection name is required.")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO collections(name, description, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET description = COALESCE(excluded.description, collections.description), updated_at = excluded.updated_at
            """,
            (clean_name, description, now, now),
        )
        row = conn.execute("SELECT id, name, description FROM collections WHERE name = ? COLLATE NOCASE", (clean_name,)).fetchone()
    return dict(row)


def update_collection(collection_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM collections WHERE id = ?", (collection_id,)).fetchone()
        if not row:
            return None
        name = str(values.get("name") or row["name"]).strip()
        description = values.get("description", row["description"])
        conn.execute(
            "UPDATE collections SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (name, description, time.time(), collection_id),
        )
        updated = conn.execute("SELECT id, name, description FROM collections WHERE id = ?", (collection_id,)).fetchone()
    return dict(updated)


def delete_collection(collection_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        return cur.rowcount > 0


def add_asset_to_collection(collection_id: int, asset_id: str) -> dict[str, Any] | None:
    if get_asset(asset_id) is None:
        return None
    with connect() as conn:
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) AS pos FROM collection_assets WHERE collection_id = ?",
            (collection_id,),
        ).fetchone()["pos"]
        conn.execute(
            "INSERT OR IGNORE INTO collection_assets(collection_id, asset_id, position, created_at) VALUES(?, ?, ?, ?)",
            (collection_id, asset_id, int(max_pos) + 1, time.time()),
        )
    return get_asset(asset_id)


def remove_asset_from_collection(collection_id: int, asset_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        conn.execute("DELETE FROM collection_assets WHERE collection_id = ? AND asset_id = ?", (collection_id, asset_id))
    return get_asset(asset_id)


def related_assets(asset_id: str, limit: int = 18) -> dict[str, list[dict[str, Any]]]:
    asset = get_asset(asset_id)
    if not asset:
        return {}
    related: dict[str, list[dict[str, Any]]] = {}
    with connect() as conn:
        for key, clause, params in [
            ("workflow", "workflow_hash = ? AND workflow_hash IS NOT NULL AND workflow_hash != ''", [asset.get("workflow_hash")]),
            ("model", "model_name = ? AND model_name IS NOT NULL AND model_name != ''", [asset.get("model_name")]),
            ("seed", "seed = ? AND seed IS NOT NULL AND seed != ''", [asset.get("seed")]),
        ]:
            if not params[0]:
                related[key] = []
                continue
            rows = conn.execute(
                f"""
                SELECT assets.*, COALESCE(a.favorite, 0) AS favorite, a.rating AS rating,
                       COALESCE(a.archived, 0) AS archived, a.note AS note
                FROM assets
                LEFT JOIN asset_annotations a ON a.asset_id = assets.id
                WHERE is_missing = 0 AND COALESCE(a.archived, 0) = 0 AND assets.id != ? AND {clause}
                ORDER BY mtime_ns DESC
                LIMIT ?
                """,
                [asset_id, *params, limit],
            ).fetchall()
            related[key] = [asset_summary(dict(row)) for row in rows]
        loras = asset.get("lora_names") or []
        if loras:
            rows = conn.execute(
                """
                SELECT assets.*, COALESCE(a.favorite, 0) AS favorite, a.rating AS rating,
                       COALESCE(a.archived, 0) AS archived, a.note AS note
                FROM assets
                LEFT JOIN asset_annotations a ON a.asset_id = assets.id
                WHERE is_missing = 0 AND COALESCE(a.archived, 0) = 0 AND assets.id != ?
                  AND lora_names LIKE ?
                ORDER BY mtime_ns DESC
                LIMIT ?
                """,
                (asset_id, f'%"{loras[0]}"%', limit),
            ).fetchall()
            related["lora"] = [asset_summary(dict(row)) for row in rows]
        else:
            related["lora"] = []
        collection_ids = [c["id"] for c in asset.get("collections") or []]
        if collection_ids:
            placeholders = ",".join("?" for _ in collection_ids)
            rows = conn.execute(
                f"""
                SELECT DISTINCT assets.*, COALESCE(a.favorite, 0) AS favorite, a.rating AS rating,
                       COALESCE(a.archived, 0) AS archived, a.note AS note
                FROM assets
                JOIN collection_assets ca ON ca.asset_id = assets.id
                LEFT JOIN asset_annotations a ON a.asset_id = assets.id
                WHERE is_missing = 0 AND assets.id != ? AND ca.collection_id IN ({placeholders})
                ORDER BY mtime_ns DESC
                LIMIT ?
                """,
                [asset_id, *collection_ids, limit],
            ).fetchall()
            related["collections"] = [asset_summary(dict(row)) for row in rows]
        else:
            related["collections"] = []
    return related


def _asset_tags(conn: sqlite3.Connection, asset_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT t.id, t.name, t.color
            FROM tags t
            JOIN asset_tags at ON at.tag_id = t.id
            WHERE at.asset_id = ?
            ORDER BY lower(t.name)
            """,
            (asset_id,),
        ).fetchall()
    ]


def _asset_collections(conn: sqlite3.Connection, asset_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT c.id, c.name, c.description
            FROM collections c
            JOIN collection_assets ca ON ca.collection_id = c.id
            WHERE ca.asset_id = ?
            ORDER BY lower(c.name)
            """,
            (asset_id,),
        ).fetchall()
    ]


def build_view_url(filename: str, subfolder: str, file_type: str) -> str:
    from urllib.parse import quote

    url = f"/view?type={quote(file_type)}&filename={quote(filename)}"
    if subfolder:
        url += f"&subfolder={quote(subfolder)}"
    return url


def load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        return 1 if value.lower() in {"1", "true", "yes", "on"} else 0
    return 1 if bool(value) else 0


def _rating_or_none(value: Any) -> int | None:
    rating = _int_or_none(value)
    if rating is None:
        return None
    return min(max(rating, 0), 5)
