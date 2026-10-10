"""Portable score/video adapters use explicit data paths and preserve their methods."""
import json
from pathlib import Path

from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
VIDEO = REPO / ".agents/skills/barnsang-video/scripts"


from score_video_fixture import ScoreVideoFixture, load_module


class VideoAdapterTests(ScoreVideoFixture):
    def test_instructions_refuse_to_replace_an_input_or_existing_output(self):
        (self.data / 'image.png').write_bytes(b'image')
        self.json_file('story.json', {'title': 'fixture', 'context': 'fixture', 'style': 'cartoon',
            'video_model': 'fixture', 'aspect_ratio': '16:9',
            'images': [{'id': 'a', 'file': 'image.png', 'description': 'A wave'}],
            'clips': [{'id': 'a', 'start_image': 'a', 'end_image': None, 'duration_s': 1, 'action': 'wave'}]})
        (self.data / 'instructions.txt').write_text('keep')
        before = {p: p.read_bytes() for p in self.data.iterdir()}
        for output in ('story.json', 'image.png', 'instructions.txt'):
            with self.subTest(output=output):
                result = self.run_cli(VIDEO / 'write_flow_instructions.py', '--storyboard', 'story.json', '--output', output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('already exists', result.stderr)
        self.assertEqual({p: p.read_bytes() for p in self.data.iterdir()}, before)

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

    def test_image_edit_stays_disabled_before_network(self):
        module = load_module(VIDEO / "gen_edit.py", "video_edit_test")
        args = ["--config-root", str(self.config), "--model", "run-model", "--quality", "high", "--size", "1536x1024",
                "--prompt", "prompt.txt", "--reference", "prior.png", "--output", "new/frame.png"]
        with patch.object(module.requests, "post") as post:
            with self.assertRaisesRegex(ValueError, 'Image editing is disabled'):
                module.main(args)
            post.assert_not_called()
            self.assertFalse((self.data / 'new').exists())
