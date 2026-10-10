"""Offline image response writing; production image routes remain disabled."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/gen_image.py'
SPEC = importlib.util.spec_from_file_location('image_response_fixture', SCRIPT)
IMAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMAGE)


class ImageResponseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='image response ')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def response(self, payload=b'synthetic image'):
        response = Mock()
        response.headers = {'x-request-id': 'fixture-request-id'}
        response.json.return_value = {'data': [{'b64_json': base64.b64encode(payload).decode(),
                                              'revised_prompt': 'Synthetic response'}],
                                      'created': 123, 'usage': {'fixture': True}}
        return response

    def test_response_records_provider_identity_and_ordered_references(self):
        image, metadata = self.work / 'frame.png', self.work / 'frame.png.json'
        record = {'model': 'fixture', 'refs': ['prior.png', 'character.png']}
        IMAGE.save_response(self.response(), image, metadata, record, time.monotonic())
        self.assertEqual(image.read_bytes(), b'synthetic image')
        payload = json.loads(metadata.read_text())
        self.assertEqual(payload['refs'], ['prior.png', 'character.png'])
        self.assertEqual(payload['provider_request_id'], 'fixture-request-id')
        self.assertIsNone(payload['model_revision'])

    def test_response_refuses_overwrites_and_aliases_before_response_access(self):
        image, metadata = self.work / 'frame.png', self.work / 'frame.png.json'
        metadata.write_text('preserve')
        response = self.response()
        for targets in [(image, metadata), (image, image), (image, image / 'metadata.json')]:
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                IMAGE.save_response(response, *targets, {}, 0)
        response.raise_for_status.assert_not_called()
        self.assertFalse(image.exists())
        self.assertEqual(metadata.read_text(), 'preserve')

    def test_bad_response_creates_no_output(self):
        with self.assertRaisesRegex(ValueError, 'empty image'):
            IMAGE.save_response(self.response(b''), self.work / 'frame.png',
                                self.work / 'frame.png.json', {}, 0)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_live_generation_route_stays_disabled_before_http(self):
        with patch.object(IMAGE.requests, 'post') as post:
            with self.assertRaisesRegex(ValueError, 'Image generation is disabled'):
                IMAGE.main(['--model', 'fixture', '--quality', 'high', '--size', '1024x1024',
                            '--prompt', 'PROMPT.md', '--output', 'frame.png'])
            post.assert_not_called()
