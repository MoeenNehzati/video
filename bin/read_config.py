#!/usr/bin/env python3
"""Load shared and local TOML configuration; print the result as JSON when run."""

from datetime import date, datetime, time
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _merge(shared: dict, local: dict) -> dict:
    for key, value in local.items():
        if isinstance(value, dict) and isinstance(shared.get(key), dict):
            _merge(shared[key], value)
        else:
            shared[key] = value
    return shared


def load_config(root: Path = ROOT) -> dict:
    """Read and validate config.toml overlaid by optional config.local.toml.

    Tables merge recursively; other values, including lists, are replaced.
    Files are never changed. Missing or invalid project-data paths raise ValueError.
    """
    root = Path(root)
    config = {}
    for name in ("config.toml", "config.local.toml"):
        path = root / name
        try:
            with path.open("rb") as source:
                _merge(config, tomllib.load(source))
        except FileNotFoundError:
            if name == "config.toml":
                raise
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"{path}: {exc}") from exc

    paths = config.get("paths")
    data_root = paths.get("data_root") if isinstance(paths, dict) else None
    if (not isinstance(data_root, str) or not data_root.strip()
            or not Path(data_root).is_absolute() or not Path(data_root).is_dir()):
        raise ValueError(
            "paths.data_root must be the absolute path of an existing project-data "
            "directory. Set it in config.local.toml."
        )
    return config


def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"Cannot encode {type(value).__name__} as JSON")


def main() -> int:
    try:
        output = json.dumps(load_config(), indent=2, default=_json_default, allow_nan=False)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
