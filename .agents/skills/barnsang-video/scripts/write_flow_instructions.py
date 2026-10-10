"""Format a reviewed storyboard as a Flow handoff with explicit image mappings."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, load_project


def format_instructions(story, config, selected=None):
    for field in ("title", "context", "style", "video_model", "aspect_ratio"):
        if not isinstance(story.get(field), str) or not story[field].strip():
            raise ValueError(f"Storyboard needs nonempty {field}")
    rules = story.get("rules", [])
    if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
        raise ValueError("rules must be a list of strings")
    images = {}
    for item in story["images"]:
        key = str(item["id"])
        if key in images:
            raise ValueError(f"Duplicate image id: {key}")
        path = data_path(config, item["file"], must_exist=True)
        if not item.get("description", "").strip():
            raise ValueError(f"Image {key} needs a description")
        images[key] = (path.name, item["description"])
    if len({image[0] for image in images.values()}) != len(images):
        raise ValueError("Flow image filenames must be unique")
    clips = story["clips"]
    if not clips or len({str(clip["id"]) for clip in clips}) != len(clips):
        raise ValueError("Provide clips with unique ids")
    for index, clip in enumerate(clips):
        if not isinstance(clip.get("scene_break_after", False), bool):
            raise ValueError("scene_break_after must be a boolean")
        if str(clip["start_image"]) not in images or (
                clip.get("end_image") is not None and str(clip["end_image"]) not in images):
            raise ValueError(f"Unknown image in clip {clip['id']}")
        duration = float(clip["duration_s"])
        if not math.isfinite(duration) or duration <= 0 or not clip.get("action", "").strip():
            raise ValueError("Every clip needs a positive duration and an action")
        if index < len(clips) - 1 and not clip.get("scene_break_after", False):
            if clip.get("end_image") is None or str(clip["end_image"]) != str(clips[index + 1]["start_image"]):
                raise ValueError(f"Clip {clip['id']} must end on the next start image or declare a scene break")
    if selected is not None:
        missing = set(selected) - {str(clip["id"]) for clip in clips}
        if missing:
            raise ValueError(f"Unknown selected clips: {sorted(missing)}")
        clips = [clip for clip in clips if str(clip["id"]) in selected]
    out = [f"{story['title']}: make {len(clips)} separate clips.", "",
        "1. IMAGE MAPPING",
        "Identify each image by filename AND description. If they disagree, stop and resolve the mapping.",
        "Before generation, list each clip's START and END files for review.",
        "Use only the listed images. Name each result using its clip id and START filename.", "",
        "2. CONTINUITY",
        "Use START as the first frame and END as the last frame where supplied.",
        "Keep character identity, clothing, locations, lighting and props consistent.",
        "Move naturally between the frames. No morphing or transition effects.",
        "Only declared scene breaks allow a discontinuous join; otherwise END equals the next START.", "",
        "3. IMAGES"]
    out.extend(f"{name} = {description}" for name, description in images.values())
    out.extend(["", "4. CLIPS"])
    for clip in clips:
        start = images[str(clip["start_image"])][0]
        end = images[str(clip["end_image"])][0] if clip.get("end_image") is not None else "none; end calmly"
        out.extend([f"CLIP {clip['id']}: START {start} -> END {end} | {clip['duration_s']} seconds",
                    f"Action: {clip['action']}"])
        if clip.get("scene_break_after"):
            out.append("A planned scene change or time jump follows this clip.")
    out.extend(["", "5. RULES", f"Model: {story['video_model']}; aspect ratio: {story['aspect_ratio']}.",
        f"Style: {story['style']}", "One continuous shot per clip, no internal cuts.",
        "No speaking or singing mouth movement; no text on screen. Music is added afterwards."])
    out.extend(rules)
    out.extend(["", "6. CONTEXT", story["context"]])
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    add_config_argument(p)
    p.add_argument("--storyboard", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--clips", nargs="+", help="Optional clip ids to regenerate")
    args = p.parse_args(argv)
    config = load_project(args.config_root)
    source = data_path(config, args.storyboard, must_exist=True)
    output = data_path(config, args.output)
    if output.exists():
        raise ValueError("Instructions output already exists; choose a new output")
    story = json.loads(source.read_text(encoding="utf-8-sig"))
    text = format_instructions(story, config, args.clips)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(text)
    print(output)


if __name__ == "__main__":
    main()
