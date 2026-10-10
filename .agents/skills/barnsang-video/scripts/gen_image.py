"""Generate one image and its request record using explicit project-data paths."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project


def parser(description: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    add_config_argument(result)
    result.add_argument("--model", required=True)
    result.add_argument("--quality", required=True)
    result.add_argument("--size", required=True)
    result.add_argument("--prompt", required=True, help="UTF-8 prompt file under data_root")
    result.add_argument("--output", required=True, help="New PNG path under data_root")
    return result


def prepare(args):
    raise ValueError('Image generation is disabled: remote request/image bundle support is not implemented')
    config = load_project(args.config_root)
    prompt_path = data_path(config, args.prompt, must_exist=True)
    out = data_path(config, args.output)
    metadata = data_path(config, str(out) + ".json")
    if out.suffix.lower() != ".png":
        raise ValueError("Image output must use .png")
    if out.exists() or metadata.exists():
        raise ValueError("Output image or request record already exists; choose a new output")
    prompt = prompt_path.read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError("Prompt is empty")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is required")
    return config, out, metadata, prompt, key


def save_response(response, out, metadata, record, started):
    if out.resolve() == metadata.resolve() or out.exists() or metadata.exists():
        raise ValueError('Image and request outputs must be distinct new files')
    if out.resolve() in metadata.resolve().parents or metadata.resolve() in out.resolve().parents:
        raise ValueError('Image and request output files cannot contain one another')
    response.raise_for_status()
    result = response.json()
    item = result["data"][0]
    payload = base64.b64decode(item["b64_json"], validate=True)
    if not payload:
        raise ValueError("Image API returned an empty image")
    record.update(seconds=round(time.monotonic() - started, 2),
                  usage=result.get("usage"), revised_prompt=item.get("revised_prompt"),
                  provider_created=result.get("created"), model_revision=None,
                  model_revision_unknown_reason="Provider model internals are not exposed or locally replayable")
    request_id = response.headers.get("x-request-id")
    record["provider_request_id"] = request_id if isinstance(request_id, str) else None
    out.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    with out.open('xb') as stream:
        stream.write(payload)
    with metadata.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(out)


def main(argv=None):
    args = parser(__doc__).parse_args(argv)
    raise ValueError('Image generation is disabled: remote request/image bundle support is not implemented')
    _, out, metadata, prompt, key = prepare(args)
    started = time.monotonic()
    record = {"model": args.model, "quality": args.quality, "size": args.size, "prompt": prompt}
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={**record, "n": 1, "output_format": "png"}, timeout=600)
    save_response(response, out, metadata, record, started)


if __name__ == "__main__":
    main()
