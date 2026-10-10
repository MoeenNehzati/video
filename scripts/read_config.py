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
from uuid import UUID


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
    if "bookkeeping" in config:
        bookkeeping = config["bookkeeping"]
        if (not isinstance(bookkeeping, dict)
                or not isinstance(bookkeeping.get("actor_id"), str)
                or not bookkeeping["actor_id"].strip()):
            raise ValueError("Set bookkeeping.actor_id to a nonempty label in config.local.toml")
        host = bookkeeping.get("host_id")
        try:
            identifier = UUID(host) if isinstance(host, str) else None
        except ValueError:
            identifier = None
        if identifier is None or identifier.version != 4 or str(identifier) != host:
            raise ValueError("Set bookkeeping.host_id to a machine-stable lowercase UUIDv4 "
                             "in config.local.toml")
    if "resource_cache" in paths:
        value = paths["resource_cache"]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("paths.resource_cache must be an absolute path in config.local.toml")
        cache = Path(value).resolve()
        if any(cache.is_relative_to(boundary) or boundary.is_relative_to(cache)
               for boundary in (ROOT, resolved_data)):
            raise ValueError("paths.resource_cache must be separate from the repository and "
                             "paths.data_root; fix config.local.toml")
        if cache.exists() and not cache.is_dir():
            raise ValueError("paths.resource_cache must identify a directory in config.local.toml")
        if any(parent.exists() and not parent.is_dir() for parent in cache.parents):
            raise ValueError("paths.resource_cache has a non-directory ancestor; fix config.local.toml")
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
