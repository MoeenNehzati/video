"""Run a canonical skill directly, without shell wrappers or discovery aliases."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]


class SkillEntrypointTests(unittest.TestCase):
    def test_lyrics_entrypoint_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            data = work / 'data with spaces'
            data.mkdir()
            (work / 'config.toml').write_text('[paths]\ndata_root = ' + json.dumps(str(data)) + '\n')
            lyrics = data / 'lyrics.txt'
            lyrics.write_text('Twin-kle lit-tle star\n', encoding='utf-8')
            output = data / 'lyrics.json'
            result = subprocess.run([
                sys.executable, str(REPO / '.agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py'),
                str(lyrics), '--out', str(output), '--config-root', str(work),
            ], cwd=work, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            line = json.loads(output.read_text())['lyrics']['lines'][0]
            self.assertEqual(line['syllables'], ['Twin', 'kle', 'lit', 'tle', 'star'])
            self.assertEqual(line['syllable_count'], 5)
            self.assertEqual(lyrics.read_text(), 'Twin-kle lit-tle star\n')

    def test_existing_output_and_input_alias_preserve_bytes(self):
        with tempfile.TemporaryDirectory(prefix='lyrics å ') as directory:
            root = Path(directory)
            data = root / 'data'; data.mkdir()
            (root/'config.toml').write_text('[paths]\ndata_root='+json.dumps(str(data))+'\n')
            source=data/'lyrics.txt'; source.write_text('La-la\n')
            output=data/'output.json'; output.write_bytes(b'keep')
            for destination, expected in ((source,b'La-la\n'),(output,b'keep')):
                result=subprocess.run([sys.executable,str(REPO/'.agents/skills/syllabify_lyrics/scripts/syllabify_lyrics.py'),
                    str(source),'--out',str(destination),'--config-root',str(root)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(destination.read_bytes(),expected)


if __name__ == '__main__':
    unittest.main()
