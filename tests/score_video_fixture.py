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


class ScoreVideoFixture(unittest.TestCase):
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
