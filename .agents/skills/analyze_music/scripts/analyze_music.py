#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from bin.project_runtime import add_config_argument, data_path, load_project

from music21 import converter

from music_analysis import analyze_score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("arranged_score", type=Path, help="MusicXML/MIDI readable by music21")
    ap.add_argument("--tempo-bpm", type=float, default=None)
    ap.add_argument("--out", type=Path, required=True)
    add_config_argument(ap)
    args = ap.parse_args()
    config = load_project(args.config_root)
    args.arranged_score = data_path(config, args.arranged_score, must_exist=True)
    args.out = data_path(config, args.out)
    if args.out in {args.arranged_score}:
        raise ValueError("Output must not replace an input file")

    score = converter.parse(str(args.arranged_score))
    score_dict, warnings = analyze_score(score, tempo_bpm_override=args.tempo_bpm)

    payload = {"score": score_dict, "warnings": warnings}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
