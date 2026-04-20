#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create a playback-first sheet image by keeping detected staff bands and whitening everything else."
    )
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--min-width", type=int, default=2500, help="Upscale if the input width is below this value.")
    p.add_argument("--dark-threshold", type=int, default=180, help="Pixels darker than this are treated as ink.")
    p.add_argument(
        "--run-threshold",
        type=float,
        default=0.45,
        help="Minimum longest dark-run fraction in a row to count as a staff-core row.",
    )
    p.add_argument("--merge-gap", type=int, default=80, help="Merge adjacent staff-core rows separated by at most this many pixels.")
    p.add_argument(
        "--pad-top-ratio",
        type=float,
        default=0.16,
        help="Extra space above each detected staff-core band as a multiple of the core-band height.",
    )
    p.add_argument(
        "--pad-bottom-ratio",
        type=float,
        default=0.48,
        help="Extra space below each detected staff-core band as a multiple of the core-band height.",
    )
    return p.parse_args()


def merge_rows(rows: np.ndarray, gap: int) -> list[tuple[int, int]]:
    if rows.size == 0:
        return []
    bands: list[tuple[int, int]] = []
    start = prev = int(rows[0])
    for row in rows[1:]:
        row = int(row)
        if row - prev <= gap:
            prev = row
            continue
        bands.append((start, prev))
        start = prev = row
    bands.append((start, prev))
    return bands


def merge_bands(bands: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not bands:
        return []
    merged = [bands[0]]
    for start, end in bands[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def main() -> None:
    args = parse_args()
    src = Image.open(args.input).convert("RGBA")

    if src.width < args.min_width:
        scale = args.min_width / src.width
        new_size = (int(round(src.width * scale)), int(round(src.height * scale)))
        src = src.resize(new_size, Image.Resampling.LANCZOS)

    # Flatten transparency against white, then detect dark staff rows.
    white = Image.new("RGBA", src.size, (255, 255, 255, 255))
    src = Image.alpha_composite(white, src)
    gray = np.array(src.convert("L"))
    dark = gray < args.dark_threshold

    # Staff lines create very long horizontal dark runs; titles and chord names usually do not.
    run_threshold = int(round(src.width * args.run_threshold))
    core_rows = []
    for y in range(src.height):
        row = dark[y]
        best = cur = 0
        for value in row:
            if value:
                cur += 1
                if cur > best:
                    best = cur
            else:
                cur = 0
        if best >= run_threshold:
            core_rows.append(y)
    core_rows = np.array(core_rows, dtype=int)
    core_bands = merge_rows(core_rows, args.merge_gap)

    expanded: list[tuple[int, int]] = []
    for start, end in core_bands:
        core_height = max(1, end - start + 1)
        pad_top = int(round(core_height * args.pad_top_ratio))
        pad_bottom = int(round(core_height * args.pad_bottom_ratio))
        y0 = max(0, start - pad_top)
        y1 = min(src.height, end + pad_bottom)
        expanded.append((y0, y1))
    bands = merge_bands(expanded)

    out = Image.new("RGBA", src.size, (255, 255, 255, 255))
    for y0, y1 in bands:
        out.paste(src.crop((0, y0, src.width, y1)), (0, y0))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output)
    print(f"input_size={src.width}x{src.height}")
    print(f"bands={bands}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
