"""Exercise optional skill I/O and preserved musical logic with synthetic inputs."""
import csv
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


class OptionalSkillTests(unittest.TestCase):
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

    def acquisition_args(self):
        return ["catalog.csv", "--sheets-dir", "acquired/sheets", "--xml-dir", "acquired/xml",
                "--midi-dir", "acquired/midi", "--lyrics-dir", "acquired/lyrics",
                "--build-dir", "acquired/derived", "--report", "acquired/report.md", "--no-lyrics"]

    def make_catalog(self):
        source = self.data / "source.musicxml"
        source.write_text('<score-partwise><work><work-title>Fixture</work-title></work></score-partwise>')
        with (self.data / "catalog.csv").open("w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["number", "title", "copyright_status", "source", "url", "format"])
            writer.writerow(["01", "Fixture", "FRI GLOBALT", "fixture", source.as_uri(), "MUSICXML"])

    def test_acquisition_checks_tools_before_creating_outputs(self):
        self.make_catalog()
        self.run_script("download-scores", "download_scores.py", *self.acquisition_args(), success=False)
        self.assertFalse((self.data / "acquired").exists())

    def test_acquisition_report_cannot_replace_catalogue(self):
        self.make_catalog()
        original = (self.data / "catalog.csv").read_bytes()
        args = self.acquisition_args()
        args[args.index("--report") + 1] = "catalog.csv"
        result = self.run_script("download-scores", "download_scores.py", *args, "--no-convert", success=False)
        self.assertIn("must not replace", result.stderr)
        self.assertEqual((self.data / "catalog.csv").read_bytes(), original)
        self.assertFalse((self.data / "acquired").exists())

    def symlink(self, path, target, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")

    def test_acquisition_validates_derived_directories_and_download_filenames(self):
        self.make_catalog()
        outside = self.work / "outside data"
        outside.mkdir()
        derived = self.data / "acquired/derived"
        derived.mkdir(parents=True)
        self.symlink(derived / "xml", outside, directory=True)
        result = self.run_script("download-scores", "download_scores.py", *self.acquisition_args(),
                                 "--no-convert", success=False)
        self.assertIn("inside paths.data_root", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])
        (derived / "xml").unlink()
        downloads = self.data / "acquired/xml"
        downloads.mkdir()
        victim = outside / "valuable.musicxml"
        victim.write_text("original", encoding="utf-8")
        self.symlink(downloads / "01_Fixture_fixture.musicxml", victim)
        result = self.run_script("download-scores", "download_scores.py", *self.acquisition_args(),
                                 "--no-convert", "--force", success=False)
        self.assertIn("inside paths.data_root", result.stderr)
        self.assertEqual(victim.read_text(), "original")
        self.assertFalse((self.data / "acquired/report.md").exists())

    def test_audiveris_checks_log_and_discovered_byproduct_paths(self):
        module = load_script("download-scores", "download_scores")
        config = {"paths": {"data_root": str(self.data)}}
        source = self.data / "scan.pdf"
        source.write_bytes(b"%PDF-fixture")
        output = self.data / "converted"
        output.mkdir()
        logs = self.data / "logs"
        logs.mkdir()
        outside = self.work / "external"
        outside.mkdir()
        victim = outside / "do-not-touch.log"
        victim.write_text("original")
        self.symlink(logs / "scan.audiveris.log", victim)
        with patch.object(module.subprocess, "run") as run, self.assertRaises(ValueError):
            module._audiveris_export_pdf_to_mxl(["tool"], source, output, logs, config, ())
        run.assert_not_called()
        self.assertEqual(victim.read_text(), "original")
        (logs / "scan.audiveris.log").unlink()
        self.symlink(output / "intermediate", outside, directory=True)

        def fake_audiveris(command, **kwargs):
            target = Path(command[command.index("-output") + 1])
            (target / "scan.mxl").write_bytes(b"synthetic mxl")
            (target / "intermediate").mkdir()
            (target / "intermediate/book.omr").write_bytes(b"synthetic omr")

        with patch.object(module.subprocess, "run", side_effect=fake_audiveris), self.assertRaises(ValueError):
            module._audiveris_export_pdf_to_mxl(["tool"], source, output, logs, config, ())
        self.assertFalse((outside / "book.omr").exists())
        self.assertFalse((output / "scan.mxl").exists())
        self.assertFalse((logs / "scan.audiveris.log").exists())

    def test_acquisition_uses_one_configured_exporter_and_handles_failure(self):
        self.make_catalog()
        stub = self.work / "stub exporter.py"
        calls = self.work / "calls.jsonl"
        stub.write_text(
            "import json, pathlib, sys\n"
            "args=sys.argv[2:]\n"
            "with pathlib.Path(sys.argv[1]).open('a') as f: f.write(json.dumps(args)+'\\n')\n"
            "out=pathlib.Path(args[args.index('-o')+1])\n"
            "if out.suffix == '.pdf': sys.exit(7)\n"
            "out.write_bytes(b'MThdfixture')\n", encoding="utf-8",
        )
        self.configure("[tools.musescore]\ncommand = " + json.dumps([sys.executable, str(stub), str(calls)]) + "\n")
        self.run_script("download-scores", "download_scores.py", *self.acquisition_args())
        self.assertEqual((self.data / "acquired/derived/midi/01_Fixture.mid").read_bytes(), b"MThdfixture")
        self.assertFalse((self.data / "acquired/derived/sheets/01_Fixture.pdf").exists())
        report = (self.data / "acquired/report.md").read_text()
        self.assertIn("MusicXML→PDF FAILED", report)
        commands = [json.loads(line) for line in calls.read_text().splitlines()]
        self.assertEqual(len(commands), 2)
        self.assertEqual({Path(command[1]).suffix for command in commands}, {".mid", ".pdf"})

    def test_nishiren_fails_before_debug_or_audio_with_missing_models(self):
        models = self.work / "external voicebank"
        models.mkdir()
        self.configure("[resources]\nnishiren_root = " + json.dumps(str(models)) + "\n")
        (self.data / "events.json").write_text("{}", encoding="utf-8")
        result = self.run_script("synthesize_vocal_with_diffsinger", "synthesize_vocal_with_diffsinger.py",
                                "events.json", "--out", "output/vocal.wav", "--debug-out", "output/debug.json",
                                "--log", "output/log.json", success=False)
        self.assertIn("Missing Nishiren resources", result.stderr)
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


if __name__ == "__main__":
    unittest.main()
