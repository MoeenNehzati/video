"""Ordinary acquisition/conversion fixtures; no live network or native backend."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'

def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='download å ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        (self.root/'config.toml').write_text('[paths]\ndata_root='+json.dumps(str(self.data))+'\n')
        self.stage = load('download_scores')

    def run_stage(self, *args):
        self.stage.main([*map(str,args),'--config-root',str(self.root)])

    def test_explicit_download_receipt_and_no_clobber(self):
        raw = self.root/'external.musicxml'
        raw.write_bytes(b'<score-partwise/>')
        source = self.data/'source.musicxml'
        receipt = self.data/'receipt.json'
        self.run_stage('download',raw.as_uri(),'--title','Fixture','--out',source,'--receipt',receipt)
        self.assertEqual(source.read_bytes(),raw.read_bytes())
        self.assertEqual(json.loads(receipt.read_text())['requested_url'],raw.as_uri())
        with patch.object(self.stage,'_download') as network, self.assertRaises(ValueError):
            self.run_stage('download',raw.as_uri(),'--title','Fixture','--out',source,'--receipt',receipt)
        network.assert_not_called()
        self.assertEqual(source.read_bytes(),raw.read_bytes())

    def test_output_alias_fails_before_network(self):
        with patch.object(self.stage,'_download') as network, self.assertRaises(ValueError):
            self.run_stage('download','https://example.invalid','--title','Fixture','--out','same','--receipt','same')
        network.assert_not_called()
        self.assertFalse((self.data/'same').exists())

    def test_extraction_quality_and_raw_preservation(self):
        raw = self.data/'raw.txt'
        text = 'This is a long lyric line with singing children\nAnother line repeats the melody and words\nAnd the final line completes this little song\n'
        raw.write_text(text)
        self.run_stage('extract',raw,'--title','Fixture','--url','https://example.invalid','--out','lyrics.txt')
        self.assertEqual(raw.read_text(),text)
        self.assertTrue((self.data/'lyrics.txt').read_text().endswith('\n'))
        raw.write_text('<script>bad</script>')
        with self.assertRaises(ValueError):
            self.run_stage('extract',raw,'--title','Fixture','--url','https://example.invalid','--out','failed.txt')
        self.assertFalse((self.data/'failed.txt').exists())

    def test_protected_catalogue_skips_search(self):
        source = self.data/'catalogue.csv'
        source.write_text('number,title,status,format,url,source\n1,Protected,SKYDDAD,MIDI,https://example.invalid/test.mid,fixture\n')
        # Use the domain row directly so catalogue column aliases do not obscure this gate.
        row = self.stage.Row(number='1',title='Protected',composer_or_origin='',status='SKYDDAD',fmt='MIDI',url='https://example.invalid/test.mid',source='fixture')
        with patch.object(self.stage,'_read_rows',return_value=[row]), patch.object(self.stage,'_candidate_urls_for_song') as search:
            self.run_stage('catalogue',source,'--out','candidates.json','--search-direct')
        search.assert_not_called()
        self.assertEqual(json.loads((self.data/'candidates.json').read_text())[0]['skipped'],'SKYDDAD')

    def test_conversion_rejects_external_score_before_tool(self):
        converter = load('convert_score')
        source = self.data/'score.musicxml'
        source.write_text('<score-partwise><image source="outside.png"/></score-partwise>')
        with self.assertRaisesRegex(ValueError,'External score'):
            converter.main([str(source),'--out','out.pdf','--log','conversion.log','--scratch','scratch','--config-root',str(self.root)])
        self.assertFalse((self.data/'scratch').exists())

    def test_conversion_writes_explicit_output_and_preserves_source(self):
        converter = load('convert_score')
        source = self.data/'score.mid'; source.write_bytes(b'MThd fixture')
        tool = self.root/'tool.py'
        tool.write_text('import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_bytes(b"%PDF fixture")\n')
        with (self.root/'config.toml').open('a') as stream:
            stream.write('[tools.musescore]\ncommand='+json.dumps([sys.executable,str(tool)])+'\n')
        args=[str(source),'--out','out.pdf','--log','conversion.log','--scratch','scratch','--config-root',str(self.root)]
        converter.main(args)
        self.assertEqual((self.data/'out.pdf').read_bytes(),b'%PDF fixture')
        self.assertEqual(source.read_bytes(),b'MThd fixture')
        with self.assertRaises(ValueError):
            converter.main(args)

    def test_conversion_container_and_trailing_silence_checks(self):
        import zipfile
        import mido
        from music21 import stream, note, meter
        from types import SimpleNamespace
        converter=load('convert_score')
        unsafe=self.data/'unsafe.mxl'
        with zipfile.ZipFile(unsafe,'w') as archive:
            archive.writestr('../outside.xml','<score-partwise/>')
        with self.assertRaisesRegex(ValueError,'Unsafe path'):
            converter.validate_score_container(unsafe)
        score=stream.Score(); part=stream.Part(); measure=stream.Measure(number=1)
        measure.append(meter.TimeSignature('4/4')); measure.append(note.Note('C4',quarterLength=1))
        measure.append(note.Rest(quarterLength=3)); part.append(measure); score.append(part)
        source=self.data/'score.musicxml'; score.write('musicxml',fp=source)
        midi=mido.MidiFile(ticks_per_beat=480)
        track=mido.MidiTrack(); midi.tracks.append(track)
        track.extend([mido.Message('note_on',note=60,time=0),mido.Message('note_off',note=60,time=480),mido.MetaMessage('end_of_track',time=0)])
        destination=self.data/'score.mid'; midi.save(destination)
        converter.preserve_midi_duration(SimpleNamespace(score=source,midi=destination))
        result=mido.MidiFile(destination)
        self.assertEqual(sum(message.time for message in result.tracks[0]),1920)
        self.assertEqual(result.tracks[0][1].time,480)
        self.assertEqual(result.tracks[0][-1].time,1440)
        result.tracks[0][-1].time=2000; result.save(destination)
        before=destination.read_bytes()
        with self.assertRaisesRegex(ValueError,'refusing to truncate'):
            converter.preserve_midi_duration(SimpleNamespace(score=source,midi=destination))
        self.assertEqual(destination.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
