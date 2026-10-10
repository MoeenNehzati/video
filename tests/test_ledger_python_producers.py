"""Ordinary domain CLIs executed through the generic immutable command boundary."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / '.agents/skills'
sys.path.insert(0, str(SKILLS/'artifact-bookkeeping/scripts'))
from artifact_ledger import Ledger, LedgerError, reference
from ledger_execution import prepare, execute, finish, status


class PythonProducerTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='domain å ')
        self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name)
        self.data=self.directory/'data with spaces'; self.data.mkdir()
        self.config={'paths': {'data_root': str(self.data), 'resource_cache': str(self.directory/'cache')},
            'resources': {'python_packages': str(Path(importlib.metadata.distribution('music21').locate_file('')).resolve())},
            'bookkeeping': {'actor_id': 'fixture','host_id': str(uuid4())}}
        self.ledger=Ledger(self.config)

    def register(self, filename, content, dependencies=None):
        path=self.data/filename; path.write_bytes(content)
        event=self.ledger.import_files({filename:path},kind='source',label=filename,dependencies=dependencies or [])
        return path,{**reference(event['data']['updates'][0]),'files':[filename],'purpose':'fixture-input'}

    def operation(self, skill, script, inputs, files, args, packages=()):
        folder=SKILLS/skill
        code=sorted(str(path.relative_to(REPO)) for path in (folder/'scripts').glob('*.py'))
        if (folder/'schema').exists():
            code.extend(str(path.relative_to(REPO)) for path in (folder/'schema').glob('*.xsd'))
        return {'operation':'domain-fixture','skill':skill,'declaration':str((folder/'SKILL.md').relative_to(REPO)),
            'code':code,'inputs':inputs,'packages':list(packages),
            'outputs':{'result':{'kind':'result','label':'Domain result','song_ids':[], 'storage_parent':None,
                'dependencies':list(inputs),'contract':{'files':[{'path':name,'role':'result'} for name in files]}}},
            'command':['{python}','{code:'+str((folder/'scripts'/script).relative_to(REPO))+'}',*args]}

    def run_operation(self, request):
        intent=prepare(self.ledger,request)
        execute(self.ledger,intent['run_id'])
        event=finish(self.ledger,intent['run_id'])
        update=event['data']['updates'][0]
        record=self.ledger.resolve(update['artifact_id'],update['revision']['revision_id'])
        return self.data/record['history_path'],record,intent

    def tool(self, code):
        folder=self.directory/'tool'; folder.mkdir()
        path=folder/'tool.py'; path.write_text('#!/usr/bin/env python3\n'+code)
        self.config['resources']['tool']=str(folder)
        event=self.ledger.register_resource('resources.tool',['tool.py'],label='Synthetic backend',version='fixture',
            source={'execution':{'entrypoint':'tool.py','mode':'python-stdlib'}})
        return reference(event['data']['updates'][0])

    def fixture_score(self):
        return b'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type><sound tempo="120"/></direction>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
</measure></part></score-partwise>'''

    def test_analysis_alignment_use_frozen_runtime_and_inputs(self):
        source,score=self.register('score.musicxml',self.fixture_score())
        request=self.operation('analyze_music','analyze_music.py',{'arranged_score':score},['analysis.json'],
            ['{input:arranged_score}','--out','{output:result/analysis.json}'],['music21'])
        directory,record,intent=self.run_operation(request)
        self.assertEqual(record['dependencies'],[score])
        self.assertEqual(len(record['producer']['resources']),1)
        analysis={**{key:record[key] for key in ('artifact_id','revision_id')},'files':['analysis.json'],'purpose':'analysis'}
        _,lyrics=self.register('lyrics.json',json.dumps({'lyrics':{'language':'English','lines':[{'id':'l1','syllables':['Sun','shine']}]}}).encode())
        request=self.operation('plan_vocals','plan_and_align_vocals.py',
            {'music_analysis_json':analysis,'lyrics_json':lyrics,'score':score},['events.json'],
            ['{input:music_analysis_json}','{input:lyrics_json}','--score','{input:score}','--out','{output:result/events.json}'],['music21'])
        request['relations']=[{'input':'music_analysis_json','depends_on':'score'}]
        directory,record,_=self.run_operation(request)
        events=json.loads((directory/'events.json').read_text())['vocal_events']
        self.assertEqual([event['pitch'] for event in events],['C4','D4','E4','G4'])
        self.assertEqual([event['lyric'] for event in events if not event['is_slur']],['Sun','shine'])
        self.assertEqual(len(record['dependencies']),3)
        self.assertEqual(source.read_bytes(),self.fixture_score())

    def test_score_report_uses_isolated_lxml(self):
        _,score=self.register('score.musicxml',self.fixture_score())
        request=self.operation('score-to-musicxml','verify_score.py',{'score':score},['report.json'],
            ['{input:score}','--output','{output:result/report.json}'],['lxml'])
        directory,record,_=self.run_operation(request)
        self.assertFalse(json.loads((directory/'report.json').read_text())['issues'])
        self.assertEqual(len(record['producer']['resources']),1)

    def test_analysis_score_mismatch_fails_before_resource_capture(self):
        _,score=self.register('score.musicxml',self.fixture_score())
        _,alternative=self.register('other.musicxml',self.fixture_score().replace(b'<step>C</step>',b'<step>F</step>'))
        _,analysis=self.register('analysis.json',b'{}',[score])
        _,lyrics=self.register('lyrics.json',b'{}')
        request=self.operation('plan_vocals','plan_and_align_vocals.py',
            {'music_analysis_json':analysis,'lyrics_json':lyrics,'score':alternative},['events.json'],
            ['{input:music_analysis_json}','{input:lyrics_json}','--score','{input:score}','--out','{output:result/events.json}'],['music21'])
        request['relations']=[{'input':'music_analysis_json','depends_on':'score'}]
        before=self.ledger.state()
        with self.assertRaisesRegex(LedgerError,'relationship'):
            prepare(self.ledger,request)
        self.assertEqual(self.ledger.state(),before)
        self.assertFalse((self.directory/'cache').exists())

    def test_geometry_registers_complete_declared_bundle(self):
        import cv2
        import numpy as np
        image=np.full((400,1600,3),255,dtype=np.uint8)
        for index in range(5):
            cv2.line(image,(100,150+index*12),(1500,190+index*12),(0,0,0),2)
        ok,encoded=cv2.imencode('.png',image); self.assertTrue(ok)
        source,image_ref=self.register('source.png',encoded.tobytes())
        _,seeds=self.register('seeds.json',b'[[100,1500,150,190,12,12]]')
        files=['geometry/geometry.json',*[f'geometry/system_1_{name}.png' for name in ('grid','source','dewarped')]]
        request=self.operation('score-to-musicxml','slope_grid.py',{'source':image_ref,'seeds':seeds},files,
            ['{input:source}','{input:seeds}','{output:result/geometry}'],['opencv-python-headless','numpy'])
        request['publish_json']=['{output:result/geometry/geometry.json}']
        directory,record,_=self.run_operation(request)
        result=json.loads((directory/'geometry/geometry.json').read_text())
        self.assertTrue(result['systems'][0]['accepted_geometry'])
        self.assertEqual(result['source_sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertIn('/history/',result['source'])
        self.assertEqual(len(record['files']),4)

    def test_download_then_extract_uses_separate_exact_dependency(self):
        text='This is a long lyric line with singing children\nAnother line repeats the melody and words\nAnd the final line completes this little song\n'
        external=self.directory/'external.txt'; external.write_text(text)
        _,evidence=self.register('choice.json',json.dumps({'url':external.as_uri(),'title':'Fixture'}).encode())
        request=self.operation('download-scores','download_scores.py',{'evidence':evidence},['raw.txt','receipt.json'],
            ['download',external.as_uri(),'--title','Fixture','--out','{output:result/raw.txt}','--receipt','{output:result/receipt.json}'])
        request['settings']={'url':external.as_uri(),'title':'Fixture'}
        directory,record,_=self.run_operation(request)
        receipt=json.loads((directory/'receipt.json').read_text())
        self.assertEqual(receipt['requested_url'],external.as_uri())
        raw={**{key:record[key] for key in ('artifact_id','revision_id')},'files':['raw.txt'],'purpose':'raw lyric page'}
        receipt_ref={**{key:record[key] for key in ('artifact_id','revision_id')},'files':['receipt.json'],'purpose':'acquisition evidence'}
        request=self.operation('download-scores','download_scores.py',{'raw':raw,'receipt':receipt_ref},['lyrics.txt'],
            ['extract','{input:raw}','--url',external.as_uri(),'--title','Fixture','--out','{output:result/lyrics.txt}'])
        directory,record,_=self.run_operation(request)
        self.assertEqual((directory/'lyrics.txt').read_text(),text)
        self.assertEqual(record['dependencies'],[raw,receipt_ref])

    def test_conversion_uses_frozen_tool_and_preserves_source(self):
        source,score=self.register('score.mid',b'MThd fixture')
        ref=self.tool('import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_bytes(b"%PDF fixture")\n')
        request=self.operation('download-scores','convert_score.py',{'score':score},['score.pdf','conversion.log'],
            ['{input:score}','--out','{output:result/score.pdf}','--log','{output:result/conversion.log}','--scratch','{scratch:convert}'])
        request['resources']={'musescore':ref}
        request['config']={'tools':{'musescore':{'command':'{tool:musescore}'}}}
        intent=prepare(self.ledger,request)
        (self.directory/'tool/tool.py').write_text('raise RuntimeError("live tool must not execute")')
        execute(self.ledger,intent['run_id']); event=finish(self.ledger,intent['run_id'])
        record=self.ledger.resolve(event['data']['updates'][0]['artifact_id'])
        self.assertEqual((self.data/record['history_path']/'score.pdf').read_bytes(),b'%PDF fixture')
        self.assertEqual(record['producer']['resources'],[ref])
        self.assertEqual(source.read_bytes(),b'MThd fixture')

    def test_pdf_review_captures_complete_bundle_and_tool_resource(self):
        _,pdf=self.register('score.pdf',b'%PDF fixture')
        ref=self.tool('import pathlib,sys\npathlib.Path(sys.argv[-1]+"-1.png").write_bytes(bytes.fromhex("89504e470d0a1a0a"))\n')
        request=self.operation('score-to-musicxml','render_pdf.py',{'pdf':pdf},['pages/page-1.png','pages/RENDER.log'],
            ['{input:pdf}','--out','{output:result/pages}'])
        request['resources']={'pdftoppm':ref}
        request['config']={'tools':{'pdftoppm':{'command':'{tool:pdftoppm}'}}}
        directory,record,_=self.run_operation(request)
        self.assertEqual((directory/'pages/page-1.png').read_bytes(),bytes.fromhex('89504e470d0a1a0a'))
        self.assertEqual(record['producer']['resources'],[ref])
        self.assertEqual(record['dependencies'],[pdf])

    def test_missing_synthesis_models_fail_without_publishing_partial_outputs(self):
        _,events=self.register('events.json',b'{}')
        _,lexicon=self.register('lexicon.json',b'{"la":["l","aa"]}')
        bank=self.directory/'bank'; bank.mkdir(); (bank/'README.txt').write_text('Incomplete synthetic bank')
        self.config['resources']['nishiren_root']=str(bank)
        event=self.ledger.register_resource('resources.nishiren_root',['README.txt'],label='Incomplete fixture',
            version='fixture',source={'fixture':True})
        ref=reference(event['data']['updates'][0])
        request=self.operation('synthesize_vocal_with_diffsinger','synthesize_vocal_with_diffsinger.py',
            {'vocal_events_json':events,'pronunciation_lexicon':lexicon},['voice.wav','debug.json','log.json'],
            ['{input:vocal_events_json}','--pronunciation-lexicon','{input:pronunciation_lexicon}',
             '--nishiren-root','{resource:nishiren}','--out','{output:result/voice.wav}',
             '--debug-out','{output:result/debug.json}','--log','{output:result/log.json}'])
        request['resources']={'nishiren':ref}
        intent=prepare(self.ledger,request)
        with self.assertRaisesRegex(LedgerError,'Missing Nishiren resources'):
            execute(self.ledger,intent['run_id'])
        self.assertFalse(any(item['kind']=='result' for item in self.ledger.state()['artifacts'].values()))
        work=self.data/intent['workspace']
        self.assertFalse(list((work/'outputs').rglob('*.wav')))
        self.assertEqual(intent['producer']['resources'],[ref])
        self.assertEqual(intent['outputs'][0]['dependencies'],[events,lexicon])


if __name__ == '__main__':
    unittest.main()
