"""ComfyUI Asset Browser custom node extension."""

from .asset_browser.routes import register_routes
from .asset_browser.scanner import start_background_scan_once

WEB_DIRECTORY = "./js"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

register_routes()
start_background_scan_once(delay_seconds=8.0)

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
