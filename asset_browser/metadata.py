from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}


def supported_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def asset_id_for_path(path: str) -> str:
    normalized = os.path.normcase(os.path.abspath(path))
    return hashlib.sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()[:32]


def extract_asset(path: str, output_dir: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    abs_path = os.path.abspath(path)
    stat = os.stat(abs_path)
    rel = os.path.relpath(abs_path, output_dir)
    subfolder = os.path.dirname(rel)
    if subfolder == ".":
        subfolder = ""
    subfolder = subfolder.replace("\\", "/")

    metadata: dict[str, Any] = {}
    prompt = None
    workflow = None
    width = None
    height = None
    image_format = Path(abs_path).suffix.lower().lstrip(".")
    scan_error = None

    try:
        with Image.open(abs_path) as img:
            width, height = img.size
            image_format = (img.format or image_format).lower()
            metadata = _image_metadata(img)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        scan_error = str(exc)

    prompt = _load_jsonish(metadata.get("prompt"))
    workflow = _load_jsonish(metadata.get("workflow"))
    fields = extract_generation_fields(prompt, workflow, metadata)
    workflow_hash = stable_hash(workflow) if workflow is not None else None

    asset = {
        "id": asset_id_for_path(abs_path),
        "path": abs_path,
        "filename": os.path.basename(abs_path),
        "subfolder": subfolder,
        "type": "output",
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": getattr(stat, "st_birthtime_ns", stat.st_ctime_ns),
        "width": width,
        "height": height,
        "format": image_format,
        "has_prompt": 1 if prompt is not None else 0,
        "has_workflow": 1 if workflow is not None else 0,
        "prompt_json": _json_dump(prompt),
        "workflow_json": _json_dump(workflow),
        "metadata_json": _json_dump(metadata) or "{}",
        "workflow_hash": workflow_hash,
        "lora_names": _json_dump(fields.get("lora_names") or []),
        "model_name": fields.get("model_name"),
        "sampler_name": fields.get("sampler_name"),
        "steps": _int_or_none(fields.get("steps")),
        "cfg": _float_or_none(fields.get("cfg")),
        "seed": _string_or_none(fields.get("seed")),
        "duration_sec": _float_or_none(fields.get("duration_sec")),
        "scan_error": scan_error,
        "updated_at": time.time(),
    }
    return asset, flatten_metadata(asset["id"], metadata, fields)


def _image_metadata(img: Image.Image) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in (img.info or {}).items():
        if key in {"icc_profile", "exif", "XML:com.adobe.xmp"}:
            continue
        metadata[str(key)] = _safe_value(value)
    if hasattr(img, "text"):
        for key, value in getattr(img, "text", {}).items():
            metadata[str(key)] = _safe_value(value)
    return metadata


def _safe_value(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return f"<{len(value)} bytes>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _load_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _json_dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def extract_generation_fields(prompt: Any, workflow: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {"lora_names": []}
    for source in (prompt, workflow, metadata):
        _walk_for_fields(source, fields)
    return fields


def _walk_for_fields(value: Any, fields: dict[str, Any]) -> None:
    if isinstance(value, dict):
        class_type = value.get("class_type") or value.get("type")
        inputs = value.get("inputs") if isinstance(value.get("inputs"), dict) else value
        if isinstance(inputs, dict):
            if not fields.get("model_name"):
                for key in ("ckpt_name", "model_name", "unet_name", "vae_name"):
                    if inputs.get(key):
                        fields["model_name"] = str(inputs[key])
                        break
            if not fields.get("sampler_name") and inputs.get("sampler_name"):
                fields["sampler_name"] = _string_or_none(inputs.get("sampler_name"))
            if inputs.get("lora_name"):
                lora_name = str(inputs["lora_name"])
                if lora_name not in fields["lora_names"]:
                    fields["lora_names"].append(lora_name)
            for key in ("steps", "cfg", "seed"):
                if fields.get(key) is None and inputs.get(key) is not None:
                    fields[key] = inputs.get(key) if not isinstance(inputs.get(key), list) else None
            if class_type and "KSampler" in str(class_type):
                for key in ("steps", "cfg", "seed", "sampler_name"):
                    if fields.get(key) is None and inputs.get(key) is not None:
                        fields[key] = inputs.get(key) if not isinstance(inputs.get(key), list) else None
        for child in value.values():
            _walk_for_fields(child, fields)
    elif isinstance(value, list):
        for child in value:
            _walk_for_fields(child, fields)


def stable_hash(value: Any) -> str:
    normalized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()[:32]


def flatten_metadata(asset_id: str, metadata: dict[str, Any], fields: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal_by_key: dict[str, int] = {}

    def add(key: str, val: Any) -> None:
        if val is None:
            return
        ordinal = ordinal_by_key.get(key, 0)
        ordinal_by_key[key] = ordinal + 1
        row = {
            "asset_id": asset_id,
            "key": key,
            "value_text": None,
            "value_num": None,
            "value_bool": None,
            "ordinal": ordinal,
        }
        if isinstance(val, bool):
            row["value_bool"] = 1 if val else 0
        elif isinstance(val, (int, float)):
            row["value_num"] = float(val)
            row["value_text"] = str(val)
        elif isinstance(val, str):
            row["value_text"] = val[:2048]
        else:
            row["value_text"] = json.dumps(val, ensure_ascii=False, default=str)[:2048]
        rows.append(row)

    for key, value in metadata.items():
        add(key, value)
    for key, value in fields.items():
        add(key, value)
    return rows


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
