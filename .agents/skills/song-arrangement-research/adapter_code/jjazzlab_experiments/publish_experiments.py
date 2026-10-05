"""Publish explicit render reports as a local A/B listening page and catalogue."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from bin.project_runtime import add_config_argument, data_path, load_project
from verification import component, require
from check_delivery import check_files


def publish(report_paths, out, config):
    require(not out.exists(), "Listening output already exists; allocate a new version")
    reports = [row for path in report_paths for row in json.loads(path.read_text(encoding="utf-8"))]
    require(reports, "Empty render reports")
    check_files(reports, config)
    songs, catalogue, logs = {}, [], []
    seen = set()
    for result in reports:
        folder = data_path(config, result["folder"], must_exist=True, directory=True)
        arrangement = data_path(config, result["arrangement_folder"], must_exist=True, directory=True)
        cfg = json.loads((arrangement / "parameters.json").read_text(encoding="utf-8"))
        component(cfg["stem"])
        component(cfg["id"])
        component(cfg["filename"])
        require(cfg["filename"] == result["filename"], "Render and arrangement filenames differ")
        identity = (cfg["stem"], cfg["id"])
        require(identity not in seen, "Repeated song/version; publish each render comparison separately")
        seen.add(identity)
        relative_link = lambda path: quote(Path(os.path.relpath(path, out)).as_posix(), safe="/")
        files = {ext: relative_link(folder / (cfg["filename"] + "." + ext)) for ext in ("mp3", "wav")}
        files.update({ext: relative_link(arrangement / (cfg["filename"] + "." + ext)) for ext in ("mid", "sng", "mix")})
        for ext in ("wav", "mp3", "mid"):
            parent = arrangement if ext == "mid" else folder
            files["backing_" + ext] = relative_link(parent / (cfg["filename"] + "_backing." + ext))
        files["prompt"] = relative_link(arrangement / "ARRANGEMENT_PROMPT.md")
        files["participation"] = relative_link(arrangement / "participation.md")
        files["credits"] = relative_link(folder / "CREDITS.md")
        log = data_path(config, out / cfg["stem"] / (cfg["id"] + ".md"))
        require(log.is_relative_to(out), "Unsafe parameter-log path")
        files["log"] = relative_link(log)
        libraries = sorted({result["libraries"][route["library"]]["credits"] for route in result["routes"].values()})
        lines = [f"# {cfg['title']} — {cfg['label']}", "", cfg["composition_notes"], "",
                 *[f"- {key}: {cfg[key]}" for key in ("axis", "tempo", "meter", "style", "variation", "intensity", "ensemble", "room")],
                 f"- Loudness: {result['final_lufs']} LUFS; true peak: {result['final_true_peak_dbtp']} dBTP",
                 "", "Guide and backing share the same master gain and frame count. User supplies vocals.",
                 "Native projects can regenerate style voicings; supplied MIDI freezes the approved baseline and preserves post-export expression.",
                 "", "## Verification", "", "```json", json.dumps(result["verification"], ensure_ascii=False, indent=2), "```",
                 "", "Human listening review: " + result["human_listening_review"], "", "## Sample credits", "", *libraries]
        logs.append((log, "\n".join(lines) + "\n"))
        item = {**{key: cfg[key] for key in ("id", "label", "axis", "tempo", "meter", "variation", "room")},
                "files": files, "libraries": libraries, "duration": result["duration_seconds"], "lufs": result["final_lufs"]}
        songs.setdefault(cfg["stem"], {"title": cfg["title"], "versions": []})["versions"].append(item)
        catalogue.append({"song": cfg["title"], "version": cfg["id"], "dimension": cfg["axis"], "tempo": cfg["tempo"],
                          "meter": cfg["meter"], "lufs": result["final_lufs"], "wav": files["wav"], "mp3": files["mp3"], "parameters": files["log"]})
    template = Path(__file__).with_name("listening_page.html").read_text(encoding="utf-8")
    data = json.dumps(songs, ensure_ascii=False).replace("<", "\\u003c")
    out.mkdir(parents=True)
    for path, text in logs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    with (out / "catalogue.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=catalogue[0])
        writer.writeheader()
        writer.writerows(catalogue)
    (out / "catalogue.json").write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(template.replace("__DATA__", data), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    config = load_project(args.config_root)
    publish([data_path(config, value, must_exist=True) for value in args.reports], data_path(config, args.out_dir, directory=True), config)


if __name__ == "__main__":
    main()
