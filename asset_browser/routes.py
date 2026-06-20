from __future__ import annotations

import json
from typing import Any

from aiohttp import web
from server import PromptServer

from .database import (
    add_asset_tag,
    add_asset_to_collection,
    create_collection,
    create_tag,
    delete_collection,
    delete_tag,
    get_asset,
    list_assets,
    list_collections,
    list_filter_options,
    list_tags,
    related_assets,
    remove_asset_from_collection,
    remove_asset_tag,
    update_annotation,
    update_collection,
    update_tag,
)
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
            favorite=_clean(request.query.get("favorite")),
            archived=_clean(request.query.get("archived")),
            rating=_clean(request.query.get("rating")),
            tag=_clean(request.query.get("tag")),
            collection=_clean(request.query.get("collection")),
            min_width=_optional_int(request.query.get("min_width")),
            min_height=_optional_int(request.query.get("min_height")),
            date_from=_optional_int(request.query.get("date_from")),
            date_to=_optional_int(request.query.get("date_to")),
            sampler=_clean(request.query.get("sampler")),
            seed=_clean(request.query.get("seed")),
            duration=_clean(request.query.get("duration")),
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
            favorite=_clean(request.query.get("favorite")),
            archived=_clean(request.query.get("archived")),
            rating=_clean(request.query.get("rating")),
            tag=_clean(request.query.get("tag")),
            collection=_clean(request.query.get("collection")),
            min_width=_optional_int(request.query.get("min_width")),
            min_height=_optional_int(request.query.get("min_height")),
            date_from=_optional_int(request.query.get("date_from")),
            date_to=_optional_int(request.query.get("date_to")),
            sampler=_clean(request.query.get("sampler")),
            seed=_clean(request.query.get("seed")),
            duration=_clean(request.query.get("duration")),
        )
        return web.json_response(payload)

    @routes.get("/asset-browser/assets/{asset_id}")
    async def asset_browser_asset_detail(request: web.Request) -> web.Response:
        asset = get_asset(request.match_info["asset_id"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.patch("/asset-browser/assets/{asset_id}/annotation")
    async def asset_browser_asset_annotation(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "BAD_JSON", "Expected a JSON object.")
        asset = update_annotation(request.match_info["asset_id"], body)
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.get("/asset-browser/assets/{asset_id}/related")
    async def asset_browser_asset_related(request: web.Request) -> web.Response:
        limit = _bounded_int(request.query.get("limit"), 18, 1, 60)
        related = related_assets(request.match_info["asset_id"], limit=limit)
        if related == {} and not get_asset(request.match_info["asset_id"]):
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response({"id": request.match_info["asset_id"], "related": related})

    @routes.get("/asset-browser/tags")
    async def asset_browser_tags(request: web.Request) -> web.Response:
        return web.json_response({"tags": list_tags()})

    @routes.post("/asset-browser/tags")
    async def asset_browser_create_tag(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "BAD_JSON", "Expected a JSON object.")
        try:
            return web.json_response(create_tag(str(body.get("name") or ""), body.get("color")))
        except ValueError as exc:
            return _json_error(400, "BAD_TAG", str(exc))

    @routes.patch("/asset-browser/tags/{tag_id}")
    async def asset_browser_update_tag(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "BAD_JSON", "Expected a JSON object.")
        tag = update_tag(_bounded_int(request.match_info["tag_id"], -1, -1, 10_000_000), body)
        if not tag:
            return _json_error(404, "NOT_FOUND", "Tag not found.")
        return web.json_response(tag)

    @routes.delete("/asset-browser/tags/{tag_id}")
    async def asset_browser_delete_tag(request: web.Request) -> web.Response:
        deleted = delete_tag(_bounded_int(request.match_info["tag_id"], -1, -1, 10_000_000))
        if not deleted:
            return _json_error(404, "NOT_FOUND", "Tag not found.")
        return web.json_response({"deleted": True})

    @routes.post("/asset-browser/assets/{asset_id}/tags/{tag}")
    async def asset_browser_add_asset_tag(request: web.Request) -> web.Response:
        asset = add_asset_tag(request.match_info["asset_id"], request.match_info["tag"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.delete("/asset-browser/assets/{asset_id}/tags/{tag}")
    async def asset_browser_remove_asset_tag(request: web.Request) -> web.Response:
        asset = remove_asset_tag(request.match_info["asset_id"], request.match_info["tag"])
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.get("/asset-browser/collections")
    async def asset_browser_collections(request: web.Request) -> web.Response:
        return web.json_response({"collections": list_collections()})

    @routes.post("/asset-browser/collections")
    async def asset_browser_create_collection(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "BAD_JSON", "Expected a JSON object.")
        try:
            return web.json_response(create_collection(str(body.get("name") or ""), body.get("description")))
        except ValueError as exc:
            return _json_error(400, "BAD_COLLECTION", str(exc))

    @routes.patch("/asset-browser/collections/{collection_id}")
    async def asset_browser_update_collection(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "BAD_JSON", "Expected a JSON object.")
        collection = update_collection(_bounded_int(request.match_info["collection_id"], -1, -1, 10_000_000), body)
        if not collection:
            return _json_error(404, "NOT_FOUND", "Collection not found.")
        return web.json_response(collection)

    @routes.delete("/asset-browser/collections/{collection_id}")
    async def asset_browser_delete_collection(request: web.Request) -> web.Response:
        deleted = delete_collection(_bounded_int(request.match_info["collection_id"], -1, -1, 10_000_000))
        if not deleted:
            return _json_error(404, "NOT_FOUND", "Collection not found.")
        return web.json_response({"deleted": True})

    @routes.post("/asset-browser/collections/{collection_id}/assets/{asset_id}")
    async def asset_browser_add_collection_asset(request: web.Request) -> web.Response:
        asset = add_asset_to_collection(
            _bounded_int(request.match_info["collection_id"], -1, -1, 10_000_000),
            request.match_info["asset_id"],
        )
        if not asset:
            return _json_error(404, "NOT_FOUND", "Asset not found.")
        return web.json_response(asset)

    @routes.delete("/asset-browser/collections/{collection_id}/assets/{asset_id}")
    async def asset_browser_remove_collection_asset(request: web.Request) -> web.Response:
        asset = remove_asset_from_collection(
            _bounded_int(request.match_info["collection_id"], -1, -1, 10_000_000),
            request.match_info["asset_id"],
        )
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


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except ValueError:
        return None


async def _json_body(request: web.Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _json_error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> web.Response:
    return web.json_response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=status,
    )
