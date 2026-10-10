"""Exercise the imported arrangement brief contract without external tools."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest



REPO = Path(__file__).resolve().parents[4]
COMPILER = REPO / ".agents/skills/song-arrangement-research/scripts/compile_brief.py"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ImportedBriefTests(unittest.TestCase):
    def make_inputs(self, work):
        (work / "config.toml").write_text("[paths]\ndata_root = " + json.dumps(str(work.resolve())) + "\n")
        source = work / "source.musicxml"
        source.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<score-partwise version="4.0"><part-list><score-part id="P1">'
            '<part-name>Piano</part-name></score-part></part-list><part id="P1">'
            '<measure number="1"><attributes><divisions>1</divisions>'
            '<time><beats>4</beats><beat-type>4</beat-type></time></attributes>'
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>4</duration><type>whole</type></note>'
            '</measure></part></score-partwise>', encoding="utf-8",
        )
        baseline = work / "baseline"
        baseline.mkdir()
        midi = baseline / "baseline.mid"
        # Format 0, 480 ticks/beat; one middle C held for four beats.
        midi.write_bytes(bytes.fromhex(
            "4d546864 00000006 0000 0001 01e0"
            "4d54726b 0000000d 00 903c40 8f00 803c00 00 ff2f00"
        ))
        parameters = baseline / "parameters.json"
        parameters.write_text(json.dumps({
            "stem": "test_song", "filename": "baseline", "meter": "4/4", "bars": 1,
        }))
        research = work / "research.json"
        research.write_text(json.dumps({
            "song_id": "test_song", "evidence": [{"id": "test_evidence"}],
        }))
        brief = work / "brief.json"
        brief.write_text(json.dumps({
            "song_id": "test_song", "vocals": "user_supplied",
            "audience": {"age_min": 2, "age_max": 8, "context": "group singing"},
            "invariants": ["Preserve the source melody"],
            "source_xml": str(source), "source_sha256": sha256(source),
            "baseline_folder": str(baseline), "baseline_midi_sha256": sha256(midi),
            "output_root": str(work / "arrangement variants"),
            "variants": [{
                "id": "01_simple", "axis": "percussion", "label": "Simple pulse",
                "rationale": "Support the beat", "evidence_ids": ["test_evidence"],
                "baseline_percussion": "preserve", "events": [[36, 0, 1, 80]],
                "participation_windows": [[0, 4]],
            }],
        }))
        return source, midi, parameters, research, brief

    def run_compiler(self, work, brief, research):
        runner = work / "separate_working_directory"
        runner.mkdir()
        return subprocess.run(
            [sys.executable, str(COMPILER), str(brief), str(research),
             "--out", str(work / "compiled"), "--config-root", str(work)],
            cwd=runner, capture_output=True, text=True,
        )

    def test_compile_from_another_directory_preserves_inputs_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "song with spaces"
            work.mkdir()
            inputs = self.make_inputs(work)
            source, midi, parameters, research, brief = inputs
            original = {path: path.read_bytes() for path in inputs}
            result = self.run_compiler(work, brief, research)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads((work / "compiled/execution_plan.json").read_text())
            self.assertEqual(plan["song_length_beats"], 4)
            self.assertEqual(plan["adapter"], "barnsang_percussion_v1")
            self.assertEqual(plan["research_file"], str(research.resolve()))
            self.assertEqual(plan["research_sha256"], sha256(research))
            self.assertEqual(plan["source_sha256"], sha256(source))
            self.assertEqual(plan["baseline_midi_sha256"], sha256(midi))
            self.assertEqual(plan["variants"], json.loads(brief.read_text())["variants"])
            prompt = (work / "compiled/PROMPT.md").read_text()
            self.assertIn("test_song", prompt)
            self.assertIn("01_simple", prompt)
            self.assertEqual({path: path.read_bytes() for path in inputs}, original)

    def test_existing_destination_and_input_alias_are_preserved(self):
        for alias in (False, True):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory(prefix="brief å space ") as directory:
                work=Path(directory)
                inputs=self.make_inputs(work)
                source,midi,parameters,research,brief=inputs
                out=brief if alias else work/"compiled"
                if not alias:
                    out.mkdir(); (out/"PROMPT.md").write_text("original")
                before={path:path.read_bytes() for path in inputs}
                result=subprocess.run([sys.executable,str(COMPILER),str(brief),str(research),
                    "--out",str(out),"--config-root",str(work)],text=True,capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual({path:path.read_bytes() for path in before},before)
                if not alias: self.assertEqual((out/"PROMPT.md").read_text(),"original")

    def test_rejects_stale_inputs_and_invalid_events_before_writing_outputs(self):
        for invalid in ("source_changed", "midi_changed", "event_out_of_bounds",
                        "unsupported_percussion"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                inputs = self.make_inputs(work)
                source, midi, parameters, research, brief = inputs
                if invalid == "source_changed":
                    source.write_bytes(source.read_bytes() + b"\n")
                elif invalid == "midi_changed":
                    changed = bytearray(midi.read_bytes())
                    changed[12:14] = bytes.fromhex("00f0")  # Still valid MIDI, new PPQ.
                    midi.write_bytes(changed)
                else:
                    data = json.loads(brief.read_text())
                    if invalid == "event_out_of_bounds":
                        data["variants"][0]["events"] = [[36, 3.5, 1, 80]]
                    else:
                        data["variants"][0]["baseline_percussion"] = "unsupported"
                    brief.write_text(json.dumps(data))
                original = {path: path.read_bytes() for path in inputs}
                result = self.run_compiler(work, brief, research)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ValueError", result.stderr)
                self.assertFalse((work / "compiled").exists())
                self.assertEqual({path: path.read_bytes() for path in inputs}, original)


if __name__ == "__main__":
    unittest.main()
