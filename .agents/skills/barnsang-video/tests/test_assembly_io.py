"""Ordinary assembly CLI destination checks, independent of bookkeeping."""
import json
from pathlib import Path
import subprocess
import sys

from score_video_fixture import ScoreVideoFixture

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/assemble_flow.py'


class AssemblyIOTests(ScoreVideoFixture):
    def setUp(self):
        super().setUp()
        self.install_media_stubs()
        self.json_file('settings.json', {
            'source_bpm': 120, 'target_bpm': 120, 'beats_per_bar': 4,
            'verse_bars': 2, 'interlude_bars': 0, 'verse_groups': [['a']],
            'width': 320, 'height': 240, 'fps': 24,
        })
        self.json_file('nested/clips.json', [{'id': 'a', 'file': 'clip.mp4'}])
        (self.data / 'clip.mp4').write_text('4')
        (self.data / 'audio.wav').write_text('8')

    def assemble(self, output='film.mp4', prepared='prepared.wav', timeline='timeline.json'):
        return subprocess.run([
            sys.executable, str(SCRIPT), '--config-root', str(self.config),
            '--song-config', 'settings.json', '--clips', 'nested/clips.json',
            '--audio', 'audio.wav', '--output', output, '--output-audio', prepared,
            '--timeline', timeline,
        ], cwd=self.other, capture_output=True, text=True)

    def test_standalone_resolves_embedded_clip_relative_to_data_root(self):
        result = self.assemble()
        self.assertEqual(result.returncode, 0, result.stderr)
        timeline = json.loads((self.data / 'timeline.json').read_text())
        self.assertEqual(timeline['clips'][0]['path'], str(self.data / 'clip.mp4'))
        for key in ('audio', 'film', 'prepared_audio'):
            self.assertTrue(Path(timeline[key]).is_file())
        self.assertFalse((self.data / 'ledger').exists())

    def test_destination_alias_existing_and_parent_conflicts_stop_before_encoding(self):
        for outputs in [('film.mp4', 'film.mp4', 'timeline.json'),
                        ('clip.mp4', 'prepared.wav', 'timeline.json'),
                        ('film.mp4', 'audio.wav', 'timeline.json'),
                        ('film.mp4', 'prepared.wav', 'settings.json'),
                        ('film.mp4', 'film.mp4/prepared.wav', 'timeline.json')]:
            with self.subTest(outputs=outputs):
                result = self.assemble(*outputs)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.tool_log.exists())
                self.assertFalse((self.data / 'film.mp4').exists())
        self.assertEqual((self.data / 'clip.mp4').read_text(), '4')
        self.assertEqual((self.data / 'audio.wav').read_text(), '8')
