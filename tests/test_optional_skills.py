"""Exercise optional skill I/O and preserved musical logic with synthetic inputs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

from unittest.mock import patch

import numpy as np
from music21 import meter, note, stream, tempo


REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".agents/skills"


from optional_skill_fixture import OptionalSkillFixture, load_script


class OptionalSkillTests(OptionalSkillFixture):
    def test_analysis_lyrics_and_alignment_explicit_paths(self):
        self.make_score()
        (self.data / "lyrics.txt").write_text("Sun-shine\n", encoding="utf-8")
        source_bytes = (self.data / "score.musicxml").read_bytes()
        self.run_script("analyze_music", "analyze_music.py", "score.musicxml", "--out", "review/music.json")
        self.run_script("syllabify_lyrics", "syllabify_lyrics.py", "lyrics.txt", "--out", "review/lyrics.json")
        self.run_script("plan_vocals", "plan_and_align_vocals.py", "review/music.json", "review/lyrics.json",
                        "--score", "score.musicxml", "--out", "review/events.json")
        lyrics = json.loads((self.data / "review/lyrics.json").read_text())
        self.assertEqual(lyrics["lyrics"]["lines"][0]["syllables"], ["Sun", "shine"])
        result = json.loads((self.data / "review/events.json").read_text())
        events = result["vocal_events"]
        self.assertEqual(len(events), 4)
        self.assertEqual(sum(event["duration_beats"] for event in events), 4)
        self.assertEqual([event["pitch"] for event in events], ["C4", "D4", "E4", "G4"])
        self.assertEqual([event["lyric"] for event in events if not event["is_slur"]], ["Sun", "shine"])
        self.assertTrue(all(event["lyric"] == "" for event in events if event["is_slur"]))
        self.assertEqual((self.data / "score.musicxml").read_bytes(), source_bytes)

    def test_cli_rejects_outside_root_and_self_overwrite(self):
        lyrics = self.data / "lyrics.txt"
        lyrics.write_text("la-la\n", encoding="utf-8")
        outside = self.work / "unmanaged.json"
        self.run_script("syllabify_lyrics", "syllabify_lyrics.py", "lyrics.txt", "--out", outside, success=False)
        self.run_script("syllabify_lyrics", "syllabify_lyrics.py", "lyrics.txt", "--out", "lyrics.txt", success=False)
        self.assertFalse(outside.exists())
        self.assertEqual(lyrics.read_text(), "la-la\n")
        # Legacy combined input is no longer an advertised or accepted mode.
        self.run_script("plan_vocals", "plan_and_align_vocals.py", "combined.json", "--score", "score.xml",
                        "--out", "new/events.json", success=False)
        self.assertFalse((self.data / "new").exists())
