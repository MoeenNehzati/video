"""Validate a song-specific brief and emit an auditable prompt and adapter plan."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project



def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_brief(brief_path, research_path, config):
    b = json.loads(brief_path.read_text(encoding="utf-8-sig"))
    r = json.loads(research_path.read_text(encoding="utf-8-sig"))
    require(b["song_id"] == r["song_id"], "Research song does not match brief")
    require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", b["song_id"]), "Unsafe song_id")
    require(b["vocals"] == "user_supplied", "Only user-supplied vocals are supported")
    require(0 <= b["audience"]["age_min"] <= b["audience"]["age_max"] <= 18, "Invalid ages")
    require(b["invariants"] and b["variants"], "Invariants and variants are required")
    ids = {e["id"] for e in r["evidence"]}
    require(len(ids) == len(r["evidence"]), "Duplicate evidence IDs")
    source = data_path(config, b["source_xml"], must_exist=True)
    folder = data_path(config, b["baseline_folder"], must_exist=True, directory=True)
    data_path(config, b["output_root"], directory=True)
    require(sha(source) == b["source_sha256"], "Source hash changed")
    cfg = json.loads((folder / "parameters.json").read_text(encoding="utf-8"))
    require(Path(cfg["filename"]).name == cfg["filename"] and "/" not in cfg["filename"] and "\\" not in cfg["filename"], "Unsafe baseline filename")
    midi = data_path(config, folder / (cfg["filename"] + ".mid"), must_exist=True)
    require(cfg["stem"] == b["song_id"], "Baseline song differs")
    require(sha(midi) == b["baseline_midi_sha256"], "Baseline MIDI hash changed")
    num, den = map(int, cfg["meter"].split("/"))
    require(num > 0 and den > 0 and den & (den - 1) == 0 and cfg["bars"] > 0, "Invalid meter or bars")
    length = cfg["bars"] * num * 4 / den
    seen = set()
    for v in b["variants"]:
        require(re.fullmatch(r"[0-9]{2}_[a-z0-9_]+", v["id"]) and v["id"] not in seen, "Invalid or duplicate variant ID")
        seen.add(v["id"])
        require(v["axis"] and v["label"] and v["rationale"], "Variant needs axis, label and rationale")
        require(v["evidence_ids"] and set(v["evidence_ids"]) <= ids, "Unknown evidence")
        require(v["baseline_percussion"] in ("preserve", "replace"), "Unsupported percussion operation")
        for pitch, beat, duration, velocity in v["events"]:
            require(type(pitch) is int and 0 <= pitch <= 127 and type(velocity) is int and 1 <= velocity <= 127, "Invalid MIDI pitch/velocity")
            require(all(math.isfinite(x) for x in (beat, duration)) and beat >= 0 and duration > 0 and beat + duration <= length + .001, "Event outside song")
        for start, end in v["participation_windows"]:
            require(0 <= start < end <= length, "Participation window outside song")
    return {**b, "research_file": str(research_path.resolve()), "research_sha256": sha(research_path),
            "adapter": "barnsang_percussion_v1", "song_length_beats": length}


def compile_brief(brief_path, research_path, out, config):
    plan = validate_brief(brief_path, research_path, config)
    out = data_path(config, out, directory=True)
    require(not out.exists() or not any(out.iterdir()), "Use an empty output directory")
    lines = ["# Codex arrangement instruction", f"Arrange {plan['song_id']} for ages {plan['audience']['age_min']}-{plan['audience']['age_max']} ({plan['audience']['context']}).",
             "User supplies vocals; create no vocals. Deliver guide preview and aligned backing-only exports.", f"Baseline MIDI SHA256: {plan['baseline_midi_sha256']} (path in execution_plan.json)", "## Preserve"]
    lines.extend("- " + x for x in plan["invariants"])
    for v in plan["variants"]:
        lines += [f"## {v['id']}: {v['label']}", f"Change only: {v['axis']}. {v['rationale']}",
                  f"Evidence: {', '.join(v['evidence_ids'])}. Baseline percussion: {v['baseline_percussion']}.",
                  f"Execute {len(v['events'])} exact events; optional participation windows: {v['participation_windows']}."]
    lines += ["## Execution", "Use the supported JJazzLab adapter for native projects and freeze exact baseline MIDI. Verify source hashes, note-level changes, sample coverage, note pairing, loudness/peaks, aligned backing and listening-page playback. Record unsupported operations and pending listening reviews."]
    out.mkdir(parents=True, exist_ok=True)
    (out / "execution_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "PROMPT.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("brief")
    parser.add_argument("research")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    config = load_project(args.config_root)
    compile_brief(data_path(config, args.brief, must_exist=True),
                  data_path(config, args.research, must_exist=True), args.out, config)
    print("Wrote PROMPT.md and execution_plan.json")


if __name__ == "__main__":
    main()
