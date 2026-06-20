# ComfyUI Asset Browser

ComfyUI Asset Browser indexes generated output images and adds an Assets panel to the ComfyUI frontend. V2 turns the browser into a non-destructive curated library: it can favorite, rate, tag, annotate, archive, and collect assets without deleting, renaming, moving, or editing generated files.

## Features

- Scans the configured ComfyUI output folder for PNG, WebP, JPEG, and JPG files.
- Stores a local SQLite index in `user/ComfyUI-Asset-Browser/assets.sqlite`.
- Shows a left-side Assets browser with search, curation filters, format/model/LoRA/workflow filters, sorting, thumbnails, and metadata details.
- Adds favorites, ratings, notes, archived/hidden assets, tags, collections, selection, and bulk favorite/archive/tag actions.
- Reads embedded `prompt` and `workflow` metadata when present.
- Opens embedded workflows from generated images. It attempts a new workflow tab first, then falls back to a confirmed current-canvas replacement when the frontend does not expose a tab API.
- Optionally links to ComfyUI Performance Tracker when installed, showing linked run duration, cache ratio, status, node counts, and friendly model names.

## Install

Clone or copy this folder into a ComfyUI custom nodes directory:

```powershell
cd F:\ComfyFiles\custom_nodes
git clone https://github.com/JonMichaelSales/ComfyUI_AssetManager
```

Restart ComfyUI. A startup background scan runs once, and the Assets panel also has a manual Scan button.

## API

- `GET /asset-browser/assets`
- `GET /asset-browser/assets/{id}`
- `GET /asset-browser/assets/{id}/metadata`
- `GET /asset-browser/assets/{id}/workflow`
- `PATCH /asset-browser/assets/{id}/annotation`
- `GET /asset-browser/assets/{id}/related`
- `GET/POST/PATCH/DELETE /asset-browser/tags`
- `POST/DELETE /asset-browser/assets/{id}/tags/{tag}`
- `GET/POST/PATCH/DELETE /asset-browser/collections`
- `POST/DELETE /asset-browser/collections/{id}/assets/{asset_id}`
- `POST /asset-browser/scan`
- `GET /asset-browser/scan/status`

ComfyUI also mirrors these routes under `/api/asset-browser/*`.

## Publishing

Before publishing to Comfy Registry:

1. Confirm `PublisherId` and `Icon` values in `pyproject.toml`.
2. Add a Registry `PublisherId`.
3. Add the real repository and issue URLs.
4. Optionally add an icon URL.
5. Publish with `comfy node publish`, or use the included GitHub Actions workflow with `COMFY_REGISTRY_ACCESS_TOKEN`.

## Notes

- Existing output images only show workflow loading when they contain embedded workflow metadata.
- Generation duration is enriched from Performance Tracker when a recorded run output matches by filename, subfolder, and type.
- Archived assets are hidden from the default view but remain indexed and can be shown with the archive filter.

