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


class SynthesisAlgorithmTests(OptionalSkillFixture):
    def test_nishiren_fails_before_debug_or_audio_with_missing_models(self):
        models = self.work / "external voicebank"
        models.mkdir()
        self.configure("[resources]\nnishiren_root = " + json.dumps(str(models)) + "\n")
        (self.data / "events.json").write_text("{}", encoding="utf-8")
        module = load_script("synthesize_vocal_with_diffsinger", "synthesize_vocal_with_diffsinger")
        with self.assertRaisesRegex(ValueError, "Missing Nishiren resources"):
            module._preflight_models(models, "Standard")
        self.assertFalse((self.data / "output").exists())

    def test_nishiren_timing_pitch_and_pronunciation_contract(self):
        module = load_script("synthesize_vocal_with_diffsinger", "synthesize_vocal_with_diffsinger")
        self.assertAlmostEqual(module._pitch_to_hz("A4"), 440.0)
        self.assertAlmostEqual(module._pitch_to_hz("B-4"), module._pitch_to_hz("Bb4"))
        event = {"measure": 1, "start_beat": 1, "duration_beats": 3, "pitch": "C4", "lyric": "la", "is_slur": False}
        module._validate_event_timing([event, dict(event, measure=2)], "3/4")
        for changes in ({"start_beat": 2}, {"lyric": ""}, {"is_slur": True}, {"pitch": "REST"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                module._validate_event_timing([dict(event, **changes)], "3/4")
        self.assertEqual(module._normalize_nishiren_phonemes(["AA1", "en/l"], "en"), ["en/aa", "en/l"])
        with self.assertRaises(ValueError):
            module._word_to_phones("unknown", {})

    def test_nishiren_keeps_duration_and_phoneme_inference(self):
        module = load_script("synthesize_vocal_with_diffsinger", "synthesize_vocal_with_diffsinger")
        voicebank = self.work / "voicebank"
        for group in ("dsdur", "dsmain", "dsvocoder"):
            (voicebank / group).mkdir(parents=True)
        for group in ("dsdur", "dsmain"):
            (voicebank / group / "phonemes.json").write_text(json.dumps({"en/l": 1, "en/aa": 2}))
            (voicebank / group / "languages.json").write_text(json.dumps({"en": 0}))
        for name in ("dsdur/linguistic.onnx", "dsdur/dur.onnx", "dsmain/acoustic.onnx", "dsvocoder/vocoder.onnx"):
            (voicebank / name).touch()
        np.zeros(384, dtype=np.float32).tofile(voicebank / "dsmain/Standard.emb")
        calls = {}

        class Session:
            def __init__(self, path, providers):
                self.name = Path(path).stem

            def run(self, requested, inputs):
                calls[self.name] = inputs
                if self.name == "linguistic":
                    return np.zeros((1, 2, 384)), np.ones((1, 2))
                if self.name == "dur":
                    return [np.array([[1.0, 3.0]])]
                if self.name == "acoustic":
                    return [np.zeros((1, 1, 1))]
                return [np.array([0.1, -0.1], dtype=np.float32)]

        soundfile = types.SimpleNamespace(write=lambda path, samples, sr: Path(path).write_bytes(b"synthetic wav"))
        with patch.dict(sys.modules, {"onnxruntime": types.SimpleNamespace(InferenceSession=Session), "soundfile": soundfile}):
            log = module._run_nishiren_onnx(
                nishiren_root=voicebank, language="en", style="Standard",
                events=[{"lyric": "la", "duration_beats": 1, "pitch": "A4", "phonemes": ["L", "AA1"]}],
                tempo_bpm=60, sr=44100, out_wav=self.data / "result.wav", log_path=self.data / "log.json",
                debug_out=self.data / "debug.json", vel=1.25, gender=0, steps=30, lexicon={},
            )
        self.assertEqual(calls["linguistic"]["tokens"].tolist(), [[1, 2]])
        self.assertEqual(calls["acoustic"]["durations"].sum(), round(44100 / 512))
        self.assertEqual(log["phoneme_count"], 2)
        self.assertEqual(json.loads((self.data / "debug.json").read_text())["ph_seq"], "en/l en/aa")
