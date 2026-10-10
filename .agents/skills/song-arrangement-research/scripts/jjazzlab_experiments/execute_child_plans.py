"""Build native projects and exact baseline-preserving percussion variants."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project, resource_path, tool_command

from verification import component, load_auditor, require, sha, verify, check_frozen_messages, check_child_events, check_backing


def compiler_module():
    path = HERE.parents[1] / "scripts" / "compile_brief.py"
    spec = importlib.util.spec_from_file_location("arrangement_brief", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def timed_events(track):
    at = 0
    for message in track:
        at += message.time
        yield at, message


def save_events(track, events, end, mido):
    events.sort(key=lambda item: item[0])
    track.clear()
    at = 0
    for tick, message in events:
        track.append(message.copy(time=tick - at))
        at = tick
    track.append(mido.MetaMessage("end_of_track", time=max(0, end - at)))


def frozen_midis(baseline_midi, operation):
    """Retain all original non-percussion events, including expression/tempo."""
    import mido
    source = mido.MidiFile(baseline_midi)
    end = max(sum(message.time for message in track) for track in source.tracks)
    for track in source.tracks:
        events = [(at, msg) for at, msg in timed_events(track) if msg.type != "end_of_track" and not (
            operation["baseline_percussion"] == "replace" and msg.type in ("note_on", "note_off") and msg.channel == 9)]
        save_events(track, events, end, mido)
    track = mido.MidiTrack()
    events = [(0, mido.MetaMessage("track_name", name="Child percussion additions"))]
    for pitch, beat, duration, velocity in operation["events"]:
        events += [(round(beat * source.ticks_per_beat), mido.Message("note_on", channel=9, note=pitch, velocity=velocity)),
                   (round((beat + duration) * source.ticks_per_beat), mido.Message("note_off", channel=9, note=pitch, velocity=0))]
    save_events(track, events, end, mido)
    source.tracks.append(track)
    backing = mido.MidiFile(type=1, ticks_per_beat=source.ticks_per_beat)
    guide = [track for track in source.tracks if any(msg.type == "track_name" and "Original melody" in msg.name for msg in track)]
    require(len(guide) == 1, "Baseline must have exactly one Original melody track")
    backing.tracks = [track.copy() for track in source.tracks if track is not guide[0]]
    return source, backing


def compile_java(config, build, runtime, manifest):
    jar = resource_path(config, "jjazzlab_toolkit")
    command = runtime["javac"]
    subprocess.run([*command, "-proc:full", "-cp", str(jar), "-d", str(build), str(HERE / "ChildExperiment.java")], check=True, env=runtime["environment"], cwd=build)
    require((build / "ChildExperiment.class").is_file(), "Java compiler produced no ChildExperiment.class")
    return os.pathsep.join((str(build), str(jar)))


def execute(paths, manifest, config, *, runtime=None, output_root=None):
    require(runtime is not None, "JJazz execution requires explicit tools and scratch directory")
    auditor = load_auditor(config)
    java = runtime["java"]
    resource_path(config, "jjazzlab_toolkit")
    rhythms = resource_path(config, "jjazzlab_rhythms", directory=True)
    module = compiler_module()
    jobs = []
    destinations = set()
    for planpath in paths:
        stored = json.loads(planpath.read_text(encoding="utf-8"))
        require(stored["adapter"] == "barnsang_percussion_v1", "Unsupported adapter")
        research = data_path(config, stored["research_file"], must_exist=True)
        require(sha(research) == stored["research_sha256"], "Research changed since compilation")
        plan = module.validate_brief(planpath, research, config)
        baseline = data_path(config, plan["baseline_folder"], must_exist=True, directory=True)
        base, _ = verify(baseline, config, auditor)
        component(base["stem"])
        component(base["filename"])
        require(base["source_sha256"] == plan["source_sha256"], "Baseline and brief use different source scores")
        for key in ("title", "style", "variation", "intensity", "room", "counter_library"):
            require(key in base, "Missing baseline parameter: " + key)
        require(isinstance(base.get("percussion_events"), list), "Baseline percussion_events is required")
        for event in base["percussion_events"]:
            require(isinstance(event, list) and len(event) == 4, "Malformed baseline percussion event")
            pitch, beat, duration, velocity = event
            require(type(pitch) is int and 0 <= pitch <= 127 and type(velocity) is int and 1 <= velocity <= 127,
                    "Invalid baseline percussion pitch/velocity")
            require(all(isinstance(value, (int, float)) and math.isfinite(value) for value in (beat, duration))
                    and beat >= 0 and duration > 0 and beat + duration <= plan["song_length_beats"] + .001,
                    "Invalid baseline percussion timing")
        properties = dict(line.split("=", 1) for line in (baseline / "input.properties").read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith(("#", "!")))
        for key in ("title", "tempo", "bars", "variation", "style", "intensity", "ensemble", "lead", "counter_program", "counter_volume"):
            require(key in properties, "Missing baseline input.properties key: " + key)
        required = ["chords.tsv", "melody.tsv", "upper.tsv", "input.properties", "tracks.tsv"]
        if base["ensemble"] in ("trio", "chamber"):
            required.append("bass.tsv")
        if base["ensemble"] == "chamber":
            required.append("strings.tsv")
        for name in required:
            data_path(config, baseline / name, must_exist=True)
        prompt = data_path(config, planpath.parent / "PROMPT.md", must_exist=True)
        root = data_path(config, output_root or plan["output_root"], directory=True)
        for variant in plan["variants"]:
            folder = data_path(config, root / plan["song_id"] / variant["id"], directory=True)
            require(not folder.exists(), f"Output already exists: {folder}; allocate a new version")
            require(folder not in destinations, "Duplicate output directory")
            destinations.add(folder)
            midi, backing = frozen_midis(baseline / (base["filename"] + ".mid"), variant)
            jobs.append((folder, planpath, plan, base, baseline, variant, required, prompt, midi, backing))
    require(jobs, "At least one variant is required")
    require(not manifest.exists(), "Folder manifest already exists")
    require(all(not manifest.is_relative_to(folder) and not folder.is_relative_to(manifest) for folder in destinations), "Manifest must be separate from variant directories")
    build = data_path(config, runtime["build"], directory=True)
    require(not build.exists(), "Scratch directory already exists")
    require(all(not build.is_relative_to(folder) and not folder.is_relative_to(build) for folder in destinations), "Scratch must be separate from variant directories")
    require(not manifest.is_relative_to(build), "Manifest must be separate from scratch")
    build.mkdir(parents=True)
    classpath = compile_java(config, build, runtime, manifest)
    for folder, planpath, plan, base, baseline, variant, required, prompt, midi, backing in jobs:
        cfg = {**base, "id": variant["id"], "filename": base["stem"] + "__" + variant["id"],
               "label": variant["label"], "axis": variant["axis"], "parameters_changed_vs_reference": variant["rationale"],
               "composition_notes": variant["rationale"], "child_plan": str(planpath), "child_plan_sha256": sha(planpath),
               "baseline_folder": str(baseline), "baseline_filename": base["filename"],
               "baseline_midi_sha256": plan["baseline_midi_sha256"], "audience": plan["audience"],
               "variant_operations": variant, "vocals": "user_supplied"}
        folder.mkdir(parents=True)
        (folder / "parameters.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        for name in required:
            if name != "input.properties":
                shutil.copy2(baseline / name, folder / name)
        events = (base["percussion_events"] if variant["baseline_percussion"] == "preserve" else []) + variant["events"]
        (folder / "triangle.tsv").write_text("".join(f"{p}\t{t}\t{d}\t{v}\n" for p, t, d, v in events), encoding="utf-8")
        lines = [line for line in (baseline / "input.properties").read_text(encoding="utf-8").splitlines() if not line.startswith(("filename=", "percussion_name=", "replace_beat=", "xml="))]
        lines += ["filename=" + cfg["filename"], "percussion_name=Child percussion", "replace_beat=" + str(variant["baseline_percussion"] == "replace").lower(), "xml=" + data_path(config, plan["source_xml"], must_exist=True).as_posix()]
        (folder / "input.properties").write_text("\n".join(lines) + "\n", encoding="utf-8")
        shutil.copy2(prompt, folder / "ARRANGEMENT_PROMPT.md")
    subprocess.run([*java, "-Djava.awt.headless=true", "-Djava.util.prefs.userRoot=" + str(build / "preferences"), "-Duser.home=" + str(build / "home"),
                    "-Djava.io.tmpdir=" + str(build),
                    "--add-opens=java.base/java.util=ALL-UNNAMED", "--add-opens=java.base/java.lang=ALL-UNNAMED",
                    "-cp", classpath, "ChildExperiment", str(rhythms), *map(str, sorted(destinations))], check=True, env=runtime["environment"], cwd=build)
    for folder, planpath, plan, base, baseline, variant, required, prompt, midi, backing in jobs:
        cfg = json.loads((folder / "parameters.json").read_text(encoding="utf-8"))
        midi.save(folder / (cfg["filename"] + ".mid"))
        backing.save(folder / (cfg["filename"] + "_backing.mid"))
        check_frozen_messages(folder / (cfg["filename"] + ".mid"), baseline / (base["filename"] + ".mid"))
        actual = auditor.read_midi(folder / (cfg["filename"] + ".mid"))
        reference = auditor.read_midi(baseline / (base["filename"] + ".mid"))
        check_child_events(actual, reference, variant)
        guide = next(track for track in actual["tracks"] if any(kind == 3 and b"Original melody" in bytes.fromhex(value) for tick, kind, value in track["meta"]))
        channels = {note[3] for note in guide["notes"]}
        require(len(channels) == 1, "Guide melody channel is ambiguous")
        check_backing(actual, auditor.read_midi(folder / (cfg["filename"] + "_backing.mid")), next(iter(channels)))
        require((folder / "native_reload_verified.txt").is_file(), "Native project was not reopened")
        shutil.copy2(folder / "tracks.tsv", folder / "native_tracks.tsv")
        shutil.copy2(baseline / "tracks.tsv", folder / "tracks.tsv")
        (folder / "verification.json").write_text(json.dumps({
            "variant": variant["id"],
            "checks": {"native_project_reopened": True, "pitched_events_frozen": True,
                       "backing_guide_removed": True},
            "live_runtime_qualification": "Synthetic tools do not establish real JJazz qualification",
        }, indent=2), encoding="utf-8")
        (folder / "participation.md").write_text("Optional participation; no voices generated.\n" + "\n".join(f"Optional response from beat {start:g} to {end:g}; backing continues." for start, end in variant["participation_windows"]) + "\n", encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps([str(path) for path in sorted(destinations)], indent=2), encoding="utf-8")
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("plans", nargs="+")
    parser.add_argument("--out", required=True, help="New JSON file listing produced variant directories")
    parser.add_argument("--output-root", required=True, help="Root for song/variant output directories")
    parser.add_argument("--scratch", required=True, help="New private compiler and Java preferences directory")
    args = parser.parse_args()
    config = load_project(args.config_root)
    scratch = data_path(config, args.scratch, directory=True)
    require(not scratch.exists(), "Scratch directory already exists")
    paths = [data_path(config, value, must_exist=True) for value in args.plans]
    manifest = data_path(config, args.out)
    runtime = {"java": tool_command(config, "java"), "javac": tool_command(config, "javac"),
               "build": scratch, "environment": dict(os.environ)}
    execute(paths, manifest, config, runtime=runtime, output_root=args.output_root)


if __name__ == "__main__":
    main()
