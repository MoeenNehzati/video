"""Verify controlled variants and render aligned guide/backing with shared gain."""
import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from scripts.project_runtime import add_config_argument, data_path, load_project, resource_path, tool_command

from verification import artifact_file, component, check_frozen_messages, check_backing, check_child_events, load_auditor, require, sha, verify

RATE = 48000


def normalize_pair(data, backing, meter, target):
    """Preserve relative guide/backing levels; never normalize backing alone."""
    require(data.shape == backing.shape, "Full/backing frame count differs")
    raw = float(meter.integrated_loudness(data))
    require(math.isfinite(raw), "Non-finite source loudness")
    gain = 10 ** ((target - raw) / 20)
    for _ in range(6):
        delta = target - float(meter.integrated_loudness(data * gain))
        if abs(delta) < .005:
            break
        gain *= 10 ** (delta / 20)
    return data * gain, backing * gain, gain


def render(folders, out, config, target=-18.3, ceiling=-1.5, audio_out=None):
    out = data_path(config, out, directory=True)
    require(not out.exists() or not any(out.iterdir()), "Render report directory must be empty")
    audio_out = data_path(config, audio_out or out / "audio", directory=True)
    require(audio_out != out and not out.is_relative_to(audio_out), "Audio and report destinations must be separate")
    import numpy as np
    import soundfile as sf
    import pyloudnorm as pyln
    from scipy.signal import resample_poly
    from sample_renderer import banks, CounterRenderer

    auditor = load_auditor(config)
    ffmpeg = tool_command(config, "ffmpeg")
    library = resource_path(config, "fluidsynth_library")
    fonts = banks(resource_path(config, "soundfont_manifest"))
    credits = resource_path(config, "soundfont_credits")
    require(math.isfinite(target) and math.isfinite(ceiling) and ceiling <= 0, "Invalid loudness/peak targets")
    require(not (out / "verification.json").exists(), "Render report already exists; allocate a new version")
    jobs = []
    destinations = set()
    for folder in folders:
        cfg, verification = verify(folder, config, auditor)
        component(cfg["filename"])
        component(cfg["baseline_filename"])
        component(cfg["stem"])
        component(cfg["id"])
        mid = artifact_file(config, folder, cfg["filename"] + ".mid", must_exist=True)
        base = artifact_file(config, data_path(config, cfg["baseline_folder"], must_exist=True, directory=True), cfg["baseline_filename"] + ".mid", must_exist=True)
        require(sha(base) == cfg["baseline_midi_sha256"], "Changed baseline MIDI")
        require(sha(data_path(config, cfg["child_plan"], must_exist=True)) == cfg["child_plan_sha256"], "Changed child plan")
        actual, reference = auditor.read_midi(mid), auditor.read_midi(base)
        check_child_events(actual, reference, cfg["variant_operations"])
        check_frozen_messages(mid, base)
        with (folder / "tracks.tsv").open(encoding="utf-8", newline="") as stream:
            channels = {row["voice"]: int(row["channel"]) for row in csv.DictReader(stream, delimiter="\t")}
        backing_path = artifact_file(config, folder, cfg["filename"] + "_backing.mid", must_exist=True)
        check_backing(actual, auditor.read_midi(backing_path), channels["Original melody"])
        require(cfg["counter_library"] in fonts, "Missing supporting instrument sample library")
        require(cfg["room"] in ("studio", "hall", "chamber"), "Unsupported room")
        destination = audio_out / cfg["stem"] / cfg["id"]
        require(not destination.exists(), "Render destination already exists")
        require(destination not in destinations, "Duplicate render destination")
        destinations.add(destination)
        for suffix in ("", "_backing"):
            for ext in (".wav", ".mp3"):
                artifact_file(config, destination, cfg["filename"] + suffix + ext)
        jobs.append((folder, cfg, verification, mid, backing_path, channels, destination))
    require(jobs, "No arrangements supplied")
    out.mkdir(parents=True, exist_ok=True)
    synth = CounterRenderer(fonts, library)
    meter = pyln.Meter(RATE)
    results = []
    try:
        for folder, cfg, verification, mid, backing_path, channels, destination in jobs:
            synth.counter_channel = channels["Background line"]
            synth.counter_library = cfg["counter_library"]
            data, report = synth.render(mid, cfg["room"])
            backing, _ = synth.render(backing_path, cfg["room"])
            data, backing, gain = normalize_pair(data, backing, meter, target)
            outputs = {}
            # Measure BOTH outputs before writing either one.
            for suffix, signal in (("", data), ("_backing", backing)):
                lufs = float(meter.integrated_loudness(signal))
                amplitude = float(np.max(abs(resample_poly(signal, 4, 1, axis=0))))
                peak = 20 * math.log10(amplitude) if amplitude > 0 else -math.inf
                require(math.isfinite(lufs) and peak <= ceiling + .01, "Loudness/true-peak check failed")
                require(bool(suffix) or abs(lufs - target) < .05, "Loudness matching failed")
                outputs[suffix] = {"lufs": round(lufs, 3), "true_peak_dbtp": round(peak, 3)}
            destination.mkdir(parents=True)
            for suffix, signal in (("", data), ("_backing", backing)):
                wav = artifact_file(config, destination, cfg["filename"] + suffix + ".wav")
                mp3 = wav.with_suffix(".mp3")
                sf.write(wav, signal, RATE, subtype="PCM_24")
                subprocess.run([*ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "320k",
                                "-metadata", "title=" + cfg["title"] + " - " + cfg["id"] + suffix,
                                "-metadata", "comment=Sample sources and licenses: accompanying CREDITS.md", str(mp3)], check=True)
                outputs[suffix].update(wav_sha256=sha(wav), mp3_sha256=sha(mp3))
            shutil.copy2(credits, destination / "CREDITS.md")
            verification.update(pitched_baseline_exact=True, percussion_matches_plan=True, source_and_plan_hashes_verified=True,
                                backing_contains_every_non_guide_event=True, backing_audio_frame_aligned=True)
            report.update(folder=str(destination), arrangement_folder=str(folder), filename=cfg["filename"], title=cfg["title"], id=cfg["id"],
                          song_id=cfg["stem"], tempo=cfg["tempo"], verification=verification, target_lufs=target, peak_ceiling_dbtp=ceiling,
                          final_lufs=outputs[""]["lufs"], final_true_peak_dbtp=outputs[""]["true_peak_dbtp"], normalization_gain_db=round(20 * math.log10(gain), 3),
                          duration_seconds=round(len(data) / RATE, 3), wav_sha256=outputs[""]["wav_sha256"], mp3_sha256=outputs[""]["mp3_sha256"],
                          wav_format="48 kHz stereo PCM 24-bit", mp3_format="320 kbps stereo",
                          backing={**outputs["_backing"], "midi_sha256": sha(backing_path), "frames": len(backing), "gain_policy": "Same gain as full mix"},
                          child_plan_sha256=cfg["child_plan_sha256"], human_listening_review="pending", vocals="user_supplied",
                          libraries={key: {"sha256": value["sha256"], "credits": value["credits"]} for key, value in fonts.items()})
            log = out / cfg["stem"] / cfg["id"] / "render_log.json"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(report)
    finally:
        synth.close()
    (out / "verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("folders", help="JSON list of arrangement directories")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--audio-dir", help="Separate audio bundle root; defaults to out-dir/audio")
    parser.add_argument("--target-lufs", type=float, default=-18.3)
    parser.add_argument("--peak-ceiling", type=float, default=-1.5)
    args = parser.parse_args()
    config = load_project(args.config_root)
    listing = data_path(config, args.folders, must_exist=True)
    values = json.loads(listing.read_text(encoding="utf-8"))
    require(isinstance(values, list) and values and all(isinstance(value, str) for value in values), "Expected nonempty folder list")
    folders = [data_path(config, value, must_exist=True, directory=True) for value in values]
    require(len(set(folders)) == len(folders), "Duplicate arrangement folder")
    render(folders, args.out_dir, config, args.target_lufs, args.peak_ceiling, args.audio_dir)


if __name__ == "__main__":
    main()
