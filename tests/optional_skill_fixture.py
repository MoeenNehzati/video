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


def load_script(skill, name):
    spec = importlib.util.spec_from_file_location(name, SKILLS / skill / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OptionalSkillFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="optional skills ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.data = self.work / "project data"
        self.data.mkdir()
        self.configuration = self.work / "configuration"
        self.configuration.mkdir()
        (self.configuration / "config.toml").write_text("", encoding="utf-8")
        self.configure()

    def configure(self, extra=""):
        (self.configuration / "config.local.toml").write_text(
            "[paths]\ndata_root = " + json.dumps(str(self.data)) + "\n" + extra,
            encoding="utf-8",
        )

    def run_script(self, skill, filename, *args, success=True):
        result = subprocess.run(
            [sys.executable, str(SKILLS / skill / "scripts" / filename),
             "--config-root", str(self.configuration), *map(str, args)],
            cwd=self.work, capture_output=True, text=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def make_score(self):
        score = stream.Score()
        part = stream.Part()
        measure = stream.Measure(number=1)
        measure.append(meter.TimeSignature("4/4"))
        measure.append(tempo.MetronomeMark(number=120))
        for pitch in ("C4", "D4", "E4", "G4"):
            measure.append(note.Note(pitch, quarterLength=1))
        part.append(measure)
        score.append(part)
        score.write("musicxml", fp=self.data / "score.musicxml")
