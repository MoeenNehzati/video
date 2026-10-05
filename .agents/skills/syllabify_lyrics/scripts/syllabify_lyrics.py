#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from bin.project_runtime import add_config_argument, data_path, load_project

from lyrics_syllabify import syllabify_lyrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("lyrics", type=Path)
    ap.add_argument("--language", default="English")
    ap.add_argument("--out", type=Path, required=True)
    add_config_argument(ap)
    args = ap.parse_args()
    config = load_project(args.config_root)
    args.lyrics = data_path(config, args.lyrics, must_exist=True)
    args.out = data_path(config, args.out)
    if args.out in {args.lyrics}:
        raise ValueError("Output must not replace an input file")

    payload, _warnings = syllabify_lyrics(args.lyrics, args.language)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
