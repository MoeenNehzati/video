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


REPO = Path(__file__).resolve().parents[4]
SCORE = REPO / ".agents/skills/score-to-musicxml/scripts"
VIDEO = REPO / ".agents/skills/barnsang-video/scripts"


from score_video_fixture import ScoreVideoFixture, load_module


class ScoreAdapterTests(ScoreVideoFixture):
    def test_canonical_review_needs_no_schema_package(self):
        score = self.data / "score.musicxml"
        score.write_text('<score-partwise><part id="P1"><measure number="1">'
                         '<note><rest measure="yes"/><duration>4</duration><type>whole</type></note>'
                         '</measure></part></score-partwise>', encoding="utf-8")
        result = subprocess.run([sys.executable, "-I", "-c", '''
import runpy, sys
sys.modules["lxml"] = None
validator = runpy.run_path(sys.argv[1])
items = validator["canonical"](sys.argv[2])
assert items[0][0] == "note" and items[0][6] is True
assert items[1][0] == "measure_rest"
assert validator["audit"](sys.argv[2])["issues"] == []
try:
    validator["audit"](sys.argv[2], "schema-required.xsd")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("XSD validation must still require lxml")
''', str(SCORE / "validate.py"), str(score)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_canonical_distinguishes_whole_measure_rest_without_changing_duration(self):
        validator = load_module(SCORE / "validate.py", "rest_validator_test")
        score = self.data / "rest.musicxml"
        xml = '<score-partwise><part id="P1"><measure number="1"><note><rest%s/><duration>3</duration></note></measure></part></score-partwise>'
        score.write_text(xml % ' measure="yes"')
        whole = validator.canonical(score)
        score.write_text(xml % '')
        ordinary = validator.canonical(score)
        self.assertEqual(whole[0], ordinary[0])
        self.assertNotEqual(whole, ordinary)
        score.write_text(xml % ' measure="no"')
        self.assertEqual(validator.canonical(score), ordinary)

    def test_score_schema_source_counts_and_full_file_reference_guard(self):
        score = self.data / "score.musicxml"
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
</measure></part></score-partwise>'''
        score.write_text(xml, encoding="utf-8")
        self.json_file("expectations.json", {"counts": {"measures": 1, "notes": 1}})
        result = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--expectations", "expectations.json")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(json.loads(result.stdout)["source_fidelity_certified"])
        self.json_file("expectations.json", {"counts": {"harmonies": 1}})
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--expectations", "expectations.json")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("completeness harmonies", failed.stdout)
        validator = load_module(SCORE / "validate.py", "score_validator_test")
        self.json_file("reference.json", validator.canonical(score))
        reviewed_hash = hashlib.sha256(score.read_bytes()).hexdigest()
        score.write_text(xml.replace("<part-list>", "<credit><credit-words>Changed credit</credit-words></credit><part-list>"), encoding="utf-8")
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml", "--reference", "reference.json",
                              "--reviewed-sha256", reviewed_hash)
        self.assertNotEqual(failed.returncode, 0)
        report = json.loads(failed.stdout)
        self.assertTrue(report["reviewed_reference_matches"])
        self.assertFalse(report["reviewed_file_matches"])
        score.write_text(xml.replace("<step>C</step>", "<step>H</step>"), encoding="utf-8")
        failed = self.run_cli(SCORE / "verify_score.py", "score.musicxml")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("schema:", failed.stdout)

    def test_slope_geometry_uses_source_and_explicit_output(self):
        import cv2
        import numpy as np
        original = np.full((400, 1600, 3), 255, dtype=np.uint8)
        for index in range(5):
            cv2.line(original, (100, 150 + index * 12), (1500, 190 + index * 12), (0, 0, 0), 2)
        source = self.data / "source.png"
        self.assertTrue(cv2.imwrite(str(source), original))
        before = source.read_bytes()
        self.json_file("seeds.json", [[100, 1500, 150, 190, 12, 12]])
        result = self.run_cli(SCORE / "slope_grid.py", "source.png", "seeds.json", "geometry")
        self.assertEqual(result.returncode, 0, result.stderr)
        geometry = json.loads((self.data / "geometry/geometry.json").read_text())
        self.assertTrue(geometry["systems"][0]["accepted_geometry"])
        self.assertEqual(geometry["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(source.read_bytes(), before)
        self.assertTrue((self.data / "geometry/system_1_grid.png").exists())


    def test_geometry_refuses_existing_output_and_source_alias(self):
        source = self.data/'source.png'; source.write_bytes(b'keep source')
        self.json_file('seeds.json', [[0,100,10,10,5,5]])
        output=self.data/'geometry'; output.mkdir(); (output/'keep').write_bytes(b'keep')
        for destination in ('geometry','source.png'):
            result=self.run_cli(SCORE/'slope_grid.py','source.png','seeds.json',destination)
            self.assertNotEqual(result.returncode,0)
        self.assertEqual(source.read_bytes(),b'keep source')
        self.assertEqual((output/'keep').read_bytes(),b'keep')

    def test_pdf_renderer_explicit_command_and_no_clobber(self):
        source=self.data/'source.pdf'; source.write_bytes(b'%PDF fixture')
        tool=self.root/'render.py'
        tool.write_text('import pathlib,sys\npathlib.Path(sys.argv[-1]+"-1.png").write_bytes(bytes.fromhex("89504e470d0a1a0a"))\n')
        with self.local.open('a') as stream:
            stream.write('[tools.pdftoppm]\ncommand='+json.dumps([sys.executable,str(tool)])+'\n')
        args=('source.pdf','--out','pages')
        result=self.run_cli(SCORE/'render_pdf.py',*args)
        self.assertEqual(result.returncode,0,result.stderr)
        page=self.data/'pages/page-1.png'
        before=page.read_bytes()
        self.assertTrue((self.data/'pages/RENDER.log').exists())
        result=self.run_cli(SCORE/'render_pdf.py',*args)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(page.read_bytes(),before)
