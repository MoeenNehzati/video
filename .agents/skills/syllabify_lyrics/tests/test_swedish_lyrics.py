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


REPO = Path(__file__).resolve().parents[4]
SKILLS = REPO / ".agents/skills"


from optional_skill_fixture import OptionalSkillFixture, load_script


class SwedishLyricsTests(OptionalSkillFixture):
    def test_swedish_letters_survive_syllabification(self):
        text = "Nu är det jul, för där går å-ä-ö!\na\u0308r fo\u0308r da\u0308r\n"
        (self.data / "lyrics.txt").write_text(text, encoding="utf-8")
        self.run_script("syllabify_lyrics", "syllabify_lyrics.py", "lyrics.txt",
                        "--language", "Swedish", "--out", "review/lyrics.json")
        payload = json.loads((self.data / "review/lyrics.json").read_text())
        self.assertTrue(any("English-oriented" in warning for warning in payload["warnings"]))
        lines = payload["lyrics"]["lines"]
        self.assertEqual(lines[0]["syllables"],
                         ["Nu", "är", "det", "jul", "för", "där", "går", "å", "ä", "ö"])
        self.assertEqual(lines[1]["syllables"], ["är", "för", "där"])
        self.assertEqual([line["text"] for line in lines], text.splitlines())
        self.assertEqual((self.data / "lyrics.txt").read_text(), text)
