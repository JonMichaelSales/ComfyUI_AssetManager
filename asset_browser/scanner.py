from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any

import folder_paths

from .database import connect, mark_missing_except, upsert_asset
from .metadata import extract_asset, supported_image

LOGGER = logging.getLogger("ComfyUI-Asset-Browser")


@dataclass
class ScanStatus:
    running: bool = False
    started_at: float | None = None
    finished_at: float | None = None
    files_seen: int = 0
    files_indexed: int = 0
    files_failed: int = 0
    missing_marked: int = 0
    last_error: str | None = None


_status = ScanStatus()
_lock = threading.Lock()
_background_started = False


def get_status() -> dict[str, Any]:
    with _lock:
        return asdict(_status)


def start_scan(*, background: bool = False) -> bool:
    with _lock:
        if _status.running:
            return False
        _status.running = True
        _status.started_at = time.time()
        _status.finished_at = None
        _status.files_seen = 0
        _status.files_indexed = 0
        _status.files_failed = 0
        _status.missing_marked = 0
        _status.last_error = None

    thread = threading.Thread(target=_scan_worker, name="ComfyUIAssetBrowserScan", daemon=True)
    thread.start()
    if not background:
        LOGGER.info("Asset Browser scan started")
    return True


def start_background_scan_once(delay_seconds: float = 8.0) -> None:
    global _background_started
    if _background_started:
        return
    _background_started = True

    def delayed() -> None:
        time.sleep(delay_seconds)
        start_scan(background=True)

    threading.Thread(target=delayed, name="ComfyUIAssetBrowserStartupScan", daemon=True).start()


def _scan_worker() -> None:
    seen_paths: set[str] = set()
    try:
        output_dir = os.path.abspath(folder_paths.get_output_directory())
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_state(id, started_at, finished_at, last_error, files_seen, files_indexed, files_failed)
                VALUES(1, ?, NULL, NULL, 0, 0, 0)
                ON CONFLICT(id) DO UPDATE SET
                    started_at = excluded.started_at,
                    finished_at = NULL,
                    last_error = NULL,
                    files_seen = 0,
                    files_indexed = 0,
                    files_failed = 0
                """,
                (time.time(),),
            )

        for root, _, files in os.walk(output_dir):
            for filename in files:
                path = os.path.join(root, filename)
                if not supported_image(path):
                    continue
                seen_paths.add(os.path.abspath(path))
                _increment("files_seen")
                try:
                    asset, rows = extract_asset(path, output_dir)
                    with connect() as conn:
                        upsert_asset(conn, asset, rows)
                    _increment("files_indexed")
                except Exception as exc:  # keep scan resilient for bad files
                    LOGGER.warning("Failed to index asset %s: %s", path, exc)
                    _increment("files_failed")

        with connect() as conn:
            missing = mark_missing_except(conn, seen_paths)
            conn.execute(
                """
                UPDATE scan_state
                SET finished_at = ?, files_seen = ?, files_indexed = ?, files_failed = ?, last_error = NULL
                WHERE id = 1
                """,
                (time.time(), _status.files_seen, _status.files_indexed, _status.files_failed),
            )
        with _lock:
            _status.missing_marked = missing
    except Exception as exc:
        LOGGER.exception("Asset Browser scan failed")
        with _lock:
            _status.last_error = str(exc)
        try:
            with connect() as conn:
                conn.execute(
                    "UPDATE scan_state SET finished_at = ?, last_error = ? WHERE id = 1",
                    (time.time(), str(exc)),
                )
        except Exception:
            LOGGER.exception("Failed to persist scan error")
    finally:
        with _lock:
            _status.running = False
            _status.finished_at = time.time()


def _increment(field: str) -> None:
    with _lock:
        setattr(_status, field, getattr(_status, field) + 1)
