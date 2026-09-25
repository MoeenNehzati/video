"""Smoke-check relocated scripts without models or private score fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[1]


class SkillEntrypointTests(unittest.TestCase):
    def test_lyrics_entrypoints_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            lyrics = work / "lyrics.txt"
            lyrics.write_text("Twin-kle lit-tle star\n", encoding="utf-8")
            entries = [
                [str(REPO / "bin/syllabify_lyrics")],
                [sys.executable, str(REPO / ".agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py")],
                [sys.executable, str(REPO / ".claude/skills/syllabify_lyrics/scripts/syllabify_lyrics.py")],
            ]
            for entry in entries:
                with self.subTest(entry=entry):
                    output = work / "lyrics.json"
                    subprocess.run(entry + [str(lyrics), "--out", str(output)], cwd=work, check=True, capture_output=True)
                    line = json.loads(output.read_text())["lyrics"]["lines"][0]
                    self.assertEqual(line["syllables"], ["Twin", "kle", "lit", "tle", "star"])
                    self.assertEqual(line["syllable_count"], 5)

    def test_arranger_with_synthetic_score(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "input.musicxml"
            notes = "".join(
                f"<note><pitch><step>{step}</step><octave>4</octave></pitch>"
                "<duration>4</duration><type>quarter</type></note>"
                for step in ("C", "D", "E", "G")
            )
            source.write_text(
                '<score-partwise version="3.1"><part-list><score-part id="P1">'
                '<part-name>Piano</part-name></score-part></part-list><part id="P1">'
                '<measure number="1"><attributes><divisions>4</divisions>'
                '<key><fifths>0</fifths><mode>major</mode></key>'
                '<time><beats>4</beats><beat-type>4</beat-type></time>'
                '<clef><sign>G</sign><line>2</line></clef></attributes>'
                '<direction><sound tempo="120"/></direction>' + notes + '</measure>'
                + ''.join(f'<measure number="{i}">{notes}</measure>' for i in range(2, 5))
                + '</part></score-partwise>', encoding="utf-8"
            )
            original = source.read_bytes()
            output = work / "arranged.musicxml"
            result = subprocess.run(
                [sys.executable, str(REPO / ".agents/skills/arrange-score/scripts/arrange_score.py"),
                 str(source), "--goal", "add violin", "--preset", "none", "--target-key", "keep",
                 "--tempo", "keep", "--add-instruments", "violin", "--output", str(output), "--print-summary"],
                cwd=work, check=True, capture_output=True, text=True,
            )
            score = ET.parse(output).getroot()
            self.assertEqual(len(score.findall("part")), 2)
            self.assertIn("Violin", json.loads(result.stdout)["parts_added"])
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
