"""Score conversion publication boundaries with synthetic exporters."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import zipfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / '.agents/skills/artifact-bookkeeping/scripts'))

from artifact_ledger import Ledger, reference
from ledger_execution import prepare, execute, finish
from ledger_tools import conversion_environment
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".agents/skills/download-scores/scripts"))
from convert_score import validate_score_container, preserve_midi_duration


class ScoreConversionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='lc-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'; self.data.mkdir()
        self.tools = self.root / 'tools'; self.tools.mkdir()
        self.ledger = Ledger({'paths': {'data_root': str(self.data), 'resource_cache': str(self.root / 'cache')},
            'resources': {'converter': str(self.tools)},
            'bookkeeping': {'actor_id': 'test', 'host_id': str(uuid4())}})
        self.song = self.ledger.create_song('Test')
        source = self.root / 'scan.pdf'; source.write_bytes(b'%PDF-fixture')
        event = self.ledger.import_files({'scan.pdf': source}, kind='source', label='Scan')
        self.input = {**reference(event['data']['updates'][0]), 'files': ['scan.pdf'], 'purpose': 'OMR'}

    def tool(self, code):
        path = self.tools / 'omr.py'; path.write_text('#!/usr/bin/env python3\n' + code)
        event = self.ledger.register_resource('resources.converter', ['omr.py'], label='Fixture converter',
            version='fixture-1', source={'execution': {'entrypoint': 'omr.py', 'mode': 'python-stdlib'}})
        return reference(event['data']['updates'][0])

    def convert(self, ref, dependency=None, extension='mxl', engine='audiveris'):
        request={'operation':'score-conversion','skill':'download-scores',
            'declaration':'.agents/skills/download-scores/SKILL.md',
            'code':['.agents/skills/download-scores/scripts/convert_score.py'],
            'inputs':{'score':dependency or self.input},'resources':{engine:ref},
            'config':{'tools':{engine:{'command':'{tool:'+engine+'}'}}},
            'outputs':{'result':{'kind':'score-export','label':'Converted score','song_ids':[self.song['song_id']],
                'storage_parent':None,'dependencies':['score'],
                'contract':{'files':[{'path':'score.'+extension,'role':'score'},{'path':'CONVERSION.log','role':'log'}]}}},
            'command':['{python}','{code:.agents/skills/download-scores/scripts/convert_score.py}',
                '{input:score}','--engine',engine,'--out','{output:result/score.'+extension+'}',
                '--log','{output:result/CONVERSION.log}','--scratch','{scratch:conversion}']}
        if engine == 'musescore' and extension == 'mid':
            request['packages']=['music21','mido']
        intent=prepare(self.ledger,request)
        try:
            execute(self.ledger,intent['run_id'])
            event=finish(self.ledger,intent['run_id'])
        except ValueError as exc:
            return None,{'error':str(exc)}
        return reference(event['data']['updates'][0]),None

    def test_omr_separate_checkpoint_keeps_unknown_byproducts_in_workspace(self):
        ref = self.tool('import pathlib,sys\n'
            'out=pathlib.Path(sys.argv[sys.argv.index("-output")+1])\n'
            '(out/"scan.mxl").write_bytes(b"mxl fixture")\n'
            '(out/"scan.omr").write_bytes(b"intermediate fixture")\n')
        result, failed = self.convert(ref)
        self.assertIsNone(failed)
        record = self.ledger.resolve(result['artifact_id'])
        self.assertEqual({file['path'] for file in record['files']}, {'score.mxl', 'CONVERSION.log'})
        self.assertEqual(record['dependencies'], [self.input])
        work = self.data / 'work' / record['producer']['run_id']
        self.assertTrue((work / 'scratch/conversion/generated/scan.omr').is_file())
        before = len(self.ledger.state()['events'])
        self.ledger.recover(record['producer']['run_id'])
        self.assertEqual(len(self.ledger.state()['events']), before)

    def test_generated_symlink_fails_without_publication_or_editing_victim(self):
        victim = self.root / 'victim'; victim.write_bytes(b'original')
        ref = self.tool('import pathlib,sys\n'
            'out=pathlib.Path(sys.argv[sys.argv.index("-output")+1])\n'
            f'(out/"scan.mxl").symlink_to({str(victim)!r})\n')
        result, failed = self.convert(ref)
        self.assertIsNone(result)
        self.assertIn('symbolic link', failed['error'])
        self.assertEqual(victim.read_bytes(), b'original')
        self.assertFalse(any(a['kind'] == 'score-export' for a in self.ledger.state()['artifacts'].values()))

    def test_container_traversal_and_external_image_rejected(self):
        path = self.root / 'source.mxl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('../outside.xml', '<score-partwise/>')
        with self.assertRaisesRegex(ValueError, 'Unsafe path'):
            validate_score_container(path)
        path = self.root / 'source.musicxml'
        path.write_text('<score-partwise><image source="/private/image.png"/></score-partwise>')
        with self.assertRaisesRegex(ValueError, 'External score images'):
            validate_score_container(path)
        path = self.root / 'external.mxl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('score.xml', '<!DOCTYPE score SYSTEM "file:///private/input"><score/>')
        with self.assertRaisesRegex(ValueError, 'DTD/entities'):
            validate_score_container(path)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('score.mscx', '<museScore><Image><path>/private/image.png</path></Image></museScore>')
        with self.assertRaisesRegex(ValueError, 'External score images'):
            validate_score_container(path)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
            archive.writestr('score.xml', '<score><identification><source>Published score</source></identification><image source="Pictures/image.png"/></score>')
            archive.writestr('Pictures/image.png', b'fixture')
        validate_score_container(path)

    def test_converter_receives_private_font_configuration(self):
        (self.tools / 'font.conf').write_text('private font configuration')
        (self.tools / 'omr.py').write_text('#!/usr/bin/env python3\nimport pathlib,sys,os\n'
            'font=pathlib.Path(os.environ["FONTCONFIG_FILE"])\nassert "/cache/" in str(font)\n'
            'assert pathlib.Path(os.environ["FONTCONFIG_SYSROOT"]) == font.parent\n'
            'out=pathlib.Path(sys.argv[sys.argv.index("-output")+1])\n'
            '(out/"scan.mxl").write_text(font.read_text())\n')
        source = {'execution': {'entrypoint': 'omr.py', 'mode': 'python-stdlib'},
                  'conversion': {'closure_review': 'Synthetic explicit font-config consumer',
                                 'environment': {'FONTCONFIG_FILE': 'font.conf', 'FONTCONFIG_SYSROOT': '.'}}}
        event = self.ledger.register_resource('resources.converter', ['omr.py', 'font.conf'],
            label='Configured converter', version='fixture-1', source=source)
        result, failure = self.convert(reference(event['data']['updates'][0]))
        self.assertIsNone(failure)
        record = self.ledger.resolve(result['artifact_id'])
        self.assertEqual((self.data / record['history_path'] / 'score.mxl').read_text(), 'private font configuration')
        source['conversion']['environment']['FONTCONFIG_FILE'] = '../unrecorded'
        with self.assertRaises(ValueError):
            conversion_environment(self.tools, {'source': source, 'files': [{'path': 'font.conf'}]})
        source['conversion']['environment'] = {'FONTCONFIG_SYSROOT': '/usr/share'}
        with self.assertRaises(ValueError):
            conversion_environment(self.tools, {'source': source, 'files': [{'path': 'font.conf'}]})

    def test_midi_export_preserves_repeated_score_tail_and_all_sounding_events(self):
        import importlib.metadata
        import io
        import json
        import mido
        source = self.root / 'repeat.musicxml'
        source.write_text('''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
<barline location="left"><repeat direction="forward"/></barline><note><pitch><step>C</step><octave>4</octave></pitch><duration>3</duration><type>half</type><dot/></note></measure>
<measure number="2"><note><pitch><step>D</step><octave>4</octave></pitch><duration>3</duration><type>half</type><dot/></note><barline location="right"><repeat direction="backward"/></barline></measure>
<measure number="3"><note><rest measure="yes"/><duration>3</duration></note></measure></part></score-partwise>''')
        original = source.read_bytes()
        imported = self.ledger.import_files({'repeat.musicxml': source}, kind='score', label='Repeated score')
        dependency = {**reference(imported['data']['updates'][0]), 'files': ['repeat.musicxml'], 'purpose': 'source'}
        midi = mido.MidiFile(ticks_per_beat=480)
        midi.tracks.append(mido.MidiTrack())
        for i, pitch in enumerate((60, 62, 60, 62)):
            midi.tracks[0].append(mido.Message('note_on', note=pitch, time=0 if i == 0 else 1))
            midi.tracks[0].append(mido.Message('note_off', note=pitch, time=1439))
        midi.tracks[0].append(mido.MetaMessage('end_of_track', time=1))
        blob = io.BytesIO(); midi.save(file=blob)
        tool = self.tool('import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_bytes(' + repr(blob.getvalue()) + ')\n')
        self.ledger.config['resources']['python_packages'] = str(importlib.metadata.distribution('music21').locate_file(''))
        result, failure = self.convert(tool, dependency, extension='mid', engine='musescore')
        self.assertIsNone(failure)
        record = self.ledger.resolve(**{key: result[key] for key in ('artifact_id', 'revision_id')})
        output = self.data / record['history_path']
        exported = mido.MidiFile(output / 'score.mid')
        self.assertEqual(sum(message.time for message in exported.tracks[0]), 15 * 480)
        self.assertEqual(exported.tracks[0][:-1], midi.tracks[0][:-1])
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(len(record['producer']['resources']), 2)
        report = json.loads((output / 'CONVERSION.log').read_text().strip())
        self.assertEqual(report['original_track_end_ticks'], [12 * 480])
        from types import SimpleNamespace
        from unittest.mock import patch
        exported.tracks[0][-1].time += 1
        longer = self.root / 'longer.mid'; exported.save(longer)
        before = longer.read_bytes()
        with self.assertRaisesRegex(ValueError, 'refusing to truncate'):
            preserve_midi_duration(SimpleNamespace(score=source, midi=longer))
        self.assertEqual(longer.read_bytes(), before)

    def test_pdf_review_pages_pin_input_renderer_and_executed_code(self):
        import json
        import subprocess
        import sys
        tool = self.tool('import pathlib,sys\n'
                         'assert "/cache/" in __file__\n'
                         'assert "work" in pathlib.Path(sys.argv[-2]).parts\n'
                         'assert pathlib.Path(sys.argv[-2]).read_bytes()==b"%PDF-fixture"\n'
                         'for page in (1,2): pathlib.Path(sys.argv[-1]+f"-{page}.png").write_bytes(b"\\x89PNG\\r\\n\\x1a\\nfixture")\n')
        script = Path(__file__).resolve().parents[4] / '.agents/skills/score-to-musicxml/scripts/render_pdf.py'
        original = self.ledger.resolve(self.input['artifact_id'], self.input['revision_id'])
        pdf = self.data / original['history_path'] / 'scan.pdf'
        request={'operation':'pdf-review','skill':'score-to-musicxml',
            'declaration':'.agents/skills/score-to-musicxml/SKILL.md',
            'code':['.agents/skills/score-to-musicxml/scripts/render_pdf.py'],
            'inputs':{'pdf':self.input},'resources':{'pdftoppm':tool},
            'config':{'tools':{'pdftoppm':{'command':'{tool:pdftoppm}'}}},
            'outputs':{'result':{'kind':'review-pages','label':'PDF review','song_ids':[],
                'storage_parent':None,'dependencies':['pdf'],
                'contract':{'files':[{'path':'pages/'+name,'role':'review'} for name in ['page-1.png','page-2.png','RENDER.log']]}}},
            'command':['{python}','{code:.agents/skills/score-to-musicxml/scripts/render_pdf.py}',
                       '{input:pdf}','--out','{output:result/pages}']}
        intent=prepare(self.ledger,request)
        execute(self.ledger,intent['run_id'])
        finish(self.ledger,intent['run_id'])
        artifact = next(a for a in self.ledger.state()['artifacts'].values() if a['kind']=='review-pages')
        record = self.ledger.resolve(artifact['artifact_id'])
        self.assertEqual({f['path'] for f in record['files']}, {'pages/page-1.png','pages/page-2.png','pages/RENDER.log'})
        self.assertEqual(record['dependencies'], [self.input])
        self.assertEqual(record['producer']['resources'], [tool])
        self.assertIn(script.relative_to(script.parents[4]).as_posix(), [f['path'] for f in record['producer']['code']['files']])
        self.assertEqual(pdf.read_bytes(), b'%PDF-fixture')


if __name__ == '__main__':
    unittest.main()
