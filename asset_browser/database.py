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
    sort: str,
    order: str,
) -> dict[str, Any]:
    clauses = ["is_missing = 0"]
    params: list[Any] = []
    if query:
        like = f"%{query}%"
        clauses.append(
            "(filename LIKE ? OR model_name LIKE ? OR sampler_name LIKE ? OR prompt_json LIKE ? OR metadata_json LIKE ?)"
        )
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

    sort_column = {
        "filename": "filename",
        "modified": "mtime_ns",
        "size": "size",
        "model": "model_name",
    }.get(sort, "mtime_ns")
    order_sql = "ASC" if order.lower() == "asc" else "DESC"
    where = " AND ".join(clauses)
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM assets WHERE {where}", params).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT id, filename, subfolder, type, size, mtime_ns, width, height,
                   format, has_prompt, has_workflow, workflow_hash, lora_names, model_name, sampler_name,
                   steps, cfg, seed, duration_sec
            FROM assets
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
    )
    with connect() as conn:
        model_rows = conn.execute(
            f"""
            SELECT model_name AS value, COUNT(*) AS count
            FROM assets
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
            WHERE {where} AND workflow_hash IS NOT NULL AND workflow_hash != ''
            GROUP BY workflow_hash
            ORDER BY count DESC, value ASC
            LIMIT 200
            """,
            params,
        ).fetchall()
        lora_source = conn.execute(
            f"SELECT lora_names FROM assets WHERE {where} AND lora_names IS NOT NULL AND lora_names != ''",
            params,
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
    }

def get_asset(asset_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        return None
    return asset_detail(dict(row))


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
        "view_url": build_view_url(row["filename"], row["subfolder"], row["type"]),
    }


def asset_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = asset_summary(row)
    detail["created"] = row["ctime_ns"]
    detail["scan_error"] = row["scan_error"]
    detail["metadata"] = load_json(row.get("metadata_json")) or {}
    detail["prompt"] = load_json(row.get("prompt_json"))
    return detail


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
