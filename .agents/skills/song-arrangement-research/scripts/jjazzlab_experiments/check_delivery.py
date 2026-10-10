"""Check rendered hashes/format/alignment and local listening-page playback."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

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


def check_page(directory, config, browser_command, environment, *, out):
    require(not Path(out).exists(), "Verification report already exists")
    require(not any(arg.startswith(("--user-data-dir", "--profile-directory")) for arg in browser_command[1:]),
            "Browser profile must remain private")
    from playwright.sync_api import sync_playwright
    songs = json.loads((directory / "catalogue.json").read_text(encoding="utf-8"))
    for song in songs.values():
        for version in song["versions"]:
            for link in version["files"].values():
                url = urlsplit(link)
                require(not (url.scheme or url.netloc or url.query or url.fragment), "Page links must be local files")
                linked = data_path(config, directory / unquote(link), must_exist=True)
                require(linked.is_relative_to(directory.resolve()), "Page links must remain inside the delivery")
    errors, media = [], []
    local_files = {path.resolve() for path in directory.rglob('*') if path.is_file()}
    def local_request(route):
        url = urlsplit(route.request.url)
        allowed = (url.scheme in ('data', 'blob') or
                   (url.scheme == 'file' and not url.netloc and Path(url2pathname(url.path)).resolve() in local_files))
        route.continue_() if allowed else route.abort()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_command[0], args=browser_command[1:] + ["--mute-audio"], headless=True, env=environment)
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 1040}, service_workers="block")
            page.route("**/*", local_request)
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
    parser.add_argument("--scratch", required=True, help="New private browser home and temporary directory")
    args = parser.parse_args()
    config = load_project(args.config_root)
    output = data_path(config, args.out)
    require(not output.exists(), "Verification report already exists")
    page = data_path(config, args.page_dir, must_exist=True, directory=True)
    reports = [data_path(config, value, must_exist=True) for value in args.reports]
    rows = [row for report in reports for row in json.loads(report.read_text(encoding="utf-8"))]
    files = check_files(rows, config)
    browser = tool_command(config, "browser")
    scratch = data_path(config, args.scratch, directory=True)
    require(not scratch.exists(), "Browser scratch directory already exists")
    require(not output.is_relative_to(scratch) and not scratch.is_relative_to(page), "Scratch must be separate from report and page")
    scratch.mkdir(parents=True)
    environment = dict(os.environ)
    for name in ("PLAYWRIGHT_NODEJS_PATH", "NODE_OPTIONS", "NODE_PATH"):
        os.environ.pop(name, None)
        environment.pop(name, None)
    for name in ("HOME", "TMPDIR", "TMP", "TEMP", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        environment[name] = str(scratch)
        os.environ[name] = str(scratch)
    result = check_page(page, config, browser, environment, out=output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"files_verified": files, **result}, stream, indent=2)


if __name__ == "__main__":
    main()
