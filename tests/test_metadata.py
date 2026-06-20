import json
import sys
from pathlib import Path

from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asset_browser.metadata import extract_asset, supported_image  # noqa: E402


def test_supported_image_extensions():
    assert supported_image("a.png")
    assert supported_image("a.webp")
    assert supported_image("a.jpg")
    assert not supported_image("a.txt")


def test_extract_png_prompt_and_workflow(tmp_path):
    output = tmp_path / "output"
    nested = output / "nested"
    nested.mkdir(parents=True)
    image_path = nested / "sample.png"

    prompt = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"steps": 24, "cfg": 7.5, "seed": 123, "sampler_name": "euler"}},
    }
    workflow = {"nodes": [{"type": "KSampler"}]}
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("prompt", json.dumps(prompt))
    metadata.add_text("workflow", json.dumps(workflow))

    Image.new("RGB", (16, 12), "red").save(image_path, pnginfo=metadata)

    asset, rows = extract_asset(str(image_path), str(output))

    assert asset["filename"] == "sample.png"
    assert asset["subfolder"] == "nested"
    assert asset["width"] == 16
    assert asset["height"] == 12
    assert asset["has_prompt"] == 1
    assert asset["has_workflow"] == 1
    assert asset["model_name"] == "model.safetensors"
    assert asset["sampler_name"] == "euler"
    assert asset["steps"] == 24
    assert asset["cfg"] == 7.5
    assert asset["seed"] == "123"
    assert any(row["key"] == "prompt" for row in rows)
