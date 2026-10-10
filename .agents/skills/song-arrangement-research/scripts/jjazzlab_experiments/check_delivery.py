"""Check rendered hashes/format/alignment and local listening-page playback."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from scripts.project_runtime import add_config_argument, data_path, load_project, tool_command
from verification import artifact_file, component, require, sha


def check_files(rows, config):
    import soundfile as sf
    require(rows, "No deliveries supplied")
    checks = []
    for row in rows:
        audio = data_path(config, row["folder"], must_exist=True, directory=True)
        arrangement = data_path(config, row["arrangement_folder"], must_exist=True, directory=True)
        stem = component(row["filename"])
        for extension in ("wav", "mp3", "mid", "sng", "mix"):
            parent = audio if extension in ("wav", "mp3") else arrangement
            path = artifact_file(config, parent, stem + "." + extension, must_exist=True)
            require(path.stat().st_size > 0, "Empty delivery file")
            if extension in ("wav", "mp3", "mid"):
                expected = row[extension + "_sha256"] if extension != "mid" else row["verification"]["midi_sha256"]
                require(sha(path) == expected, "Delivery hash mismatch")
        info = sf.info(audio / (stem + ".wav"))
        require(info.samplerate == 48000 and info.channels == 2 and info.subtype == "PCM_24", "Unexpected WAV format")
        require(abs(row["final_lufs"] - row["target_lufs"]) < .05 and row["final_true_peak_dbtp"] <= row["peak_ceiling_dbtp"] + .01, "Recorded loudness/peak limit failed")
        for ext in ("wav", "mp3", "mid"):
            parent = arrangement if ext == "mid" else audio
            path = artifact_file(config, parent, stem + "_backing." + ext, must_exist=True)
            require(sha(path) == row["backing"][("midi" if ext == "mid" else ext) + "_sha256"], "Backing hash mismatch")
        back = sf.info(audio / (stem + "_backing.wav"))
        require(back.frames == info.frames and back.subtype == info.subtype and back.samplerate == info.samplerate and back.channels == info.channels, "Backing alignment/format mismatch")
        checks.append(stem)
    return checks


def check_page(directory, config):
    from playwright.sync_api import sync_playwright
    browser_command = tool_command(config, "browser")
    songs = json.loads((directory / "catalogue.json").read_text(encoding="utf-8"))
    for song in songs.values():
        for version in song["versions"]:
            for link in version["files"].values():
                data_path(config, directory / unquote(link), must_exist=True)
    errors, media = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_command[0], args=browser_command[1:] + ["--mute-audio"], headless=True)
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 1040})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto((directory / "index.html").as_uri())
            require(page.locator("#song option").count() == len(songs), "Song count differs")
            for key, song in songs.items():
                page.select_option("#song", key)
                versions = song["versions"]
                require(page.locator(".version").count() == len(versions), "Version count differs")
                for index, version in enumerate(versions):
                    page.locator(".version").nth(index).click()
                    page.wait_for_function("document.querySelector('audio').readyState>=1 && Number.isFinite(document.querySelector('audio').duration)")
                    item = page.locator("audio").evaluate("a => ({src:a.currentSrc,duration:a.duration,error:a.error&&a.error.message})")
                    expected = (directory / unquote(version["files"]["mp3"])).resolve().as_uri()
                    require(item["error"] is None and item["duration"] > 0 and item["src"] == expected, "Preview failed to load")
                    media.append(item)
                if len(versions) > 1:
                    page.locator(".version").nth(1).click()
                    page.wait_for_function("document.querySelector('audio').readyState>=1")
                    second = versions[1]
                    position = min(2., second["duration"] / 4, versions[0]["duration"] * versions[0]["tempo"] / second["tempo"] / 4)
                    page.locator("audio").evaluate("(a,t)=>a.currentTime=t", position)
                    page.click("#ref")
                    page.wait_for_function("document.querySelector('audio').readyState>=1 && document.querySelector('audio').currentTime>0")
                    at = page.locator("audio").evaluate("a=>a.currentTime")
                    require(abs(at - position * second["tempo"] / versions[0]["tempo"]) < .2, "A/B beat position changed")
                    page.click("#chosen")
                    page.wait_for_function("document.querySelector('audio').readyState>=1 && document.querySelector('audio').currentTime>0")
                    require(abs(page.locator("audio").evaluate("a=>a.currentTime") - position) < .2, "A/B round trip changed position")
            page.set_viewport_size({"width": 390, "height": 844})
            require(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), "Mobile overflow")
            require(not errors, f"Browser JavaScript errors: {errors}")
        finally:
            browser.close()
    return {"media_loads": media, "javascript_errors": errors, "mobile_layout_no_horizontal_overflow": True, "ab_tempo_position_preservation_pass": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--page-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    config = load_project(args.config_root)
    out = data_path(config, args.out)
    require(not out.exists(), "Delivery report already exists")
    rows = [row for value in args.reports for row in json.loads(data_path(config, value, must_exist=True).read_text(encoding="utf-8"))]
    files = check_files(rows, config)
    result = check_page(data_path(config, args.page_dir, must_exist=True, directory=True), config)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"files_verified": files, **result}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
