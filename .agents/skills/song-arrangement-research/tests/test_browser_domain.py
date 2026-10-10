"""Local delivery browser guards; no real browser qualification."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/jjazzlab_experiments'))
from check_delivery import check_page

class BrowserDomainTests(unittest.TestCase):
    def test_existing_output_prevents_browser_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); out=root/'report.json';out.write_text('original')
            with self.assertRaisesRegex(ValueError,'already exists'):
                check_page(root,{},['browser'],{},out=out)
            self.assertEqual(out.read_text(),'original')

    def test_profile_override_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaisesRegex(ValueError,'profile must remain private'):
                check_page(root,{},['browser','--user-data-dir=/external'],{},out=root/'report.json')

    def test_external_link_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'catalogue.json').write_text(json.dumps({'song':{'versions':[{'files':{'mp3':'https://example.com/audio.mp3'}}]}}))
            with self.assertRaisesRegex(ValueError,'local files'):
                check_page(root,{'paths':{'data_root':str(root)}},['browser'],{},out=root/'report.json')
