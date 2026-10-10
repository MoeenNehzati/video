"""Assemble selected Flow clips with uniform speed per verse and aligned music."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project, tool_command


def positive(value, name):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def duration(path, ffprobe):
    result = subprocess.run([*ffprobe, "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True)
    return positive(result.stdout.strip(), f"duration of {path}")


def prepare(settings, clip_map, audio, config, ffprobe):
    source_bpm = positive(settings["source_bpm"], "source_bpm")
    target_bpm = positive(settings["target_bpm"], "target_bpm")
    tempo = target_bpm / source_bpm
    if not .5 <= tempo <= 2:
        raise ValueError("Supported tempo ratio is 0.5 to 2")
    beats = positive(settings["beats_per_bar"], "beats_per_bar")
    bars = positive(settings["verse_bars"], "verse_bars")
    interlude = float(settings["interlude_bars"])
    if not math.isfinite(interlude) or interlude < 0:
        raise ValueError("interlude_bars must be nonnegative")
    groups = settings["verse_groups"]
    if not groups or any(not group for group in groups):
        raise ValueError("Each verse group needs at least one clip")
    keys = [str(key) for group in groups for key in group]
    entries = {str(clip["id"]): clip for clip in clip_map}
    if len(entries) != len(clip_map) or len(set(keys)) != len(keys) or set(entries) != set(keys):
        raise ValueError("Verse groups must use every unique clip exactly once")
    clips = []
    for key in keys:
        entry = entries[key]
        source = data_path(config, entry["file"], must_exist=True)
        available = duration(source, ffprobe)
        length = positive(entry.get("trim_end_s", available), f"trim_end_s of {key}")
        if length > available + .01:
            raise ValueError(f"Clip {key} trim exceeds its duration")
        clips.append({"id": key, "path": source, "source_s": length})
    spacing = (bars + interlude) * beats * 60 / target_bpm
    offsets = [index * spacing for index in range(len(groups))]
    trim = float(settings.get("end_trim_s", 0))
    if not math.isfinite(trim) or trim < 0:
        raise ValueError("end_trim_s must be nonnegative")
    end = offsets[-1] + duration(audio, ffprobe) / tempo - trim
    if end <= offsets[-1]:
        raise ValueError("End trim removes the final verse")
    rows, index, cursor = [], 0, 0.0
    for group_index, group in enumerate(groups):
        members = clips[index:index + len(group)]
        target = spacing if group_index < len(groups) - 1 else end - offsets[group_index]
        speed = sum(clip["source_s"] for clip in members) / target
        for clip in members:
            length = clip["source_s"] / speed
            rows.append({**clip, "speed": speed, "start_s": cursor, "end_s": cursor + length})
            cursor += length
        index += len(group)
    return {"tempo": tempo, "duration_s": end, "verse_starts_s": offsets, "clips": rows}


def render(plan, settings, audio, output, output_audio, ffmpeg):
    end = plan["duration_s"]
    fade_audio = float(settings.get("audio_fade_s", 2))
    fade_in = float(settings.get("video_fade_in_s", .6))
    fade_out = float(settings.get("video_fade_out_s", 1.2))
    for name, value in [("audio_fade_s", fade_audio), ("video_fade_in_s", fade_in), ("video_fade_out_s", fade_out)]:
        if not math.isfinite(value) or not 0 <= value <= end:
            raise ValueError(f"{name} must lie between zero and the film duration")
    width, height, fps = (int(settings[key]) for key in ("width", "height", "fps"))
    if min(width, height, fps) <= 0 or width % 2 or height % 2:
        raise ValueError("Video dimensions must be positive even integers, and fps positive")
    crf = int(settings.get("crf", 16))
    if not 0 <= crf <= 51:
        raise ValueError("crf must be between 0 and 51")
    preset = settings.get("preset", "slow")
    if preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
        raise ValueError("Unsupported encoding preset")
    # All semantic checks precede directory creation and media writes.
    for path in (output, output_audio):
        path.parent.mkdir(parents=True, exist_ok=True)
    audio_inputs, filters = [], []
    for index, offset in enumerate(plan["verse_starts_s"]):
        audio_inputs.extend(["-i", str(audio)])
        filters.append(f"[{index}:a]atempo={plan['tempo']},adelay={round(offset * 1000)}:all=1[a{index}]")
    labels = "".join(f"[a{index}]" for index in range(len(plan["verse_starts_s"])))
    filters.append(labels + f"amix=inputs={len(plan['verse_starts_s'])}:duration=longest:normalize=0,atrim=0:{end}"
                   + (f",afade=t=out:st={end-fade_audio}:d={fade_audio}" if fade_audio else "") + "[a]")
    subprocess.run([*ffmpeg, "-n", "-v", "error", *audio_inputs, "-filter_complex", ";".join(filters),
                    "-map", "[a]", "-c:a", "pcm_s24le", "-ar", "48000", str(output_audio)], check=True)
    inputs, filters = [], []
    for index, clip in enumerate(plan["clips"]):
        inputs.extend(["-t", str(clip["source_s"]), "-i", str(clip["path"])])
        filters.append(f"[{index}:v]setpts=(PTS-STARTPTS)/{clip['speed']:.12g},"
                       f"scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p,setsar=1[v{index}]")
    labels = "".join(f"[v{index}]" for index in range(len(plan["clips"])))
    filters.append(labels + f"concat=n={len(plan['clips'])}:v=1:a=0,trim=0:{end}"
                   + (f",fade=t=in:st=0:d={fade_in}" if fade_in else "")
                   + (f",fade=t=out:st={end-fade_out}:d={fade_out}" if fade_out else "") + "[v]")
    subprocess.run([*ffmpeg, "-n", "-v", "error", *inputs, "-i", str(output_audio),
        "-filter_complex", ";".join(filters), "-map", "[v]", "-map", f"{len(plan['clips'])}:a",
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-c:a", "aac", "-b:a", "256k",
        "-shortest", "-movflags", "+faststart", str(output)], check=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    add_config_argument(p)
    for name in ("song-config", "clips", "audio", "output", "output-audio", "timeline"):
        p.add_argument("--" + name, required=True)
    args = p.parse_args(argv)
    config = load_project(args.config_root)
    ffmpeg, ffprobe = tool_command(config, "ffmpeg"), tool_command(config, "ffprobe")
    source = data_path(config, args.song_config, must_exist=True)
    clip_file = data_path(config, args.clips, must_exist=True)
    audio = data_path(config, args.audio, must_exist=True)
    outputs = [data_path(config, value) for value in (args.output, args.output_audio, args.timeline)]
    if len(set(outputs)) != 3 or any(path.exists() for path in outputs):
        raise ValueError("Provide three distinct, new output paths")
    if outputs[0].suffix.lower() != ".mp4" or outputs[1].suffix.lower() != ".wav" or outputs[2].suffix.lower() != ".json":
        raise ValueError("Outputs must be MP4, WAV and timeline JSON respectively")
    settings = json.loads(source.read_text(encoding="utf-8-sig"))
    clips = json.loads(clip_file.read_text(encoding="utf-8-sig"))
    plan = prepare(settings, clips, audio, config, ffprobe)
    render(plan, settings, audio, outputs[0], outputs[1], ffmpeg)
    for path in outputs[:2]:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"External tool did not create a nonempty output: {path}")
    timeline = {**plan, "source_bpm": settings["source_bpm"], "target_bpm": settings["target_bpm"],
                "audio": str(audio), "film": str(outputs[0]), "prepared_audio": str(outputs[1]),
                "settings": settings}
    timeline["clips"] = [{**clip, "path": str(clip["path"])} for clip in plan["clips"]]
    outputs[2].parent.mkdir(parents=True, exist_ok=True)
    outputs[2].write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")
    print(outputs[0])


if __name__ == "__main__":
    main()
