"""Behavioral checks for the retained arrangement adapter, with synthetic inputs."""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from unittest.mock import patch

import mido
import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parents[4]
ADAPTER = REPO / ".agents/skills/song-arrangement-research/scripts/jjazzlab_experiments"
sys.path.insert(0, str(ADAPTER))


def load(name):
    spec = importlib.util.spec_from_file_location("arrangement_test_" + name, ADAPTER / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArrangementRuntimeTests(unittest.TestCase):
    def config(self, directory):
        return {"paths": {"data_root": str(directory)}}

    def midi(self, path):
        midi = mido.MidiFile(type=1, ticks_per_beat=480)
        midi.tracks = [mido.MidiTrack([
            mido.MetaMessage("set_tempo", tempo=500000),
            mido.MetaMessage("time_signature", numerator=4, denominator=4),
            mido.MetaMessage("end_of_track", time=1920),
        ]), mido.MidiTrack([
            mido.MetaMessage("track_name", name="Original melody"),
            mido.Message("program_change", channel=0, program=0),
            mido.Message("note_on", channel=0, note=60, velocity=81),
            mido.Message("note_off", channel=0, note=60, time=1920),
        ]), mido.MidiTrack([
            mido.MetaMessage("track_name", name="Background line"),
            mido.Message("control_change", channel=1, control=11, value=90),
            mido.Message("note_on", channel=1, note=48, velocity=66),
            mido.Message("control_change", channel=1, control=11, value=102, time=240),
            mido.Message("note_off", channel=1, note=48, time=1680),
        ]), mido.MidiTrack([
            mido.Message("note_on", channel=9, note=36, velocity=50),
            mido.Message("note_off", channel=9, note=36, time=120),
            mido.MetaMessage("end_of_track", time=1800),
        ])]
        midi.save(path)
        return mido.MidiFile(path)

    def timed(self, midi, predicate):
        events = []
        for track in midi.tracks:
            tick = 0
            for message in track:
                tick += message.time
                if predicate(message):
                    events.append((tick, str(message.copy(time=0))))
        return sorted(events)

    def test_percussion_changes_preserve_pitched_events_controllers_tempo_and_duration(self):
        execute = load("execute_child_plans")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.mid"
            baseline = self.midi(path)
            original = path.read_bytes()
            stable = lambda msg: msg.type != "end_of_track" and not (getattr(msg, "channel", None) == 9 and msg.type in ("note_on", "note_off"))
            for operation in ("preserve", "replace"):
                with self.subTest(operation=operation):
                    full, backing = execute.frozen_midis(path, {"baseline_percussion": operation, "events": [[81, 1, .25, 70]]})
                    added_track_name = lambda msg: stable(msg) and not (msg.type == "track_name" and msg.name == "Child percussion additions")
                    self.assertEqual(self.timed(full, added_track_name), self.timed(baseline, stable))
                    drums = [msg.note for track in full.tracks for msg in track if msg.type == "note_on" and msg.channel == 9]
                    self.assertEqual(sorted(drums), [36, 81] if operation == "preserve" else [81])
                    self.assertFalse(any(msg.type == "track_name" and msg.name == "Original melody" for track in backing.tracks for msg in track))
                    self.assertEqual(max(sum(msg.time for msg in tr) for tr in full.tracks), 1920)
                    self.assertEqual(max(sum(msg.time for msg in tr) for tr in backing.tracks), 1920)
                    self.assertEqual(path.read_bytes(), original)

    def test_child_verification_rejects_pitch_and_percussion_drift(self):
        verification = load("verification")
        def parsed(notes):
            return {"ppq": 480, "tracks": [{"notes": notes, "errors": []}]}
        baseline = parsed([(60, 0, 1920, 0, 80), (36, 0, 120, 9, 50)])
        op = {"baseline_percussion": "preserve", "events": [[81, 1, .25, 70]]}
        actual = parsed(baseline["tracks"][0]["notes"] + [(81, 480, 120, 9, 70)])
        verification.check_child_events(actual, baseline, op)
        with self.assertRaisesRegex(ValueError, "Pitched"):
            verification.check_child_events(parsed([(61, 0, 1920, 0, 80)]), baseline, op)
        with self.assertRaisesRegex(ValueError, "percussion"):
            verification.check_child_events(baseline, baseline, op)
        verification.check_backing(actual, parsed([(36, 0, 120, 9, 50), (81, 480, 120, 9, 70)]), 0)
        with self.assertRaisesRegex(ValueError, "precisely"):
            verification.check_backing(actual, baseline, 0)

    def test_frozen_verification_rejects_controller_program_and_pitch_bend_changes(self):
        verification = load("verification")
        execute = load("execute_child_plans")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.mid"
            self.midi(baseline)
            variant = root / "variant.mid"
            full, _ = execute.frozen_midis(baseline, {"baseline_percussion": "replace", "events": [[81, 1, .25, 70]]})
            full.save(variant)
            verification.check_frozen_messages(variant, baseline)
            for message in (mido.Message("control_change", channel=1, control=11, value=12),
                            mido.Message("program_change", channel=1, program=40),
                            mido.Message("pitchwheel", channel=1, pitch=100)):
                with self.subTest(message=message):
                    changed = mido.MidiFile(variant)
                    changed.tracks[2].insert(0, message)
                    path = root / "changed.mid"
                    changed.save(path)
                    with self.assertRaisesRegex(ValueError, "frozen baseline"):
                        verification.check_frozen_messages(path, baseline)

    def test_unsafe_filenames_fail_before_render_outputs(self):
        verification = load("verification")
        render = load("render_child_versions")
        for filename in ("../../../victim", "/absolute/victim", "C:\\victim", "..", "CON"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                folder = root / "arrangement"
                folder.mkdir()
                cfg = {"stem": "song", "id": "01_test", "filename": filename}
                (folder / "parameters.json").write_text(json.dumps(cfg))
                with self.assertRaisesRegex(ValueError, "component"):
                    verification.verify(folder, self.config(root), object())
                fake_renderer = SimpleNamespace(banks=lambda path: {}, CounterRenderer=lambda *args: self.fail("Renderer created before filename validation"))
                with patch.dict(sys.modules, {"sample_renderer": fake_renderer}), patch.object(render, "load_auditor"), patch.object(render, "tool_command", return_value=[sys.executable]), patch.object(render, "resource_path", return_value=root / "external"), patch.object(render, "verify", return_value=(cfg, {})):
                    with self.assertRaisesRegex(ValueError, "component"):
                        render.render([folder], root / "new-render", self.config(root))
                self.assertFalse((root / "new-render").exists())
                self.assertFalse((root / "victim.wav").exists())

    def test_manifest_cannot_be_ancestor_or_descendant_of_variant_directory(self):
        execute = load("execute_child_plans")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            baseline.mkdir()
            for name in ("chords.tsv", "melody.tsv", "upper.tsv", "tracks.tsv"):
                (baseline / name).write_text("")
            (baseline / "input.properties").write_text("\n".join(key + "=test" for key in ("title", "tempo", "bars", "variation", "style", "intensity", "ensemble", "lead", "counter_program", "counter_volume")))
            research = root / "research.json"
            research.write_text("{}")
            planpath = root / "execution_plan.json"
            planpath.write_text(json.dumps({"adapter": "barnsang_percussion_v1", "research_file": str(research), "research_sha256": hashlib.sha256(research.read_bytes()).hexdigest()}))
            (root / "PROMPT.md").write_text("test")
            output = root / "variants"
            variant = {"id": "01_test", "baseline_percussion": "preserve", "events": []}
            plan = {"baseline_folder": str(baseline), "source_sha256": "hash", "output_root": str(output), "song_id": "song", "song_length_beats": 4, "variants": [variant]}
            base = {"stem": "song", "filename": "baseline", "source_sha256": "hash", "ensemble": "duo", "title": "Song", "style": "style", "variation": "Main A-1", "intensity": 0, "room": "studio", "counter_library": "clarinet", "percussion_events": []}
            expected = output / "song" / "01_test"
            for manifest in (output, expected, expected / "folders.json"):
                with self.subTest(manifest=manifest), patch.object(execute, "load_auditor"), patch.object(execute, "tool_command", return_value=[sys.executable]), patch.object(execute, "resource_path", return_value=root), patch.object(execute, "compiler_module", return_value=SimpleNamespace(validate_brief=lambda *args: plan)), patch.object(execute, "verify", return_value=(base, {})), patch.object(execute, "frozen_midis", return_value=(None, None)), patch.object(execute, "compile_java") as compile_java:
                    with self.assertRaisesRegex(ValueError, "separate from variant"):
                        execute.execute([planpath], manifest, self.config(root), runtime={"java": [sys.executable]})
                    compile_java.assert_not_called()
                    self.assertFalse(output.exists())

    def test_shared_gain_preserves_backing_ratio_and_rejects_misalignment(self):
        render = load("render_child_versions")
        class Meter:
            def integrated_loudness(self, data):
                return 20 * np.log10(np.sqrt(np.mean(data ** 2)))
        signal = np.full((480, 2), .2)
        full, backing, gain = render.normalize_pair(signal, signal * .3, Meter(), -18.3)
        np.testing.assert_allclose(backing, full * .3)
        self.assertAlmostEqual(Meter().integrated_loudness(full), -18.3)
        self.assertGreater(gain, 0)
        with self.assertRaisesRegex(ValueError, "frame count"):
            render.normalize_pair(signal, signal[:100], Meter(), -18.3)

    def test_missing_decoder_stops_before_outputs_and_external_tools(self):
        execute = load("execute_child_plans")
        with tempfile.TemporaryDirectory() as directory, patch.object(execute.subprocess, "run") as run:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "resources.midi_audit"):
                execute.execute([], root / "folders.json", self.config(root), runtime={"java": [sys.executable]})
            self.assertEqual(list(root.iterdir()), [])
            run.assert_not_called()

    def test_java_source_compilation_command_uses_external_temp_directory(self):
        execute = load("execute_child_plans")
        with tempfile.TemporaryDirectory(prefix="arrangement tools ") as directory:
            root = Path(directory)
            jar = root / "toolkit.jar"
            jar.write_bytes(b"test stub only, not a real toolkit")
            build = root / "build"
            build.mkdir()
            recorder = root / "compiler.py"
            recorder.write_text("import json, pathlib, sys\na=sys.argv[1:]\np=pathlib.Path(a[a.index('-d')+1])\n(p/'ChildExperiment.class').write_bytes(b'stub')\n(p/'args.json').write_text(json.dumps(a))\n")
            cfg = {**self.config(root), "resources": {"jjazzlab_toolkit": str(jar)}, "tools": {"javac": {"command": [sys.executable, str(recorder)]}}}
            classpath = execute.compile_java(cfg, build, {"javac": [sys.executable, str(recorder)], "environment": dict(os.environ)}, root / "manifest.json")
            args = json.loads((build / "args.json").read_text())
            self.assertEqual(classpath, os.pathsep.join((str(build), str(jar))))
            self.assertIn("-proc:full", args)
            self.assertEqual(args[-1], str(ADAPTER / "ChildExperiment.java"))
            self.assertFalse((ADAPTER / "ChildExperiment.class").exists())

    def test_imports_do_not_load_native_library_or_run_tools(self):
        with patch.object(ctypes, "CDLL", side_effect=AssertionError("native load at import")), patch.object(subprocess, "run", side_effect=AssertionError("tool at import")):
            for name in ("sample_renderer", "render_child_versions", "execute_child_plans", "publish_experiments", "check_delivery", "verification"):
                load(name)

    def test_all_cli_help_from_another_directory(self):
        with tempfile.TemporaryDirectory(prefix="arrangement cwd ") as directory:
            for name in ("execute_child_plans", "render_child_versions", "publish_experiments", "check_delivery"):
                result = subprocess.run([sys.executable, str(ADAPTER / (name + ".py")), "--help"], cwd=directory, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--config-root", result.stdout)

    def test_publisher_builds_two_song_catalogue_without_embedded_experiment_choices(self):
        publisher = load("publish_experiments")
        checker = load("check_delivery")
        with tempfile.TemporaryDirectory(prefix="arrangement publication ") as directory:
            root = Path(directory)
            reports = []
            for song, tempo in (("alpha", 100), ("beta", 80)):
                folder = root / song / "audio"
                arrangement = root / song / "arrangement"
                folder.mkdir(parents=True)
                arrangement.mkdir()
                filename = song + "__01_test"
                cfg = {"stem": song, "id": "01_test", "filename": filename, "title": song.title(), "label": "Test", "axis": "percussion", "tempo": tempo,
                       "meter": "4/4", "variation": "Main A-1", "room": "studio", "style": "test", "intensity": 0, "ensemble": "duo", "composition_notes": "Synthetic comparison"}
                (arrangement / "parameters.json").write_text(json.dumps(cfg))
                for ext in ("mid", "sng", "mix"):
                    (arrangement / (filename + "." + ext)).write_bytes(b"synthetic fixture")
                (arrangement / (filename + "_backing.mid")).write_bytes(b"synthetic backing")
                for name in ("ARRANGEMENT_PROMPT.md", "participation.md"):
                    (arrangement / name).write_text("Synthetic fixture")
                (folder / "CREDITS.md").write_text("Synthetic test tone; no samples")
                for suffix in ("", "_backing"):
                    sf.write(folder / (filename + suffix + ".wav"), np.full((12000, 2), .01), 48000, subtype="PCM_24")
                    (folder / (filename + suffix + ".mp3")).write_bytes(b"stub preview")
                digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
                row = {"folder": str(folder), "arrangement_folder": str(arrangement), "filename": filename, "target_lufs": -18.3, "peak_ceiling_dbtp": -1.5,
                       "final_lufs": -18.3, "final_true_peak_dbtp": -6., "wav_sha256": digest(folder / (filename + ".wav")), "mp3_sha256": digest(folder / (filename + ".mp3")),
                       "verification": {"midi_sha256": digest(arrangement / (filename + ".mid"))}, "backing": {},
                       "routes": {"0": {"library": "synthetic"}}, "libraries": {"synthetic": {"credits": "Test tone"}}, "duration_seconds": .25, "human_listening_review": "pending"}
                for ext in ("wav", "mp3", "mid"):
                    parent = arrangement if ext == "mid" else folder
                    row["backing"][("midi" if ext == "mid" else ext) + "_sha256"] = digest(parent / (filename + "_backing." + ext))
                reports.append(row)
            (root / "scratch").mkdir()
            report = root / "scratch/verification.json"
            report.write_text(json.dumps(reports))
            out = root / "outputs/listening"
            publisher.publish([report], out, self.config(root))
            catalogue = json.loads((out / "catalogue.json").read_text())
            self.assertEqual(set(catalogue), {"alpha", "beta"})
            self.assertEqual(catalogue["beta"]["versions"][0]["tempo"], 80)
            html = (out / "index.html").read_text()
            self.assertNotIn("72 arrangements", html)
            self.assertNotIn("Broder", html)
            (Path(reports[0]["folder"]) / (reports[0]["filename"] + ".mp3")).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                checker.check_files(reports, self.config(root))


if __name__ == "__main__":
    unittest.main()
