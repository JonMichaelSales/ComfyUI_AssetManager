# ComfyUI Asset Browser

ComfyUI Asset Browser indexes generated output images and adds an Assets panel to the ComfyUI frontend. It is read-only in v1: it does not delete, rename, move, or tag files.

## Features

- Scans the configured ComfyUI output folder for PNG, WebP, JPEG, and JPG files.
- Stores a local SQLite index in `user/ComfyUI-Asset-Browser/assets.sqlite`.
- Shows a left-side Assets browser with search, format filtering, workflow filtering, sorting, thumbnails, and metadata details.
- Reads embedded `prompt` and `workflow` metadata when present.
- Opens embedded workflows from generated images. It attempts a new workflow tab first, then falls back to a confirmed current-canvas replacement when the frontend does not expose a tab API.

## Install

Clone or copy this folder into a ComfyUI custom nodes directory:

```powershell
cd F:\ComfyFiles\custom_nodes
git clone https://github.com/REPLACE-ME/ComfyUI-Asset-Browser
```

Restart ComfyUI. A startup background scan runs once, and the Assets panel also has a manual Scan button.

## API

- `GET /asset-browser/assets`
- `GET /asset-browser/assets/{id}`
- `GET /asset-browser/assets/{id}/metadata`
- `GET /asset-browser/assets/{id}/workflow`
- `POST /asset-browser/scan`
- `GET /asset-browser/scan/status`

ComfyUI also mirrors these routes under `/api/asset-browser/*`.

## Publishing

Before publishing to Comfy Registry:

1. Replace `REPLACE-ME` values in `pyproject.toml`.
2. Add a Registry `PublisherId`.
3. Add the real repository and issue URLs.
4. Optionally add an icon URL.
5. Publish with `comfy node publish`, or use the included GitHub Actions workflow with `COMFY_REGISTRY_ACCESS_TOKEN`.

## Notes

Existing output images only show workflow loading when they contain embedded workflow metadata. Generation duration is reserved in the database schema but is usually unavailable for older images.
