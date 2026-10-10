"""Self-contained listening deliveries pin all hidden source files and retain the HTML."""
import hashlib
import io
import json
from pathlib import Path
import sys
import sysconfig
import tempfile
import unittest
import wave
from uuid import uuid4
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/jjazzlab_experiments'))


from publish_experiments import publish
DELIVERY_SOURCE = Path(__file__).resolve().parents[1] / "scripts/jjazzlab_experiments/publish_experiments.py"
from scripts.read_config import ROOT


def digest(content):
    return hashlib.sha256(content).hexdigest()


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(3)
        output.setframerate(48000)
        output.writeframes(bytes(480 * 2 * 3))
    return buffer.getvalue()


class DeliveryDomainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ld-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        root = self.work / 'd'
        root.mkdir()
        self.data = root
        self.config = {'paths': {'data_root': str(root)}}
        parameters = {'stem': 'song', 'id': 'variant-a', 'filename': 'song-a', 'title': 'Synthetic song',
                      'label': 'Variant A', 'composition_notes': 'Synthetic fixture, not a listening acceptance',
                      'axis': 'tempo', 'tempo': 100, 'meter': '4/4', 'style': 'fixture', 'variation': 'steady',
                      'intensity': 'gentle', 'ensemble': 'fixture', 'room': 'dry'}
        arrangement_files = {'parameters.json': json.dumps(parameters).encode(),
                             'song-a.mid': b'synthetic MIDI placeholder', 'song-a_backing.mid': b'backing MIDI placeholder',
                             'song-a.sng': b'native song placeholder', 'song-a.mix': b'native mix placeholder',
                             'ARRANGEMENT_PROMPT.md': b'Approved synthetic prompt', 'participation.md': b'Participation text'}
        audio_files = {'song-a.wav': wav_bytes(), 'song-a_backing.wav': wav_bytes(),
                       'song-a.mp3': b'synthetic MP3 placeholder', 'song-a_backing.mp3': b'backing MP3 placeholder',
                       'CREDITS.md': b'Synthetic fixture source credits'}
        arrangement = self.import_bundle(arrangement_files, 'arrangement')
        audio = self.import_bundle(audio_files, 'render')
        arrangement_path = arrangement
        audio_path = audio
        row = {'folder': str(audio_path), 'arrangement_folder': str(arrangement_path), 'filename': 'song-a',
               'wav_sha256': digest(audio_files['song-a.wav']), 'mp3_sha256': digest(audio_files['song-a.mp3']),
               'verification': {'midi_sha256': digest(arrangement_files['song-a.mid']), 'fixture_only': True},
               'backing': {'wav_sha256': digest(audio_files['song-a_backing.wav']),
                           'mp3_sha256': digest(audio_files['song-a_backing.mp3']),
                           'midi_sha256': digest(arrangement_files['song-a_backing.mid'])},
               'final_lufs': -18.0, 'target_lufs': -18.0, 'final_true_peak_dbtp': -3.0, 'peak_ceiling_dbtp': -1.0,
               'libraries': {'fixture': {'credits': 'Synthetic fixture only'}}, 'routes': {'piano': {'library': 'fixture'}},
               'duration_seconds': .01, 'human_listening_review': 'Not performed; synthetic bytes'}
        report = self.import_bundle({'render-report.json': json.dumps([row]).encode()}, 'report')
        self.report_path = report / 'render-report.json'
        self.audio_path = audio_path
        self.audio_files = audio_files

    def import_bundle(self, contents, kind):
        directory = self.data / kind
        directory.mkdir()
        for name, content in contents.items():
            (directory / name).write_bytes(content)
        return directory

    def test_delivery_is_self_contained(self):
        output = self.data / 'listening'
        publish([self.report_path], output, self.config)
        catalogue = json.loads((output / 'catalogue.json').read_text())
        links = catalogue['song']['versions'][0]['files']
        for link in links.values():
            path = (output / unquote(link)).resolve()
            self.assertTrue(path.is_relative_to(output))
            self.assertTrue(path.is_file())
        self.assertEqual((output / unquote(links['wav'])).read_bytes(), self.audio_files['song-a.wav'])
        before={path:path.read_bytes() for path in output.rglob('*') if path.is_file()}
        with self.assertRaisesRegex(ValueError, 'must be empty'):
            publish([self.report_path], output, self.config)
        self.assertEqual({path:path.read_bytes() for path in before},before)

    def test_missing_indirect_input_rejects_before_output(self):
        (self.data/'arrangement/participation.md').unlink()
        output=self.data/'listening'
        with self.assertRaisesRegex(ValueError, 'Missing input'):
            publish([self.report_path],output,self.config)
        self.assertFalse(output.exists())

    def test_changed_audio_rejects_before_output(self):
        (self.audio_path/'song-a.wav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            publish([self.report_path],self.data/'listening',self.config)
        self.assertFalse((self.data/'listening').exists())

if __name__=='__main__': unittest.main()
