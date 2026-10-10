#!/usr/bin/env python3
"""Read project TOML as JSON, or pass it to a command through its environment."""

import argparse
from datetime import date, datetime, time
import json
import os
from pathlib import Path
import subprocess
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
            "directory. Set it in config.local.toml; see docs/configuration.md."
        )
    resolved_data = Path(data_root).resolve()
    if resolved_data.is_relative_to(ROOT) or ROOT.is_relative_to(resolved_data):
        raise ValueError("paths.data_root must be separate from the repository "
                         "(neither inside it nor containing it). "
                         "Fix config.local.toml; see docs/configuration.md.")
    for table in ("tools", "resources"):
        if table in config and not isinstance(config[table], dict):
            raise ValueError(f"{table} must be a TOML table. "
                             "Fix config.local.toml; see docs/configuration.md.")
    return config


def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"Cannot encode {type(value).__name__} as JSON")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=ROOT,
                        help="Directory containing config.toml and config.local.toml")
    parser.add_argument("--run", nargs=argparse.REMAINDER, metavar="COMMAND",
                        help="Run an argv command with project configuration in its environment")
    args = parser.parse_args(argv)
    if args.run == []:
        parser.error("--run requires a command")
    try:
        root = args.config_root.resolve()
        config = load_config(root)
        output = json.dumps(config, indent=2, default=_json_default, allow_nan=False)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    if args.run is not None:
        environment = os.environ.copy()
        environment.update({
            "MUSIC_VIDEO_CONFIG_ROOT": str(root),
            "MUSIC_VIDEO_DATA_ROOT": str(Path(config["paths"]["data_root"]).resolve()),
            "MUSIC_VIDEO_CONFIG_JSON": json.dumps(
                config, default=_json_default, allow_nan=False, separators=(",", ":")),
        })
        try:
            result = subprocess.run(args.run, env=environment)
        except OSError as exc:
            print(f"Command error: {exc}", file=sys.stderr)
            return 127
        except KeyboardInterrupt:
            return 130
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
