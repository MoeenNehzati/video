"""Portable score/video adapters use explicit data paths and preserve their methods."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCORE = REPO / ".agents/skills/score-to-musicxml/scripts"
VIDEO = REPO / ".agents/skills/barnsang-video/scripts"


def load_module(path, name):
    previous_path = sys.path[:]
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = previous_path


class ScoreVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="score video ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "project data"
        self.data.mkdir()
        self.other = self.root / "different cwd"
        self.other.mkdir()
        self.config = self.root / "project config"
        self.config.mkdir()
        (self.config / "config.toml").write_text("[paths]\n", encoding="utf-8")
        self.local = self.config / "config.local.toml"
        self.local.write_text(f"[paths]\ndata_root = {json.dumps(str(self.data))}\n", encoding="utf-8")

    def json_file(self, name, content):
        path = self.data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(script), "--config-root", str(self.config), *args],
                              cwd=self.other, capture_output=True, text=True)

    def test_score_schema_source_counts_and_full_file_reference_guard(self):
        score = self.data / "score.musicxml"
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
</measure></part></score-partwise>'''
        score.write_text(xml, encoding="utf-8")
        self.json_file("expectations.json", {"counts": {"measures": 1, "notes": 1}})
        result = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--expectations", "expectations.json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(json.loads(result.stdout)["source_fidelity_certified"])
        self.json_file("expectations.json", {"counts": {"harmonies": 1}})
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--expectations", "expectations.json")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("completeness harmonies", failed.stdout)
        validator = load_module(SCORE / "validate.py", "score_validator_test")
        self.json_file("reference.json", validator.canonical(score))
        reviewed_hash = hashlib.sha256(score.read_bytes()).hexdigest()
        score.write_text(xml.replace("<part-list>", "<credit><credit-words>Changed credit</credit-words></credit><part-list>"), encoding="utf-8")
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--reference", "reference.json",
                              "--reviewed-sha256", reviewed_hash)
        self.assertNotEqual(failed.returncode, 0)
        report = json.loads(failed.stdout)
        self.assertTrue(report["reviewed_reference_matches"])
        self.assertFalse(report["reviewed_file_matches"])
        score.write_text(xml.replace("<step>C</step>", "<step>H</step>"), encoding="utf-8")
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("schema:", failed.stdout)

    def test_slope_geometry_uses_source_and_explicit_output(self):
        import cv2
        import numpy as np
        original = np.full((400, 1600, 3), 255, dtype=np.uint8)
        for index in range(5):
            cv2.line(original, (100, 150 + index * 12), (1500, 190 + index * 12), (0, 0, 0), 2)
        source = self.data / "source.png"
        self.assertTrue(cv2.imwrite(str(source), original))
        before = source.read_bytes()
        self.json_file("seeds.json", [[100, 1500, 150, 190, 12, 12]])
        result = self.run_cli(SCORE / "slope_grid.py", "source.png", "seeds.json", "geometry")
        self.assertEqual(result.returncode, 0, result.stderr)
        geometry = json.loads((self.data / "geometry/geometry.json").read_text())
        self.assertTrue(geometry["systems"][0]["accepted_geometry"])
        self.assertEqual(geometry["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(source.read_bytes(), before)
        self.assertTrue((self.data / "geometry/system_1_grid.png").exists())

    def install_media_stubs(self):
        stub = self.root / "media stub.py"
        stub.write_text('''import json, pathlib, sys
mode=sys.argv[1]
if mode == "probe":
    print(pathlib.Path(sys.argv[-1]).read_text())
else:
    log=pathlib.Path(sys.argv[2])
    with log.open("a", encoding="utf-8") as stream: stream.write(json.dumps(sys.argv[3:])+"\\n")
    pathlib.Path(sys.argv[-1]).write_bytes(b"synthetic media")
''', encoding="utf-8")
        self.tool_log = self.root / "tool calls.jsonl"
        with self.local.open("a", encoding="utf-8") as out:
            out.write("[tools.ffprobe]\ncommand = " + json.dumps([sys.executable, str(stub), "probe"]) + "\n")
            out.write("[tools.ffmpeg]\ncommand = " + json.dumps([sys.executable, str(stub), "render", str(self.tool_log)]) + "\n")

    def test_two_distinct_song_configs_preserve_continuity_and_verse_speed(self):
        self.install_media_stubs()
        for name, bpm, source_bpm, beats, groups in [
                ("one", 80, 90, 4, [["a", "b"], ["c"]]),
                ("two", 120, 120, 3, [["x"], ["y"], ["z"]])]:
            with self.subTest(song=name):
                keys = [key for group in groups for key in group]
                for key in keys:
                    (self.data / f"{name}-{key}.png").write_bytes(b"image fixture")
                    (self.data / f"{name}-{key}.mp4").write_text("4", encoding="utf-8")
                story = {"title": name, "context": "Synthetic fixture", "style": "cartoon",
                    "video_model": "selected-by-run", "aspect_ratio": "16:9",
                    "images": [{"id": key, "file": f"{name}-{key}.png", "description": f"Pose {key}"} for key in keys],
                    "clips": [{"id": key, "start_image": key, "end_image": keys[i+1] if i+1 < len(keys) else None,
                               "duration_s": 4, "action": f"Move to pose {i+1}"} for i, key in enumerate(keys)]}
                self.json_file(f"{name}-story.json", story)
                result = self.run_cli(VIDEO / "write_flow_instructions.py", "--storyboard", f"{name}-story.json",
                                      "--output", f"{name}/INSTRUCTIONS.txt")
                self.assertEqual(result.returncode, 0, result.stderr)
                instructions = (self.data / name / "INSTRUCTIONS.txt").read_text()
                self.assertIn(f"START {name}-{keys[0]}.png -> END {name}-{keys[1]}.png", instructions)
                settings = {"source_bpm": source_bpm, "target_bpm": bpm, "beats_per_bar": beats,
                    "verse_bars": 2, "interlude_bars": 1, "verse_groups": groups,
                    "width": 1280, "height": 720, "fps": 24}
                self.json_file(f"{name}-assembly.json", settings)
                self.json_file(f"{name}-clips.json", [{"id": key, "file": f"{name}-{key}.mp4"} for key in keys])
                (self.data / f"{name}.wav").write_text("8", encoding="utf-8")
                result = self.run_cli(VIDEO / "assemble_flow.py", "--song-config", f"{name}-assembly.json",
                    "--clips", f"{name}-clips.json", "--audio", f"{name}.wav", "--output", f"{name}/film.mp4",
                    "--output-audio", f"{name}/prepared.wav", "--timeline", f"{name}/timeline.json")
                self.assertEqual(result.returncode, 0, result.stderr)
                timeline = json.loads((self.data / name / "timeline.json").read_text())
                spacing = 3 * beats * 60 / bpm
                self.assertEqual(timeline["verse_starts_s"], [i * spacing for i in range(len(groups))])
                by_id = {clip["id"]: clip for clip in timeline["clips"]}
                for group in groups:
                    self.assertEqual(len({by_id[key]["speed"] for key in group}), 1)
                self.assertAlmostEqual(timeline["clips"][-1]["end_s"], timeline["duration_s"])
                self.assertEqual(timeline["tempo"], bpm / source_bpm)
        calls = [json.loads(line) for line in self.tool_log.read_text().splitlines()]
        self.assertEqual(len(calls), 4)
        self.assertIn("atempo=0.888", " ".join(calls[0]))
        self.assertIn("normalize=0", " ".join(calls[0]))

    def test_bad_continuity_and_missing_tools_create_no_outputs(self):
        (self.data / "image.png").write_bytes(b"fixture")
        self.json_file("bad-story.json", {"title": "test", "context": "fixture", "style": "cartoon",
            "video_model": "fixture", "aspect_ratio": "16:9",
            "images": [{"id": "a", "file": "image.png", "description": "fixture"}],
            "clips": [{"id": key, "start_image": "a", "end_image": None, "duration_s": 1, "action": "wave"} for key in [1, 2]]})
        result = self.run_cli(VIDEO / "write_flow_instructions.py", "--storyboard", "bad-story.json", "--output", "new/instructions.txt")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.data / "new").exists())
        result = self.run_cli(VIDEO / "assemble_flow.py", "--song-config", "unused.json", "--clips", "unused.json",
                              "--audio", "unused.wav", "--output", "new/film.mp4", "--output-audio", "new/audio.wav", "--timeline", "new/timeline.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tools.ffmpeg.command", result.stderr)
        self.assertFalse((self.data / "new").exists())

    def test_image_edit_checks_paths_before_network_and_records_references(self):
        module = load_module(VIDEO / "gen_edit.py", "video_edit_test")
        (self.data / "prompt.txt").write_text("Change only the pose", encoding="utf-8")
        (self.data / "prior.png").write_bytes(b"prior fixture")
        args = ["--config-root", str(self.config), "--model", "run-model", "--quality", "high", "--size", "1536x1024",
                "--prompt", "prompt.txt", "--reference", "prior.png", "--output", "new/frame.png"]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch.object(module.requests, "post") as post:
            post.return_value.json.return_value = {"data": [{"b64_json": base64.b64encode(b"synthetic image").decode()}]}
            module.main(args)
            self.assertEqual(post.call_count, 1)
            self.assertIn("image[]", post.call_args.kwargs["files"][0])
            record = json.loads((self.data / "new/frame.png.json").read_text())
            self.assertEqual(record["refs"], [str(self.data / "prior.png")])
            post.reset_mock()
            with self.assertRaises(ValueError):
                module.main(args[:-1] + [str(self.root / "outside.png")])
            post.assert_not_called()
            self.assertFalse((self.root / "outside.png").exists())


if __name__ == "__main__":
    unittest.main()
