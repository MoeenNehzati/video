#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def extract_xml_path(path: Path) -> bytes:
    if path.suffix == ".mxl":
        with zipfile.ZipFile(path) as zf:
            name = next(
                n for n in zf.namelist() if n.endswith(".xml") and not n.startswith("META-INF/")
            )
            return zf.read(name)
    return path.read_bytes()


def note_name(note: ET.Element) -> str | None:
    pitch = note.find("pitch")
    if pitch is None:
        return None
    step = pitch.findtext("step")
    alter = pitch.findtext("alter")
    octave = pitch.findtext("octave")
    accidental = ""
    if alter == "1":
        accidental = "#"
    elif alter == "-1":
        accidental = "b"
    return f"{step}{accidental}{octave}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    args = ap.parse_args()

    root = ET.fromstring(extract_xml_path(args.input))
    part = root.find("part")
    if part is None:
        print("missing-part")
        return 2

    by_measure: dict[int, list[str]] = {}
    octave_shifts = 0
    for measure in part.findall("measure"):
        n = int(measure.attrib["number"])
        seq: list[str] = []
        for note in measure.findall("note"):
            nn = note_name(note)
            if nn is not None:
                seq.append(nn)
        by_measure[n] = seq
        octave_shifts += sum(1 for _ in measure.iter("octave-shift"))

    opening = []
    ending = []
    for m in range(1, 5):
        opening.extend(by_measure.get(m, []))
    for m in range(13, 17):
        ending.extend(by_measure.get(m, []))

    matches = sum(1 for a, b in zip(opening, ending) if a == b)
    prefix_len = min(len(opening), len(ending))
    exact = opening == ending

    print(f"octave_shifts={octave_shifts}")
    print(f"opening={' '.join(opening)}")
    print(f"ending={' '.join(ending)}")
    print(f"prefix_match={matches}/{prefix_len}")
    print(f"exact_match={int(exact)}")

    if octave_shifts == 0 and exact:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
