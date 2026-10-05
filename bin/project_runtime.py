"""Shared configuration and explicit path/tool resolution for project skills.

This is not an artifact ledger. Helpers validate without creating directories,
running tools or loading external libraries.
"""

import argparse
from pathlib import Path
import shutil

from bin.read_config import ROOT, load_config


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-root", type=Path,
        help="Directory containing config.toml and optional config.local.toml (default: repository)",
    )


def load_project(config_root: Path | None = None) -> dict:
    return load_config(ROOT if config_root is None else config_root)


def data_path(config: dict, value: str | Path, *, must_exist: bool = False,
              directory: bool = False) -> Path:
    """Resolve a project input/output beneath data_root, including symlink checks."""
    root = Path(config["paths"]["data_root"]).resolve(strict=True)
    if root.is_relative_to(ROOT) or ROOT.is_relative_to(root):
        raise ValueError("paths.data_root must be separate from the repository; "
                         "see docs/configuration.md")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Project path must be inside paths.data_root: {value}")
    if not directory and path == root:
        raise ValueError("A file path is required, not the data root")
    if must_exist and not (path.is_dir() if directory else path.is_file()):
        kind = "directory" if directory else "file"
        raise ValueError(f"Missing input {kind}: {path}")
    if path.exists() and not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Wrong path type: {path}")
    # Catch an existing file used as an output directory ancestor before work starts.
    for parent in path.parents:
        if parent.exists():
            if not parent.is_dir():
                raise ValueError(f"Output ancestor is not a directory: {parent}")
            break
    return path


def tool_command(config: dict, name: str) -> list[str]:
    """Get an explicitly configured argv prefix; never interpret shell strings."""
    section = config.get("tools", {}).get(name, {})
    command = section.get("command") if isinstance(section, dict) else None
    if (not isinstance(command, list) or not command
            or not all(isinstance(part, str) and part.strip() for part in command)):
        raise ValueError(f"Set tools.{name}.command to an argument list in config.local.toml")
    executable = shutil.which(command[0])
    if executable is None:
        raise ValueError(f"Configured tool is unavailable: tools.{name}.command ({command[0]})")
    return [executable, *command[1:]]


def resource_path(config: dict, name: str, *, directory: bool = False) -> Path:
    """Resolve external tools, libraries, model data or other configured resources."""
    value = config.get("resources", {}).get(name)
    if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
        raise ValueError(f"Set resources.{name} to an absolute path in config.local.toml")
    path = Path(value).resolve()
    if path.is_relative_to(ROOT):
        raise ValueError(f"resources.{name} must be outside the repository; "
                         "see docs/configuration.md")
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Configured resource is unavailable: resources.{name} ({path})")
    return path
