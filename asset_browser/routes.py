from __future__ import annotations

import json
from typing import Any

from aiohttp import web
from server import PromptServer

from .database import get_asset, list_assets, list_filter_options
from .scanner import get_status, start_scan

_ROUTES_REGISTERED = False


def register_routes() -> None:
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    _ROUTES_REGISTERED = True
    routes = PromptServer.instance.routes

    @routes.get("/asset-browser/assets")
    async def asset_browser_assets(request: web.Request) -> web.Response:
        limit = _bounded_int(request.query.get("limit"), 50, 1, 200)
        offset = _bounded_int(request.query.get("offset"), 0, 0, 10_000_000)
        payload = list_assets(
            limit=limit,
            offset=offset,
            query=_clean(request.query.get("q")),
            workflow=_clean(request.query.get("workflow")),
            fmt=_clean(request.query.get("format")),
            model=_clean(request.query.get("model")),
            exclude_model=_clean(request.query.get("exclude_model")),
            lora=_clean(request.query.get("lora")),
            exclude_lora=_clean(request.query.get("exclude_lora")),
            workflow_hash=_clean(request.query.get("workflow_hash")),
            sort=_clean(request.query.get("sort")) or "modified",
            order=_clean(request.query.get("order")) or "desc",
        )
        return web.json_response(payload)


    @routes.get("/asset-browser/filters")
    async def asset_browser_filters(request: web.Request) -> web.Response:
        payload = list_filter_options(
            query=_clean(request.query.get("q")),
            workflow=_clean(request.query.get("workflow")),
            fmt=_clean(request.query.get("format")),
            model=_clean(request.query.get("model")),
            exclude_model=_clean(request.query.get("exclude_model")),
            lora=_clean(request.query.get("lora")),
            exclude_lora=_clean(request.query.get("exclude_lora")),
            workflow_hash=_clean(request.query.get("workflow_hash")),
        )
        return web.json_response(payload)

    @routes.get("/asset-browser/assets/{asset_id}")
    async def asset_browser_asset_detail(request: web.Request) -> web.Response:
        asset = get_asset(request.match_info["asset_id"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.get("/asset-browser/assets/{asset_id}/metadata")
    async def asset_browser_asset_metadata(request: web.Request) -> web.Response:
        asset = get_asset(request.match_info["asset_id"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response({
            "id": asset["id"],
            "metadata": asset.get("metadata") or {},
            "prompt": asset.get("prompt"),
        })

    @routes.get("/asset-browser/assets/{asset_id}/workflow")
    async def asset_browser_asset_workflow(request: web.Request) -> web.Response:
        asset = get_asset(request.match_info["asset_id"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        workflow_json = _get_raw_workflow(asset["id"])
        if workflow_json is None:
            return _json_error(404, "NO_WORKFLOW", "Asset has no embedded workflow metadata.")
        try:
            workflow = json.loads(workflow_json)
        except json.JSONDecodeError:
            workflow = workflow_json
        return web.json_response({"id": asset["id"], "workflow": workflow})

    @routes.post("/asset-browser/scan")
    async def asset_browser_scan(request: web.Request) -> web.Response:
        started = start_scan()
        status = get_status()
        return web.json_response({"started": started, "status": status})

    @routes.get("/asset-browser/scan/status")
    async def asset_browser_scan_status(request: web.Request) -> web.Response:
        return web.json_response(get_status())


def _get_raw_workflow(asset_id: str) -> str | None:
    from .database import connect

    with connect() as conn:
        row = conn.execute("SELECT workflow_json FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        return None
    return row["workflow_json"]


def _bounded_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        parsed = default
    return min(max(parsed, minimum), maximum)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _json_error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> web.Response:
    return web.json_response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=status,
    )
